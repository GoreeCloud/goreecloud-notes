"""Read-only attachment-binary evidence verification for GoreeCloud Notes migration manifests."""

from __future__ import annotations

import hashlib
import json
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

ATTACHMENT_MAP_FORMAT = "goreecloud-notes-attachment-map"
ATTACHMENT_MAP_SCHEMA_VERSION = 1
EVIDENCE_FORMAT = "goreecloud-notes-attachment-evidence"
EVIDENCE_SCHEMA_VERSION = 1
MIGRATION_MANIFEST_FORMAT = "goreecloud-notes-migration"
MIGRATION_MANIFEST_SCHEMA_VERSION = 1
DEFAULT_MAX_MANIFEST_BYTES = 512 * 1024 * 1024
DEFAULT_HASH_CHUNK_BYTES = 1024 * 1024


@dataclass(frozen=True)
class RequiredAttachment:
    source_name: str
    source_memo: str
    filename: str
    mime_type: str
    declared_size_bytes: int


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _sha256_bytes(encoded)


def _read_json_file(path: Path, *, max_bytes: int, label: str) -> tuple[dict[str, Any], bytes]:
    source = path.expanduser().resolve()
    size = source.stat().st_size
    if size > max_bytes:
        raise ValueError(f"{label} is {size} bytes, exceeding the configured {max_bytes}-byte limit.")
    raw = source.read_bytes()
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} root must be a JSON object.")
    return payload, raw


def _validate_manifest(payload: dict[str, Any]) -> list[RequiredAttachment]:
    if payload.get("format") != MIGRATION_MANIFEST_FORMAT:
        raise ValueError(f"Expected migration manifest format {MIGRATION_MANIFEST_FORMAT!r}.")
    if payload.get("schemaVersion") != MIGRATION_MANIFEST_SCHEMA_VERSION:
        raise ValueError("Only goreecloud-notes-migration schemaVersion 1 is supported.")

    validation = payload.get("validation")
    if not isinstance(validation, dict) or validation.get("sourceMetadataValid") is not True:
        raise ValueError("Migration manifest does not record a valid source metadata checkpoint.")
    if validation.get("sourceMutationPerformed") is not False or validation.get("targetMutationPerformed") is not False:
        raise ValueError("Migration manifest mutation boundary is missing or invalid.")

    source = payload.get("source")
    if not isinstance(source, dict):
        raise ValueError("Migration manifest source metadata is missing.")
    export_sha = source.get("sha256")
    if not isinstance(export_sha, str) or len(export_sha) != 64:
        raise ValueError("Migration manifest source export SHA-256 is missing or malformed.")

    notes = payload.get("notes")
    if not isinstance(notes, list):
        raise ValueError("Migration manifest notes must be a JSON array.")

    required: list[RequiredAttachment] = []
    seen_attachment_names: set[str] = set()
    for note_index, note in enumerate(notes):
        if not isinstance(note, dict):
            raise ValueError(f"Migration manifest note {note_index} is not an object.")
        record_sha = note.get("recordSha256")
        if not isinstance(record_sha, str) or len(record_sha) != 64:
            raise ValueError(f"Migration manifest note {note_index} is missing recordSha256.")
        unsigned_note = dict(note)
        unsigned_note.pop("recordSha256", None)
        if _canonical_sha256(unsigned_note) != record_sha:
            raise ValueError(f"Migration manifest note {note_index} recordSha256 does not match its normalized content.")

        attachments = note.get("attachments")
        if not isinstance(attachments, list):
            raise ValueError(f"Migration manifest note {note_index} attachments must be an array.")
        for attachment_index, attachment in enumerate(attachments):
            if not isinstance(attachment, dict):
                raise ValueError(f"Migration manifest note {note_index} attachment {attachment_index} is not an object.")
            binary = attachment.get("binary")
            if not isinstance(binary, dict):
                raise ValueError(f"Migration manifest attachment {note_index}:{attachment_index} has no binary state.")
            status = binary.get("status")
            if status not in {"required", "external"}:
                raise ValueError(f"Migration manifest attachment {note_index}:{attachment_index} has unsupported binary status {status!r}.")
            source_attachment = attachment.get("source")
            if not isinstance(source_attachment, dict):
                raise ValueError(f"Migration manifest attachment {note_index}:{attachment_index} has no source identity.")
            source_name = source_attachment.get("name")
            source_memo = source_attachment.get("memo")
            if not isinstance(source_name, str) or not source_name:
                raise ValueError(f"Migration manifest attachment {note_index}:{attachment_index} has no source name.")
            if source_name in seen_attachment_names:
                raise ValueError(f"Migration manifest contains duplicate attachment source name {source_name!r}.")
            seen_attachment_names.add(source_name)
            if not isinstance(source_memo, str) or not source_memo:
                raise ValueError(f"Migration manifest attachment {source_name!r} has no source memo.")
            if status == "external":
                continue
            declared_size = attachment.get("declaredSizeBytes")
            if type(declared_size) is not int or declared_size < 0:
                raise ValueError(f"Migration manifest attachment {source_name!r} has an invalid declared size.")
            filename = attachment.get("filename")
            mime_type = attachment.get("mimeType")
            if not isinstance(filename, str) or not filename:
                raise ValueError(f"Migration manifest attachment {source_name!r} has no filename.")
            if not isinstance(mime_type, str) or not mime_type:
                raise ValueError(f"Migration manifest attachment {source_name!r} has no MIME type.")
            required.append(
                RequiredAttachment(
                    source_name=source_name,
                    source_memo=source_memo,
                    filename=filename,
                    mime_type=mime_type,
                    declared_size_bytes=declared_size,
                )
            )
    return required


