"""Controlled Evernote ENEX resource extraction with deterministic integrity evidence."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import shutil
import stat
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .enex import DEFAULT_MAX_ENEX_BYTES, EnexExportReport, inspect_enex_export

DEFAULT_MAX_ENEX_RESOURCE_BYTES = 128 * 1024 * 1024
DEFAULT_MAX_ENEX_EXTRACTED_BYTES = 256 * 1024 * 1024
DEFAULT_MAX_ENEX_RESOURCE_COUNT = 10_000
EVIDENCE_FILENAME = "enex-resource-evidence.json"


@dataclass(frozen=True)
class _ResourcePlan:
    note_index: int
    resource_index: int
    element: ET.Element
    mime: str
    source_file_name: str | None
    source_hash: str | None
    size_bytes: int
    sha256: str
    relative_path: str
    duplicate_of: str | None


def _validate_limits(
    *,
    max_bytes: int,
    max_resource_bytes: int,
    max_total_bytes: int,
    max_resources: int,
) -> None:
    limits = {
        "ENEX input size": max_bytes,
        "per-resource size": max_resource_bytes,
        "total extracted-resource size": max_total_bytes,
        "resource count": max_resources,
    }
    for label, value in limits.items():
        if value <= 0:
            raise ValueError(f"{label} limit must be positive.")


def _source_bytes_if_unchanged(report: EnexExportReport) -> bytes:
    source = Path(report.source_path)
    try:
        source_stat = source.lstat()
    except OSError as exc:
        raise ValueError("ENEX source became unavailable during extraction.") from exc
    if stat.S_ISLNK(source_stat.st_mode) or not stat.S_ISREG(source_stat.st_mode):
        raise ValueError("ENEX source changed type during extraction.")
    raw = source.read_bytes()
    if len(raw) != report.source_size_bytes:
        raise ValueError("ENEX source size changed after inspection; extraction was refused.")
    digest = hashlib.sha256(raw).hexdigest()
    if digest != report.source_sha256:
        raise ValueError("ENEX source fingerprint changed after inspection; extraction was refused.")
    return raw


def _decode_resource(resource: ET.Element) -> bytes:
    data = resource.find("data")
    if data is None or data.get("encoding") != "base64":
        raise ValueError("Validated ENEX resource no longer contains supported base64 data.")
    compact = "".join((data.text or "").split())
    try:
        return base64.b64decode(compact.encode("ascii"), validate=True)
    except (UnicodeEncodeError, binascii.Error) as exc:
        raise ValueError("Validated ENEX resource data is no longer valid base64.") from exc


def _resource_file_name(resource: ET.Element) -> str | None:
    value = resource.findtext("resource-attributes/file-name")
    if value is None or not value.strip():
        return None
    return value.strip()


def _build_plan(
    root: ET.Element,
    report: EnexExportReport,
    *,
    max_resource_bytes: int,
    max_total_bytes: int,
    max_resources: int,
) -> tuple[list[_ResourcePlan], int]:
    if report.resource_count > max_resources:
        raise ValueError(
            f"ENEX contains {report.resource_count} resources, exceeding the configured "
            f"{max_resources}-resource extraction limit."
        )

    plans: list[_ResourcePlan] = []
    seen_sha256: dict[str, str] = {}
    total_bytes = 0

    for note_index, note in enumerate(root.findall("note")):
        for resource_index, resource in enumerate(note.findall("resource")):
            decoded = _decode_resource(resource)
            size_bytes = len(decoded)
            if size_bytes > max_resource_bytes:
                raise ValueError(
                    f"ENEX resource note[{note_index}].resource[{resource_index}] is {size_bytes} bytes, "
                    f"exceeding the configured {max_resource_bytes}-byte per-resource limit."
                )
            total_bytes += size_bytes
            if total_bytes > max_total_bytes:
                raise ValueError(
                    f"Decoded ENEX resources total {total_bytes} bytes, exceeding the configured "
                    f"{max_total_bytes}-byte extraction limit."
                )

            sha256 = hashlib.sha256(decoded).hexdigest()
            relative_path = (
                f"resources/note-{note_index:06d}/"
                f"resource-{resource_index:06d}-{sha256}.bin"
            )
            duplicate_of = seen_sha256.get(sha256)
            seen_sha256.setdefault(sha256, relative_path)

            data = resource.find("data")
            source_hash = data.get("hash") if data is not None else None
            mime = (resource.findtext("mime") or "").strip().casefold()

            plans.append(
                _ResourcePlan(
                    note_index=note_index,
                    resource_index=resource_index,
                    element=resource,
                    mime=mime,
                    source_file_name=_resource_file_name(resource),
                    source_hash=source_hash,
                    size_bytes=size_bytes,
                    sha256=sha256,
                    relative_path=relative_path,
                    duplicate_of=duplicate_of,
                )
            )

    if len(plans) != report.resource_count:
        raise ValueError("ENEX resource inventory changed after inspection; extraction was refused.")
    if total_bytes != report.embedded_resource_bytes:
        raise ValueError("ENEX decoded resource-byte inventory changed after inspection; extraction was refused.")
    return plans, total_bytes


def _absolute_unresolved(path: Path) -> Path:
    expanded = path.expanduser()
    return Path(os.path.abspath(expanded))


def _assert_no_symlink_ancestor(path: Path) -> None:
    current = path
    while True:
        if current.exists():
            try:
                current_stat = current.lstat()
            except OSError as exc:
                raise ValueError("Unable to inspect ENEX extraction output path.") from exc
            if stat.S_ISLNK(current_stat.st_mode):
                raise ValueError("ENEX extraction output path must not traverse symbolic links.")
        parent = current.parent
        if parent == current:
            return
        current = parent


def _prepare_output_root(output_root: Path) -> Path:
    target = _absolute_unresolved(output_root)

    try:
        target_stat = target.lstat()
    except FileNotFoundError:
        target_stat = None
    except OSError as exc:
        raise ValueError("Unable to inspect ENEX extraction output path.") from exc

    if target_stat is not None:
        if stat.S_ISLNK(target_stat.st_mode):
            raise ValueError("ENEX extraction output path must not be a symbolic link.")
        raise ValueError(
            "ENEX extraction output path must not already exist; choose a new empty destination."
        )

    parent = target.parent
    _assert_no_symlink_ancestor(parent)
    try:
        parent_stat = parent.lstat()
    except OSError as exc:
        raise ValueError("ENEX extraction output parent is unavailable.") from exc
    if not stat.S_ISDIR(parent_stat.st_mode):
        raise ValueError("ENEX extraction output parent must be a directory.")

    return target


def _contained_output_path(root: Path, relative_path: str) -> Path:
    candidate = root / relative_path
    root_resolved = root.resolve(strict=True)
    candidate_parent = candidate.parent
    candidate_parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    parent_resolved = candidate_parent.resolve(strict=True)
    if not parent_resolved.is_relative_to(root_resolved):
        raise ValueError("Generated ENEX resource path escaped the extraction root.")
    return candidate


def _exclusive_write(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        try:
            path.unlink(missing_ok=True)
        finally:
            raise


def _hash_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size_bytes = 0
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
            size_bytes += len(chunk)
    return digest.hexdigest(), size_bytes


def serialize_enex_resource_evidence(evidence: dict[str, Any]) -> str:
    """Serialize deterministic ENEX resource evidence."""

    return json.dumps(evidence, indent=2, sort_keys=True) + "\n"


def extract_enex_resources(
    source_path: Path,
    output_root: Path,
    *,
    max_bytes: int = DEFAULT_MAX_ENEX_BYTES,
    max_resource_bytes: int = DEFAULT_MAX_ENEX_RESOURCE_BYTES,
    max_total_bytes: int = DEFAULT_MAX_ENEX_EXTRACTED_BYTES,
    max_resources: int = DEFAULT_MAX_ENEX_RESOURCE_COUNT,
) -> dict[str, Any]:
    """Extract ENEX resource bytes into a new root without touching native target data."""

    _validate_limits(
        max_bytes=max_bytes,
        max_resource_bytes=max_resource_bytes,
        max_total_bytes=max_total_bytes,
        max_resources=max_resources,
    )

    report = inspect_enex_export(source_path, max_bytes=max_bytes)
    if not report.metadata_valid:
        raise ValueError(
            "ENEX resource extraction requires a metadata-valid inspection report; "
            "correct or review inspection errors before extraction."
        )

    raw = _source_bytes_if_unchanged(report)
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ValueError("ENEX source became unparsable after inspection.") from exc

    plans, total_bytes = _build_plan(
        root,
        report,
        max_resource_bytes=max_resource_bytes,
        max_total_bytes=max_total_bytes,
        max_resources=max_resources,
    )
    target = _prepare_output_root(output_root)

    created_output = False
    try:
        target.mkdir(mode=0o700)
        created_output = True

        resources: list[dict[str, Any]] = []
        for plan in plans:
            decoded = _decode_resource(plan.element)
            if len(decoded) != plan.size_bytes or hashlib.sha256(decoded).hexdigest() != plan.sha256:
                raise ValueError("ENEX resource bytes changed between validation and extraction.")

            output_path = _contained_output_path(target, plan.relative_path)
            _exclusive_write(output_path, decoded)
            written_sha256, written_size = _hash_file(output_path)
            if written_sha256 != plan.sha256 or written_size != plan.size_bytes:
                raise OSError("Extracted ENEX resource failed post-write SHA-256 verification.")

            resources.append(
                {
                    "noteIndex": plan.note_index,
                    "resourceIndex": plan.resource_index,
                    "mime": plan.mime,
                    "source": {
                        "fileName": plan.source_file_name,
                        "evernoteMd5": plan.source_hash,
                    },
                    "output": {
                        "relativePath": plan.relative_path,
                        "sha256": plan.sha256,
                        "sizeBytes": plan.size_bytes,
                    },
                    "duplicateOf": plan.duplicate_of,
                }
            )

        # Re-hash the source before finalizing evidence so a concurrent source edit cannot
        # silently produce an evidence set tied to bytes that are no longer present.
        _source_bytes_if_unchanged(report)

        evidence: dict[str, Any] = {
            "format": "goreecloud-notes-enex-resource-evidence",
            "schemaVersion": 1,
            "source": {
                "provider": "evernote",
                "format": "enex",
                "sha256": report.source_sha256,
                "sizeBytes": report.source_size_bytes,
            },
            "inspection": {
                "metadataValid": report.metadata_valid,
                "warningCount": report.warning_count,
                "issues": report.to_dict()["issues"],
            },
            "extraction": {
                "complete": True,
                "resourceCount": len(resources),
                "extractedBytes": total_bytes,
                "evidenceFile": EVIDENCE_FILENAME,
                "sourceMutationPerformed": False,
                "targetDatabaseMutationPerformed": False,
                "outputOverwritePerformed": False,
            },
            "limits": {
                "maxEnexBytes": max_bytes,
                "maxResourceBytes": max_resource_bytes,
                "maxTotalExtractedBytes": max_total_bytes,
                "maxResources": max_resources,
            },
            "resources": resources,
        }

        evidence_payload = serialize_enex_resource_evidence(evidence).encode("utf-8")
        evidence_path = _contained_output_path(target, EVIDENCE_FILENAME)
        _exclusive_write(evidence_path, evidence_payload)
        written_sha256, written_size = _hash_file(evidence_path)
        if written_sha256 != hashlib.sha256(evidence_payload).hexdigest() or written_size != len(evidence_payload):
            raise OSError("ENEX resource evidence file failed post-write verification.")
        return evidence
    except Exception:
        if created_output:
            try:
                shutil.rmtree(target)
            except OSError as cleanup_exc:
                raise OSError(
                    f"ENEX extraction failed and cleanup of {target} also failed."
                ) from cleanup_exc
        raise
