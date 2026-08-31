"""Controlled persistence importer for validated transitional GoreeCloud/Memos data.

This module is intentionally downstream of the read-only export inspector, deterministic
migration manifest, and attachment-binary evidence verifier. It never connects to Memos.
It writes only to an explicitly selected *empty* native account and preserves each exact
normalized source record in migration provenance so currently deferred native semantics are
not silently lost.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any
from unicodedata import normalize
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..documents import DOCUMENT_SCHEMA, canonicalize_document, empty_document
from ..models import Attachment, Note, Notebook, NoteRevision, NoteTag, Tag, User
from .evidence import EVIDENCE_FORMAT, EVIDENCE_SCHEMA_VERSION
from .manifest import MANIFEST_FORMAT, MANIFEST_SCHEMA_VERSION
from .persistence import MigrationImport, MigrationNoteRecord

IMPORT_RESULT_FORMAT = "goreecloud-notes-memos-import-result"
IMPORT_RESULT_SCHEMA_VERSION = 1
CONVERSION_PROFILE = "literal-markdown-lines-v1"
DEFAULT_MAX_INPUT_BYTES = 512 * 1024 * 1024
_COPY_BUFFER_BYTES = 1024 * 1024
_HEX_COLOR_PATTERN = re.compile(r"^#[0-9a-fA-F]{6}$")


class MigrationImportError(ValueError):
    """Raised when a migration input or target state is unsafe or unsupported."""


@dataclass(frozen=True, slots=True)
class _AttachmentEvidence:
    source_name: str
    source_memo: str
    filename: str
    mime_type: str
    relative_path: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class _StagedAttachment:
    source_name: str
    attachment_id: UUID
    note_id: UUID
    temporary_path: Path
    final_path: Path


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_sha256(value: object) -> str:
    return _sha256_bytes(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    )


def _read_json(path: Path, *, label: str, max_bytes: int) -> tuple[dict[str, Any], bytes]:
    source = path.expanduser()
    try:
        source_stat = source.lstat()
    except OSError as exc:
        raise MigrationImportError(f"{label} is unavailable.") from exc
    if stat.S_ISLNK(source_stat.st_mode) or not stat.S_ISREG(source_stat.st_mode):
        raise MigrationImportError(f"{label} must be a regular file, not a symbolic link.")
    if source_stat.st_size > max_bytes:
        raise MigrationImportError(f"{label} exceeds the configured input-size limit.")
    try:
        raw = source.read_bytes()
        payload = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MigrationImportError(f"{label} is not valid UTF-8 JSON.") from exc
    if not isinstance(payload, dict):
        raise MigrationImportError(f"{label} root must be a JSON object.")
    return payload, raw


def _parse_timestamp(value: object, *, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise MigrationImportError(f"{field} must be a timestamp string.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MigrationImportError(f"{field} is not a valid ISO-8601 timestamp.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise MigrationImportError(f"{field} must contain timezone information.")
    return parsed.astimezone(UTC)


def _clean_name(value: object, *, field: str, max_length: int) -> str:
    if not isinstance(value, str):
        raise MigrationImportError(f"{field} must be a string.")
    cleaned = " ".join(normalize("NFKC", value).strip().split())
    if not cleaned or len(cleaned) > max_length:
        raise MigrationImportError(f"{field} must contain 1 to {max_length} characters after normalization.")
    return cleaned


def _normalized_tag_name(value: str) -> str:
    return _clean_name(value, field="tag", max_length=128).casefold()


def _clean_filename(value: object) -> str:
    if not isinstance(value, str):
        raise MigrationImportError("Attachment filename must be a string.")
    cleaned = value.strip()
    if not cleaned or len(cleaned) > 512:
        raise MigrationImportError("Attachment filename must contain 1 to 512 characters.")
    if Path(cleaned).name != cleaned or "/" in cleaned or "\\" in cleaned or cleaned in {".", ".."}:
        raise MigrationImportError("Attachment filename contains a path component.")
    if "\x00" in cleaned:
        raise MigrationImportError("Attachment filename contains a null byte.")
    return cleaned


def _native_color(value: object) -> str | None:
    """Import only colors the current native UI/API can represent without reinterpretation."""

    if value is None:
        return None
    if not isinstance(value, str):
        raise MigrationImportError("Source note color must be a string or null.")
    cleaned = value.strip()
    if _HEX_COLOR_PATTERN.fullmatch(cleaned):
        return cleaned.lower()
    return None


def markdown_to_literal_document(markdown: str) -> dict[str, object]:
    """Preserve every Markdown character visibly without pretending rich equivalence.

    Each source line becomes one paragraph whose text remains literal Markdown. Empty lines
    become empty paragraphs. The exact original Markdown is additionally retained in the
    immutable migration provenance record. This conversion is deliberately conservative until
    a separately reviewed Markdown-to-native-rich-text compatibility layer is approved.
    """

    if not markdown:
        return empty_document()
    blocks: list[dict[str, object]] = []
    for line in markdown.split("\n"):
        content: list[dict[str, object]] = []
        if line:
            content.append({"type": "text", "text": line})
        blocks.append({"type": "paragraph", "content": content})
    return canonicalize_document({"format": "goreecloud.blocks", "version": 1, "blocks": blocks})


def _validate_manifest(payload: dict[str, Any], raw: bytes) -> tuple[str, list[dict[str, Any]]]:
    if payload.get("format") != MANIFEST_FORMAT or payload.get("schemaVersion") != MANIFEST_SCHEMA_VERSION:
        raise MigrationImportError("Unsupported migration manifest format or schema version.")
    validation = payload.get("validation")
    if not isinstance(validation, dict) or validation.get("sourceMetadataValid") is not True:
        raise MigrationImportError("Migration manifest does not contain a valid source metadata checkpoint.")
    if validation.get("sourceMutationPerformed") is not False or validation.get("targetMutationPerformed") is not False:
        raise MigrationImportError("Migration manifest mutation boundary is invalid.")
    source = payload.get("source")
    if not isinstance(source, dict) or source.get("provider") != "memos":
        raise MigrationImportError("Migration manifest source provider is unsupported.")
    source_sha = source.get("sha256")
    if not isinstance(source_sha, str) or len(source_sha) != 64:
        raise MigrationImportError("Migration manifest source export SHA-256 is missing or malformed.")
    notes = payload.get("notes")
    if not isinstance(notes, list):
        raise MigrationImportError("Migration manifest notes must be an array.")
    inventory = payload.get("inventory")
    if not isinstance(inventory, dict) or inventory.get("notes") != len(notes):
        raise MigrationImportError("Migration manifest inventory does not match its note collection.")

    seen_names: set[str] = set()
    for index, note in enumerate(notes):
        if not isinstance(note, dict):
            raise MigrationImportError(f"Migration note {index} must be an object.")
        source_record = note.get("source")
        record_sha = note.get("recordSha256")
        if not isinstance(source_record, dict) or not isinstance(source_record.get("name"), str):
            raise MigrationImportError(f"Migration note {index} has no source identity.")
        source_name = source_record["name"]
        if source_name in seen_names:
            raise MigrationImportError(f"Migration manifest contains duplicate source note {source_name!r}.")
        seen_names.add(source_name)
        if not isinstance(record_sha, str) or len(record_sha) != 64:
            raise MigrationImportError(f"Migration note {source_name!r} has no valid record SHA-256.")
        unsigned = dict(note)
        unsigned.pop("recordSha256", None)
        if _canonical_sha256(unsigned) != record_sha:
            raise MigrationImportError(f"Migration note {source_name!r} record SHA-256 does not match its content.")

    return _sha256_bytes(raw), notes


def _validate_evidence(
    payload: dict[str, Any],
    raw: bytes,
    *,
    manifest_sha256: str,
    source_export_sha256: str,
    notes: list[dict[str, Any]],
) -> tuple[str, dict[str, _AttachmentEvidence]]:
    if payload.get("format") != EVIDENCE_FORMAT or payload.get("schemaVersion") != EVIDENCE_SCHEMA_VERSION:
        raise MigrationImportError("Unsupported attachment-evidence format or schema version.")
    manifest = payload.get("manifest")
    verification = payload.get("verification")
    if not isinstance(manifest, dict) or not isinstance(verification, dict):
        raise MigrationImportError("Attachment evidence is missing manifest or verification metadata.")
    if manifest.get("sha256") != manifest_sha256 or manifest.get("sourceExportSha256") != source_export_sha256:
        raise MigrationImportError("Attachment evidence does not belong to this exact migration manifest/source export.")
    if verification.get("complete") is not True:
        raise MigrationImportError("Attachment evidence is incomplete; target import is not allowed.")
    if verification.get("sourceMutationPerformed") is not False or verification.get("targetMutationPerformed") is not False:
        raise MigrationImportError("Attachment evidence mutation boundary is invalid.")

    evidence_records = payload.get("attachments")
    if not isinstance(evidence_records, list):
        raise MigrationImportError("Attachment evidence records must be an array.")
    by_name: dict[str, _AttachmentEvidence] = {}
    for raw_record in evidence_records:
        if not isinstance(raw_record, dict):
            raise MigrationImportError("Attachment evidence contains an invalid record.")
        source_name = raw_record.get("sourceName")
        source_memo = raw_record.get("sourceMemo")
        filename = raw_record.get("filename")
        mime_type = raw_record.get("mimeType")
        relative_path = raw_record.get("relativePath")
        size_bytes = raw_record.get("verifiedSizeBytes")
        digest = raw_record.get("sha256")
        if not all(isinstance(item, str) and item for item in (source_name, source_memo, filename, mime_type, relative_path, digest)):
            raise MigrationImportError("Attachment evidence record is missing required string fields.")
        if type(size_bytes) is not int or size_bytes < 0 or len(digest) != 64:
            raise MigrationImportError(f"Attachment evidence for {source_name!r} has invalid size or SHA-256.")
        if source_name in by_name:
            raise MigrationImportError(f"Attachment evidence contains duplicate source name {source_name!r}.")
        by_name[source_name] = _AttachmentEvidence(
            source_name=source_name,
            source_memo=source_memo,
            filename=filename,
            mime_type=mime_type,
            relative_path=relative_path,
            size_bytes=size_bytes,
            sha256=digest,
        )

    expected_names: set[str] = set()
    for note in notes:
        source_note = note["source"]
        attachments = note.get("attachments")
        if not isinstance(attachments, list):
            raise MigrationImportError(f"Migration note {source_note['name']!r} attachments must be an array.")
        for attachment in attachments:
            if not isinstance(attachment, dict):
                raise MigrationImportError("Migration attachment must be an object.")
            binary = attachment.get("binary")
            source_attachment = attachment.get("source")
            if not isinstance(binary, dict) or not isinstance(source_attachment, dict):
                raise MigrationImportError("Migration attachment is missing binary/source metadata.")
            status = binary.get("status")
            source_name = source_attachment.get("name")
            if status == "external":
                raise MigrationImportError(
                    "External-link attachments do not yet have an approved native persistence representation; import was refused."
                )
            if status != "required" or not isinstance(source_name, str) or not source_name:
                raise MigrationImportError("Migration attachment has unsupported binary state or source identity.")
            evidence = by_name.get(source_name)
            if evidence is None:
                raise MigrationImportError(f"Required attachment evidence is missing for {source_name!r}.")
            if evidence.source_memo != source_note["name"] or evidence.source_memo != source_attachment.get("memo"):
                raise MigrationImportError(f"Attachment evidence {source_name!r} points at the wrong source note.")
            if evidence.filename != attachment.get("filename") or evidence.mime_type != attachment.get("mimeType"):
                raise MigrationImportError(f"Attachment evidence metadata disagrees for {source_name!r}.")
            if evidence.size_bytes != attachment.get("declaredSizeBytes"):
                raise MigrationImportError(f"Attachment evidence size disagrees for {source_name!r}.")
            expected_names.add(source_name)

    if set(by_name) != expected_names:
        raise MigrationImportError("Attachment evidence contains unexpected or missing local attachment records.")
    return _sha256_bytes(raw), by_name


def _validate_evidence_root(root: Path) -> Path:
    candidate = root.expanduser()
    try:
        root_stat = candidate.lstat()
    except OSError as exc:
        raise MigrationImportError("Attachment evidence root is unavailable.") from exc
    if stat.S_ISLNK(root_stat.st_mode) or not stat.S_ISDIR(root_stat.st_mode):
        raise MigrationImportError("Attachment evidence root must be a real directory, not a symbolic link.")
    return candidate.resolve(strict=True)


def _resolve_evidence_file(root: Path, relative_path: str) -> Path:
    pure_path = PurePosixPath(relative_path)
    if pure_path.is_absolute() or any(part in {"", ".", ".."} for part in pure_path.parts):
        raise MigrationImportError("Attachment evidence contains an unsafe relative path.")
    current = root
    for part in pure_path.parts:
        current = current / part
        try:
            component_stat = current.lstat()
        except OSError as exc:
            raise MigrationImportError(f"Attachment evidence file {relative_path!r} is unavailable.") from exc
        if stat.S_ISLNK(component_stat.st_mode):
            raise MigrationImportError(f"Attachment evidence path {relative_path!r} traverses a symbolic link.")
    if not current.is_file():
        raise MigrationImportError(f"Attachment evidence path {relative_path!r} is not a regular file.")
    return current


def _hash_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size_bytes = 0
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(_COPY_BUFFER_BYTES):
                size_bytes += len(chunk)
                digest.update(chunk)
    except OSError as exc:
        raise MigrationImportError("Unable to hash attachment evidence bytes.") from exc
    return digest.hexdigest(), size_bytes


def _safe_storage_path(root: Path, storage_key: str) -> Path:
    resolved_root = root.expanduser().resolve()
    candidate = (resolved_root / storage_key).resolve()
    try:
        candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise MigrationImportError("Generated attachment storage key escaped the configured root.") from exc
    return candidate


def _target_data_count(db: Session, *, owner_id: UUID) -> int:
    models = (Notebook, Note, Tag, NoteTag, Attachment, NoteRevision, MigrationImport, MigrationNoteRecord)
    total = 0
    for model in models:
        owner_column = getattr(model, "owner_id")
        total += int(db.scalar(select(func.count()).select_from(model).where(owner_column == owner_id)) or 0)
    return total


def _preflight_note(note: dict[str, Any], *, attachment_max_bytes: int) -> None:
    source = note.get("source")
    content = note.get("content")
    lifecycle = note.get("lifecycle")
    metadata = note.get("metadata")
    if not all(isinstance(item, dict) for item in (source, content, lifecycle, metadata)):
        raise MigrationImportError("Migration note is missing source/content/lifecycle/metadata fields.")
    source_name = source.get("name")
    if not isinstance(source_name, str) or not source_name or len(source_name) > 512:
        raise MigrationImportError("Migration source note name is invalid or too long.")
    source_uid = source.get("uid")
    if source_uid is not None and (not isinstance(source_uid, str) or len(source_uid) > 255):
        raise MigrationImportError(f"Migration source UID for {source_name!r} is invalid or too long.")
    source_order = source.get("order")
    if type(source_order) is not int or source_order < 0:
        raise MigrationImportError(f"Migration source order for {source_name!r} is invalid.")

    title = content.get("title")
    if title is not None and (not isinstance(title, str) or len(title) > 512):
        raise MigrationImportError(f"Source title for {source_name!r} exceeds native limits.")
    markdown = content.get("markdown")
    if not isinstance(markdown, str):
        raise MigrationImportError(f"Source Markdown for {source_name!r} must be a string.")
    if _sha256_bytes(markdown.encode("utf-8")) != content.get("markdownSha256"):
        raise MigrationImportError(f"Source Markdown SHA-256 disagrees for {source_name!r}.")
    try:
        markdown_to_literal_document(markdown)
    except ValueError as exc:
        raise MigrationImportError(f"Source Markdown for {source_name!r} exceeds the current native document budget.") from exc

    if lifecycle.get("state") not in {"active", "archived", "trashed"}:
        raise MigrationImportError(f"Source lifecycle state for {source_name!r} is unsupported.")
    if type(lifecycle.get("pinned")) is not bool:
        raise MigrationImportError(f"Source pinned state for {source_name!r} must be boolean.")
    if metadata.get("visibility") != "PRIVATE":
        raise MigrationImportError(
            f"Source note {source_name!r} is not PRIVATE; sharing/public semantics are not approved for native import."
        )
    _parse_timestamp(metadata.get("createTime"), field=f"{source_name}.createTime")
    _parse_timestamp(metadata.get("updateTime"), field=f"{source_name}.updateTime")
    tags = metadata.get("tags")
    if not isinstance(tags, list):
        raise MigrationImportError(f"Source tags for {source_name!r} must be an array.")
    for tag in tags:
        _normalized_tag_name(tag)

    attachments = note.get("attachments")
    if not isinstance(attachments, list):
        raise MigrationImportError(f"Source attachments for {source_name!r} must be an array.")
    for attachment in attachments:
        if not isinstance(attachment, dict):
            raise MigrationImportError(f"Source attachment for {source_name!r} must be an object.")
        _clean_filename(attachment.get("filename"))
        media_type = attachment.get("mimeType")
        if not isinstance(media_type, str) or not media_type or len(media_type) > 255:
            raise MigrationImportError(f"Source attachment MIME type for {source_name!r} is invalid.")
        size_bytes = attachment.get("declaredSizeBytes")
        if type(size_bytes) is not int or size_bytes < 0 or size_bytes > attachment_max_bytes:
            raise MigrationImportError(
                f"Source attachment for {source_name!r} exceeds current native attachment limits."
            )
        _parse_timestamp(attachment.get("createTime"), field=f"{source_name}.attachment.createTime")


def _copy_evidence_to_temporary(
    *,
    evidence_file: Path,
    temporary_path: Path,
    expected_sha256: str,
    expected_size: int,
) -> None:
    temporary_path.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    size_bytes = 0
    try:
        with evidence_file.open("rb") as source, temporary_path.open("xb") as target:
            while chunk := source.read(_COPY_BUFFER_BYTES):
                size_bytes += len(chunk)
                digest.update(chunk)
                target.write(chunk)
            target.flush()
            os.fsync(target.fileno())
    except OSError as exc:
        temporary_path.unlink(missing_ok=True)
        raise MigrationImportError("Unable to stage verified attachment bytes for native import.") from exc
    if size_bytes != expected_size or digest.hexdigest() != expected_sha256:
        temporary_path.unlink(missing_ok=True)
        raise MigrationImportError("Attachment evidence changed while native import was staging bytes.")


def import_memos_manifest(
    db: Session,
    *,
    owner: User,
    manifest_path: Path,
    evidence_path: Path,
    evidence_root: Path,
    attachment_root: Path,
    attachment_max_bytes: int,
    max_input_bytes: int = DEFAULT_MAX_INPUT_BYTES,
) -> dict[str, Any]:
    """Import a validated Memos manifest into one empty native account atomically.

    The database write is one transaction. Attachment bytes are staged under generated
    temporary paths before rows are flushed, then atomically renamed to their final generated
    paths before commit. On any caught failure, newly created files are removed and the DB
    transaction is rolled back. A process/power loss at the final rename/commit boundary can
    leave unreferenced bytes but will not create a committed row that silently points at bytes
    that were never staged.
    """

    if max_input_bytes <= 0:
        raise MigrationImportError("Input-size limit must be positive.")
    if _target_data_count(db, owner_id=owner.id) != 0:
        raise MigrationImportError("Target account is not empty; migration import was refused to prevent duplication or merging.")

    manifest, manifest_raw = _read_json(manifest_path, label="Migration manifest", max_bytes=max_input_bytes)
    manifest_sha256, notes = _validate_manifest(manifest, manifest_raw)
    source = manifest["source"]
    source_export_sha256 = source["sha256"]
    source_exported_at = _parse_timestamp(source.get("exportedAt"), field="source.exportedAt")

    evidence, evidence_raw = _read_json(evidence_path, label="Attachment evidence", max_bytes=max_input_bytes)
    evidence_sha256, evidence_by_name = _validate_evidence(
        evidence,
        evidence_raw,
        manifest_sha256=manifest_sha256,
        source_export_sha256=source_export_sha256,
        notes=notes,
    )
    resolved_evidence_root = _validate_evidence_root(evidence_root)
    resolved_attachment_root = attachment_root.expanduser().resolve()
    resolved_attachment_root.mkdir(parents=True, exist_ok=True)

    for note in notes:
        _preflight_note(note, attachment_max_bytes=attachment_max_bytes)

    # Re-hash every evidence file before any target mutation begins.
    evidence_paths: dict[str, Path] = {}
    for source_name, expected in evidence_by_name.items():
        evidence_file = _resolve_evidence_file(resolved_evidence_root, expected.relative_path)
        digest, size_bytes = _hash_file(evidence_file)
        if digest != expected.sha256 or size_bytes != expected.size_bytes:
            raise MigrationImportError(f"Attachment evidence bytes no longer match verified evidence for {source_name!r}.")
        evidence_paths[source_name] = evidence_file

    import_id = uuid4()
    note_ids = {note["source"]["name"]: uuid4() for note in notes}
    attachment_ids: dict[str, UUID] = {}
    staged: list[_StagedAttachment] = []
    finalized_paths: list[Path] = []
    tag_ids: dict[str, UUID] = {}
    source_tag_display: dict[str, str] = {}
    deferred_relations = 0
    deferred_locations = 0
    deferred_restore_targets = 0
    deferred_colors = 0

    try:
        for note in notes:
            source_note = note["source"]
            content = note["content"]
            lifecycle = note["lifecycle"]
            metadata = note["metadata"]
            source_name = source_note["name"]
            note_id = note_ids[source_name]
            markdown = content["markdown"]
            native_document = markdown_to_literal_document(markdown)
            native_state = {
                "active": "normal",
                "archived": "archived",
                "trashed": "trashed",
            }[lifecycle["state"]]
            source_color = metadata.get("color")
            color = _native_color(source_color)
            if source_color is not None and color is None:
                deferred_colors += 1
            if lifecycle.get("restoreTarget") is not None:
                deferred_restore_targets += 1
            if metadata.get("location") is not None:
                deferred_locations += 1
            relations = note.get("relations", [])
            deferred_relations += len(relations)

            created_at = _parse_timestamp(metadata["createTime"], field=f"{source_name}.createTime")
            updated_at = _parse_timestamp(metadata["updateTime"], field=f"{source_name}.updateTime")
            native_note = Note(
                id=note_id,
                owner_id=owner.id,
                notebook_id=None,
                title=content.get("title") or "",
                document=native_document,
                document_schema=DOCUMENT_SCHEMA,
                content_version=1,
                state=native_state,
                is_pinned=lifecycle["pinned"],
                color=color,
                created_at=created_at,
                updated_at=updated_at,
            )
            db.add(native_note)
            db.add(
                MigrationNoteRecord(
                    import_id=import_id,
                    owner_id=owner.id,
                    note_id=note_id,
                    source_name=source_name,
                    source_uid=source_note.get("uid"),
                    source_order=source_note["order"],
                    record_sha256=note["recordSha256"],
                    source_record=note,
                )
            )

            for source_tag in metadata["tags"]:
                display_name = _clean_name(source_tag, field="tag", max_length=128)
                normalized = display_name.casefold()
                tag_id = tag_ids.get(normalized)
                if tag_id is None:
                    tag_id = uuid4()
                    tag_ids[normalized] = tag_id
                    source_tag_display[normalized] = display_name
                    db.add(
                        Tag(
                            id=tag_id,
                            owner_id=owner.id,
                            name=display_name,
                            normalized_name=normalized,
                            color=None,
                        )
                    )
                db.add(
                    NoteTag(
                        owner_id=owner.id,
                        note_id=note_id,
                        tag_id=tag_id,
                        created_at=created_at,
                    )
                )

            for attachment in note["attachments"]:
                source_attachment = attachment["source"]
                attachment_source_name = source_attachment["name"]
                expected = evidence_by_name[attachment_source_name]
                attachment_id = uuid4()
                attachment_ids[attachment_source_name] = attachment_id
                storage_key = f"{owner.id}/{note_id}/{attachment_id}"
                final_path = _safe_storage_path(resolved_attachment_root, storage_key)
                temporary_path = final_path.with_name(f".{final_path.name}.{uuid4().hex}.part")
                _copy_evidence_to_temporary(
                    evidence_file=evidence_paths[attachment_source_name],
                    temporary_path=temporary_path,
                    expected_sha256=expected.sha256,
                    expected_size=expected.size_bytes,
                )
                staged.append(
                    _StagedAttachment(
                        source_name=attachment_source_name,
                        attachment_id=attachment_id,
                        note_id=note_id,
                        temporary_path=temporary_path,
                        final_path=final_path,
                    )
                )
                attachment_created_at = _parse_timestamp(
                    attachment["createTime"],
                    field=f"{source_name}.{attachment_source_name}.createTime",
                )
                db.add(
                    Attachment(
                        id=attachment_id,
                        owner_id=owner.id,
                        note_id=note_id,
                        filename=_clean_filename(attachment["filename"]),
                        media_type=attachment["mimeType"],
                        size_bytes=expected.size_bytes,
                        sha256=expected.sha256,
                        storage_key=storage_key,
                        extra_metadata={
                            "migration": {
                                "provider": "memos",
                                "sourceName": attachment_source_name,
                                "sourceMemo": source_name,
                                "manifestSha256": manifest_sha256,
                                "evidenceSha256": evidence_sha256,
                                "verifiedSha256": expected.sha256,
                                "verifiedSizeBytes": expected.size_bytes,
                                "sourceCreateTime": attachment["createTime"],
                                "sourceMetadata": attachment.get("sourceMetadata"),
                            }
                        },
                        created_at=attachment_created_at,
                        updated_at=attachment_created_at,
                    )
                )

        db.add(
            MigrationImport(
                id=import_id,
                owner_id=owner.id,
                provider="memos",
                source_export_sha256=source_export_sha256,
                manifest_sha256=manifest_sha256,
                evidence_sha256=evidence_sha256,
                source_exported_at=source_exported_at,
                source_note_count=len(notes),
                imported_note_count=len(notes),
                conversion_profile=CONVERSION_PROFILE,
            )
        )
        db.flush()

        for item in staged:
            item.final_path.parent.mkdir(parents=True, exist_ok=True)
            os.replace(item.temporary_path, item.final_path)
            finalized_paths.append(item.final_path)

        db.commit()
    except Exception:
        db.rollback()
        for item in staged:
            item.temporary_path.unlink(missing_ok=True)
        for path in finalized_paths:
            path.unlink(missing_ok=True)
        raise

    return {
        "format": IMPORT_RESULT_FORMAT,
        "schemaVersion": IMPORT_RESULT_SCHEMA_VERSION,
        "import": {
            "id": str(import_id),
            "ownerId": str(owner.id),
            "provider": "memos",
            "sourceExportSha256": source_export_sha256,
            "manifestSha256": manifest_sha256,
            "evidenceSha256": evidence_sha256,
            "conversionProfile": CONVERSION_PROFILE,
        },
        "counts": {
            "notes": len(notes),
            "tags": len(tag_ids),
            "attachments": len(attachment_ids),
            "provenanceRecords": len(notes),
        },
        "mappings": {
            "notes": [
                {
                    "sourceName": note["source"]["name"],
                    "sourceUid": note["source"].get("uid"),
                    "sourceRecordSha256": note["recordSha256"],
                    "targetNoteId": str(note_ids[note["source"]["name"]]),
                }
                for note in notes
            ],
            "attachments": [
                {
                    "sourceName": source_name,
                    "targetAttachmentId": str(attachment_id),
                    "sha256": evidence_by_name[source_name].sha256,
                    "sizeBytes": evidence_by_name[source_name].size_bytes,
                }
                for source_name, attachment_id in sorted(attachment_ids.items())
            ],
            "tags": [
                {
                    "normalizedName": normalized,
                    "sourceDisplayName": source_tag_display[normalized],
                    "targetTagId": str(tag_id),
                }
                for normalized, tag_id in sorted(tag_ids.items())
            ],
        },
        "equivalence": {
            "sourceRecordsPreserved": True,
            "attachmentBytesVerifiedAndCopied": True,
            "sourceMutationPerformed": False,
            "targetMutationPerformed": True,
            "nativeSemanticEquivalenceComplete": False,
            "deferred": {
                "markdownRichFormatting": len(notes),
                "relations": deferred_relations,
                "locations": deferred_locations,
                "trashRestoreTargets": deferred_restore_targets,
                "unmappedNamedColors": deferred_colors,
            },
        },
    }


def verify_imported_memos_data(
    db: Session,
    *,
    owner: User,
    import_id: UUID,
    attachment_root: Path,
) -> dict[str, Any]:
    """Re-verify native target rows, provenance, tags, and attachment bytes after commit."""

    migration_import = db.scalar(
        select(MigrationImport).where(
            MigrationImport.id == import_id,
            MigrationImport.owner_id == owner.id,
        )
    )
    if migration_import is None:
        raise MigrationImportError("Migration import checkpoint was not found for this account.")

    records = list(
        db.scalars(
            select(MigrationNoteRecord)
            .where(
                MigrationNoteRecord.import_id == import_id,
                MigrationNoteRecord.owner_id == owner.id,
            )
            .order_by(MigrationNoteRecord.source_order.asc(), MigrationNoteRecord.source_name.asc())
        )
    )
    if len(records) != migration_import.imported_note_count or len(records) != migration_import.source_note_count:
        raise MigrationImportError("Migration provenance record count does not match the import checkpoint.")

    verified_attachments = 0
    verified_tags: set[UUID] = set()
    deferred_relations = 0
    deferred_locations = 0
    deferred_restore_targets = 0
    deferred_colors = 0
    resolved_attachment_root = attachment_root.expanduser().resolve()

    for record in records:
        source_record = record.source_record
        if not isinstance(source_record, dict):
            raise MigrationImportError("Migration provenance source record is invalid.")
        unsigned = dict(source_record)
        stored_record_sha = unsigned.pop("recordSha256", None)
        if stored_record_sha != record.record_sha256 or _canonical_sha256(unsigned) != record.record_sha256:
            raise MigrationImportError(f"Migration provenance hash mismatch for {record.source_name!r}.")

        note = db.scalar(
            select(Note).where(
                Note.id == record.note_id,
                Note.owner_id == owner.id,
            )
        )
        if note is None:
            raise MigrationImportError(f"Imported native note is missing for {record.source_name!r}.")
        content = source_record["content"]
        lifecycle = source_record["lifecycle"]
        metadata = source_record["metadata"]
        expected_state = {"active": "normal", "archived": "archived", "trashed": "trashed"}[lifecycle["state"]]
        expected_document = markdown_to_literal_document(content["markdown"])
        if (
            note.title != (content.get("title") or "")
            or note.document != expected_document
            or note.document_schema != DOCUMENT_SCHEMA
            or note.content_version != 1
            or note.state != expected_state
            or note.is_pinned is not lifecycle["pinned"]
            or note.color != _native_color(metadata.get("color"))
            or note.notebook_id is not None
        ):
            raise MigrationImportError(f"Imported native note content/state mismatch for {record.source_name!r}.")

        expected_tags = {_normalized_tag_name(tag) for tag in metadata["tags"]}
        assigned_tags = list(
            db.scalars(
                select(Tag)
                .join(NoteTag, NoteTag.tag_id == Tag.id)
                .where(
                    NoteTag.owner_id == owner.id,
                    NoteTag.note_id == note.id,
                    Tag.owner_id == owner.id,
                )
            )
        )
        if {tag.normalized_name for tag in assigned_tags} != expected_tags:
            raise MigrationImportError(f"Imported native tag assignment mismatch for {record.source_name!r}.")
        verified_tags.update(tag.id for tag in assigned_tags)

        source_attachments = source_record.get("attachments", [])
        target_attachments = list(
            db.scalars(
                select(Attachment)
                .where(
                    Attachment.owner_id == owner.id,
                    Attachment.note_id == note.id,
                )
                .order_by(Attachment.created_at.asc(), Attachment.id.asc())
            )
        )
        if len(source_attachments) != len(target_attachments):
            raise MigrationImportError(f"Imported attachment count mismatch for {record.source_name!r}.")
        target_by_source: dict[str, Attachment] = {}
        for attachment in target_attachments:
            migration_metadata = attachment.extra_metadata.get("migration") if isinstance(attachment.extra_metadata, dict) else None
            source_name = migration_metadata.get("sourceName") if isinstance(migration_metadata, dict) else None
            if not isinstance(source_name, str) or source_name in target_by_source:
                raise MigrationImportError("Imported attachment provenance is missing or duplicated.")
            if migration_metadata.get("manifestSha256") != migration_import.manifest_sha256 or migration_metadata.get("evidenceSha256") != migration_import.evidence_sha256:
                raise MigrationImportError("Imported attachment provenance does not match the import checkpoint.")
            target_by_source[source_name] = attachment

        for source_attachment in source_attachments:
            source_identity = source_attachment["source"]
            source_name = source_identity["name"]
            target = target_by_source.get(source_name)
            if target is None:
                raise MigrationImportError(f"Imported attachment is missing for source {source_name!r}.")
            migration_metadata = target.extra_metadata["migration"]
            if target.filename != source_attachment["filename"] or target.media_type != source_attachment["mimeType"]:
                raise MigrationImportError(f"Imported attachment metadata mismatch for {source_name!r}.")
            if target.sha256 != migration_metadata.get("verifiedSha256") or target.size_bytes != migration_metadata.get("verifiedSizeBytes"):
                raise MigrationImportError(f"Imported attachment evidence metadata mismatch for {source_name!r}.")
            path = _safe_storage_path(resolved_attachment_root, target.storage_key)
            if not path.is_file():
                raise MigrationImportError(f"Imported attachment bytes are missing for {source_name!r}.")
            digest, size_bytes = _hash_file(path)
            if digest != target.sha256 or size_bytes != target.size_bytes:
                raise MigrationImportError(f"Imported attachment byte integrity failed for {source_name!r}.")
            verified_attachments += 1

        deferred_relations += len(source_record.get("relations", []))
        if metadata.get("location") is not None:
            deferred_locations += 1
        if lifecycle.get("restoreTarget") is not None:
            deferred_restore_targets += 1
        if metadata.get("color") is not None and _native_color(metadata.get("color")) is None:
            deferred_colors += 1

    return {
        "format": "goreecloud-notes-memos-import-verification",
        "schemaVersion": 1,
        "import": {
            "id": str(migration_import.id),
            "ownerId": str(owner.id),
            "provider": migration_import.provider,
            "sourceExportSha256": migration_import.source_export_sha256,
            "manifestSha256": migration_import.manifest_sha256,
            "evidenceSha256": migration_import.evidence_sha256,
            "conversionProfile": migration_import.conversion_profile,
        },
        "verification": {
            "databaseProvenanceValid": True,
            "nativeNoteProjectionValid": True,
            "tagAssignmentsValid": True,
            "attachmentByteIntegrityValid": True,
            "notes": len(records),
            "tags": len(verified_tags),
            "attachments": verified_attachments,
            "sourceMutationPerformed": False,
            "targetVerificationMutationPerformed": False,
        },
        "equivalence": {
            "sourceRecordsPreserved": True,
            "nativeSemanticEquivalenceComplete": False,
            "deferred": {
                "markdownRichFormatting": len(records),
                "relations": deferred_relations,
                "locations": deferred_locations,
                "trashRestoreTargets": deferred_restore_targets,
                "unmappedNamedColors": deferred_colors,
            },
        },
    }


def serialize_import_result(result: dict[str, Any]) -> str:
    return json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