def _validate_attachment_map(payload: dict[str, Any], required_names: set[str]) -> dict[str, str]:
    if payload.get("format") != ATTACHMENT_MAP_FORMAT:
        raise ValueError(f"Expected attachment map format {ATTACHMENT_MAP_FORMAT!r}.")
    if payload.get("schemaVersion") != ATTACHMENT_MAP_SCHEMA_VERSION:
        raise ValueError("Only goreecloud-notes-attachment-map schemaVersion 1 is supported.")
    attachments = payload.get("attachments")
    if not isinstance(attachments, list):
        raise ValueError("Attachment map attachments must be a JSON array.")

    mapping: dict[str, str] = {}
    seen_paths: set[str] = set()
    for index, item in enumerate(attachments):
        if not isinstance(item, dict):
            raise ValueError(f"Attachment map item {index} must be an object.")
        source_name = item.get("sourceName")
        relative_path = item.get("relativePath")
        if not isinstance(source_name, str) or not source_name:
            raise ValueError(f"Attachment map item {index} has no sourceName.")
        if source_name not in required_names:
            raise ValueError(f"Attachment map references unexpected or external attachment {source_name!r}.")
        if source_name in mapping:
            raise ValueError(f"Attachment map contains duplicate sourceName {source_name!r}.")
        if not isinstance(relative_path, str) or not relative_path:
            raise ValueError(f"Attachment map item {source_name!r} has no relativePath.")
        pure_path = PurePosixPath(relative_path)
        if pure_path.is_absolute() or any(part in {"", ".", ".."} for part in pure_path.parts):
            raise ValueError(f"Attachment map path for {source_name!r} must be a clean relative POSIX path.")
        normalized = pure_path.as_posix()
        if normalized in seen_paths:
            raise ValueError(f"Attachment map reuses relativePath {normalized!r} for multiple attachments.")
        seen_paths.add(normalized)
        mapping[source_name] = normalized
    return mapping


def _validate_root(root: Path) -> Path:
    candidate = root.expanduser()
    root_stat = candidate.lstat()
    if stat.S_ISLNK(root_stat.st_mode):
        raise ValueError("Attachment evidence root itself must not be a symbolic link.")
    if not stat.S_ISDIR(root_stat.st_mode):
        raise ValueError("Attachment evidence root must be a directory.")
    return candidate.resolve(strict=True)


def _resolve_regular_file(root: Path, relative_path: str) -> Path:
    current = root
    for part in PurePosixPath(relative_path).parts:
        current = current / part
        try:
            component_stat = current.lstat()
        except FileNotFoundError as exc:
            raise FileNotFoundError(relative_path) from exc
        if stat.S_ISLNK(component_stat.st_mode):
            raise ValueError(f"Attachment evidence path {relative_path!r} traverses a symbolic link.")
    final_stat = current.stat()
    if not stat.S_ISREG(final_stat.st_mode):
        raise ValueError(f"Attachment evidence path {relative_path!r} is not a regular file.")
    return current


def _hash_file(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(DEFAULT_HASH_CHUNK_BYTES):
            size += len(chunk)
            digest.update(chunk)
    return size, digest.hexdigest()


def verify_attachment_binaries(
    manifest_path: Path,
    attachment_map_path: Path,
    evidence_root: Path,
    *,
    max_manifest_bytes: int = DEFAULT_MAX_MANIFEST_BYTES,
) -> dict[str, Any]:
    """Verify operator-supplied attachment bytes without changing source or target state."""

    manifest, manifest_raw = _read_json_file(
        manifest_path,
        max_bytes=max_manifest_bytes,
        label="Migration manifest",
    )
    required = _validate_manifest(manifest)
    required_by_name = {attachment.source_name: attachment for attachment in required}

    attachment_map, _ = _read_json_file(
        attachment_map_path,
        max_bytes=max_manifest_bytes,
        label="Attachment map",
    )
    mapping = _validate_attachment_map(attachment_map, set(required_by_name))
    root = _validate_root(evidence_root)

    verified: list[dict[str, Any]] = []
    missing: list[str] = []
    for attachment in required:
        relative_path = mapping.get(attachment.source_name)
        if relative_path is None:
            missing.append(attachment.source_name)
            continue
        try:
            file_path = _resolve_regular_file(root, relative_path)
        except FileNotFoundError:
            missing.append(attachment.source_name)
            continue
        verified_size, digest = _hash_file(file_path)
        if verified_size != attachment.declared_size_bytes:
            raise ValueError(
                f"Attachment {attachment.source_name!r} verified size {verified_size} does not match declared size {attachment.declared_size_bytes}."
            )
        verified.append(
            {
                "sourceName": attachment.source_name,
                "sourceMemo": attachment.source_memo,
                "filename": attachment.filename,
                "mimeType": attachment.mime_type,
                "relativePath": relative_path,
                "declaredSizeBytes": attachment.declared_size_bytes,
                "verifiedSizeBytes": verified_size,
                "sha256": digest,
            }
        )

    source = manifest["source"]
    return {
        "format": EVIDENCE_FORMAT,
        "schemaVersion": EVIDENCE_SCHEMA_VERSION,
        "manifest": {
            "sha256": _sha256_bytes(manifest_raw),
            "sizeBytes": len(manifest_raw),
            "sourceExportSha256": source["sha256"],
        },
        "verification": {
            "complete": not missing and len(verified) == len(required),
            "requiredAttachments": len(required),
            "verifiedAttachments": len(verified),
            "missingAttachments": len(missing),
            "sourceMutationPerformed": False,
            "targetMutationPerformed": False,
        },
        "attachments": verified,
        "missingSourceNames": missing,
    }


def serialize_evidence(evidence: dict[str, Any]) -> str:
    return json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
