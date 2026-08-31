"""Verified re-import of native GoreeCloud Notes portable library bundles.

This is the inverse of the native full-library exporter, not a generic merge feature. The
importer writes only into an explicitly selected empty account, preserves native UUIDs and
user-owned timestamps, restores verified attachment bytes into generated private storage
keys, preserves any embedded transitional migration provenance, and refuses identifier
collisions instead of guessing remaps that could break document attachment references.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO
from unicodedata import normalize
from uuid import UUID, uuid4

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .documents import (
    DOCUMENT_SCHEMA,
    SAFE_INLINE_IMAGE_MEDIA_TYPES,
    DocumentValidationError,
    attachment_image_ids,
    canonicalize_document,
)
from .migration.persistence import MigrationImport, MigrationNoteRecord
from .models import Attachment, Note, Notebook, NoteRevision, NoteTag, Tag, User
from .portability import (
    BUNDLE_FORMAT,
    BUNDLE_SCHEMA_VERSION,
    EXPORT_FORMAT,
    EXPORT_SCHEMA_VERSION,
    BundleVerification,
    ExportError,
    verify_export_bundle,
)

NATIVE_IMPORT_RESULT_FORMAT = "goreecloud-notes-native-import-result"
NATIVE_IMPORT_RESULT_SCHEMA_VERSION = 1
_COPY_BUFFER_BYTES = 1024 * 1024
_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_LIBRARY_PATH = "library.json"
_BUNDLE_PATH = "bundle.json"


class NativeImportError(ValueError):
    """Raised when a native portable bundle or target state is unsafe for re-import."""


@dataclass(frozen=True, slots=True)
class NativeImportPlan:
    """Fully validated read-only import plan tied to one exact source bundle hash."""

    path: Path
    verification: BundleVerification
    library: dict[str, Any]
    source_account_id: UUID
    source_username: str
    notebooks: tuple[dict[str, Any], ...]
    notes: tuple[dict[str, Any], ...]
    tags: tuple[dict[str, Any], ...]
    note_tags: tuple[dict[str, Any], ...]
    attachments: tuple[dict[str, Any], ...]
    revisions: tuple[dict[str, Any], ...]
    migration_imports: tuple[dict[str, Any], ...]
    migration_records: tuple[dict[str, Any], ...]


@dataclass(frozen=True, slots=True)
class _StagedAttachment:
    attachment_id: UUID
    note_id: UUID
    temporary_path: Path
    final_path: Path
    archive_path: str


def _canonical_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise NativeImportError("Portable library contains non-canonical JSON data.") from exc


def _hash_stream(handle: BinaryIO) -> tuple[str, int]:
    digest = hashlib.sha256()
    size_bytes = 0
    while chunk := handle.read(_COPY_BUFFER_BYTES):
        digest.update(chunk)
        size_bytes += len(chunk)
    return digest.hexdigest(), size_bytes


def _hash_file(path: Path) -> tuple[str, int]:
    try:
        with path.open("rb") as handle:
            return _hash_stream(handle)
    except OSError as exc:
        raise NativeImportError("Portable bundle became unreadable during native import.") from exc


def _parse_uuid(value: object, *, field: str) -> UUID:
    if not isinstance(value, str) or not value:
        raise NativeImportError(f"{field} must contain a UUID string.")
    try:
        return UUID(value)
    except ValueError as exc:
        raise NativeImportError(f"{field} contains an invalid UUID.") from exc


def _parse_timestamp(value: object, *, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise NativeImportError(f"{field} must contain an ISO-8601 timestamp.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise NativeImportError(f"{field} is not a valid ISO-8601 timestamp.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise NativeImportError(f"{field} must contain timezone information.")
    return parsed.astimezone(UTC)


def _require_string(
    value: object,
    *,
    field: str,
    max_length: int,
    allow_empty: bool = False,
) -> str:
    if not isinstance(value, str):
        raise NativeImportError(f"{field} must be a string.")
    if (not allow_empty and not value) or len(value) > max_length:
        lower = 0 if allow_empty else 1
        raise NativeImportError(f"{field} must contain {lower} to {max_length} characters.")
    if "\x00" in value:
        raise NativeImportError(f"{field} contains a null byte.")
    return value


def _require_sha256(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise NativeImportError(f"{field} must contain a lowercase SHA-256 digest.")
    return value


def _require_int(value: object, *, field: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise NativeImportError(f"{field} must be an integer greater than or equal to {minimum}.")
    return value


def _require_bool(value: object, *, field: str) -> bool:
    if type(value) is not bool:
        raise NativeImportError(f"{field} must be boolean.")
    return value


def _require_object(value: object, *, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise NativeImportError(f"{field} must be an object.")
    return value


def _require_collection(value: object, *, field: str) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, list):
        raise NativeImportError(f"{field} must be an array.")
    result: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise NativeImportError(f"{field}[{index}] must be an object.")
        result.append(item)
    return tuple(result)


def _validate_color(value: object, *, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not _HEX_COLOR.fullmatch(value):
        raise NativeImportError(f"{field} must be null or a six-digit hexadecimal color.")
    return value.lower()


def _normalized_name(value: str) -> str:
    return " ".join(normalize("NFKC", value).strip().split()).casefold()


def _safe_filename(value: object) -> str:
    filename = _require_string(value, field="attachment.filename", max_length=512)
    if Path(filename).name != filename or "/" in filename or "\\" in filename or filename in {".", ".."}:
        raise NativeImportError("attachment.filename contains a path component.")
    return filename


def _safe_archive_path(value: object, *, field: str) -> str:
    raw = _require_string(value, field=field, max_length=2048)
    path = PurePosixPath(raw)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise NativeImportError(f"{field} contains an unsafe archive path.")
    return path.as_posix()


def _validate_document(value: object, *, field: str) -> dict[str, object]:
    try:
        return canonicalize_document(value)
    except DocumentValidationError as exc:
        raise NativeImportError(f"{field} is not valid for the current native document contract: {exc}") from exc


def _read_library(path: Path) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(path, mode="r") as archive:
            payload = json.loads(archive.read(_LIBRARY_PATH))
    except (OSError, KeyError, zipfile.BadZipFile, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NativeImportError("Verified portable bundle no longer contains readable library.json.") from exc
    if not isinstance(payload, dict):
        raise NativeImportError("Portable library root must be an object.")
    return payload


def _validate_notebook_cycles(notebooks: tuple[dict[str, Any], ...]) -> None:
    parent_by_id: dict[UUID, UUID | None] = {
        item["_id"]: item["_parent_id"] for item in notebooks
    }
    for notebook_id in parent_by_id:
        seen: set[UUID] = set()
        current: UUID | None = notebook_id
        while current is not None:
            if current in seen:
                raise NativeImportError("Portable notebook hierarchy contains a cycle.")
            seen.add(current)
            current = parent_by_id.get(current)


def _validate_library_payload(
    library: dict[str, Any],
    *,
    path: Path,
    verification: BundleVerification,
) -> NativeImportPlan:
    if library.get("format") != EXPORT_FORMAT or library.get("schemaVersion") != EXPORT_SCHEMA_VERSION:
        raise NativeImportError("Portable library format or schema version is unsupported.")

    source = _require_object(library.get("source"), field="source")
    if source.get("application") != "GoreeCloud Notes" or source.get("dataModel") != "native":
        raise NativeImportError("Portable library does not identify native GoreeCloud Notes data.")
    if source.get("sourceMutationPerformed") is not False:
        raise NativeImportError("Portable library source-mutation boundary is invalid.")
    _parse_timestamp(library.get("exportedAt"), field="exportedAt")

    account = _require_object(library.get("account"), field="account")
    source_account_id = _parse_uuid(account.get("id"), field="account.id")
    source_username = _require_string(account.get("username"), field="account.username", max_length=64)
    _require_string(account.get("displayName"), field="account.displayName", max_length=120)
    _parse_timestamp(account.get("createdAt"), field="account.createdAt")
    _parse_timestamp(account.get("updatedAt"), field="account.updatedAt")

    summary = _require_object(library.get("summary"), field="summary")
    raw_notebooks = _require_collection(library.get("notebooks"), field="notebooks")
    raw_notes = _require_collection(library.get("notes"), field="notes")
    raw_tags = _require_collection(library.get("tags"), field="tags")
    raw_note_tags = _require_collection(library.get("noteTags"), field="noteTags")
    raw_attachments = _require_collection(library.get("attachments"), field="attachments")
    raw_revisions = _require_collection(library.get("revisions"), field="revisions")
    raw_migration_imports = _require_collection(library.get("migrationImports", []), field="migrationImports")
    raw_migration_records = _require_collection(
        library.get("migrationNoteRecords", []), field="migrationNoteRecords"
    )

    expected_counts = {
        "notebooks": len(raw_notebooks),
        "notes": len(raw_notes),
        "tags": len(raw_tags),
        "noteTagRelationships": len(raw_note_tags),
        "attachments": len(raw_attachments),
        "revisions": len(raw_revisions),
    }
    for key, expected in expected_counts.items():
        if summary.get(key) != expected:
            raise NativeImportError(f"Portable library summary count for {key} does not match its collection.")
    if "migrationImports" in summary and summary.get("migrationImports") != len(raw_migration_imports):
        raise NativeImportError("Portable library migration import count does not match its collection.")
    if "migrationNoteRecords" in summary and summary.get("migrationNoteRecords") != len(raw_migration_records):
        raise NativeImportError("Portable library migration provenance count does not match its collection.")
    if verification.note_count != len(raw_notes) or verification.attachment_count != len(raw_attachments):
        raise NativeImportError("Portable bundle verification counts disagree with library.json.")

    notebooks: list[dict[str, Any]] = []
    notebook_ids: set[UUID] = set()
    for index, raw in enumerate(raw_notebooks):
        notebook_id = _parse_uuid(raw.get("id"), field=f"notebooks[{index}].id")
        if notebook_id in notebook_ids:
            raise NativeImportError("Portable library contains a duplicate notebook identifier.")
        notebook_ids.add(notebook_id)
        parent_id = None if raw.get("parentId") is None else _parse_uuid(
            raw.get("parentId"), field=f"notebooks[{index}].parentId"
        )
        notebooks.append(
            {
                **raw,
                "_id": notebook_id,
                "_parent_id": parent_id,
                "_name": _require_string(raw.get("name"), field=f"notebooks[{index}].name", max_length=255),
                "_sort_order": _require_int(raw.get("sortOrder"), field=f"notebooks[{index}].sortOrder", minimum=-(2**31)),
                "_created_at": _parse_timestamp(raw.get("createdAt"), field=f"notebooks[{index}].createdAt"),
                "_updated_at": _parse_timestamp(raw.get("updatedAt"), field=f"notebooks[{index}].updatedAt"),
            }
        )
    for item in notebooks:
        if item["_parent_id"] is not None and item["_parent_id"] not in notebook_ids:
            raise NativeImportError("Portable notebook references a parent outside the library.")
        if item["_parent_id"] == item["_id"]:
            raise NativeImportError("Portable notebook cannot be its own parent.")
    notebook_tuple = tuple(notebooks)
    _validate_notebook_cycles(notebook_tuple)

    notes: list[dict[str, Any]] = []
    note_ids: set[UUID] = set()
    for index, raw in enumerate(raw_notes):
        note_id = _parse_uuid(raw.get("id"), field=f"notes[{index}].id")
        if note_id in note_ids:
            raise NativeImportError("Portable library contains a duplicate note identifier.")
        note_ids.add(note_id)
        notebook_id = None if raw.get("notebookId") is None else _parse_uuid(
            raw.get("notebookId"), field=f"notes[{index}].notebookId"
        )
        if notebook_id is not None and notebook_id not in notebook_ids:
            raise NativeImportError("Portable note references a notebook outside the library.")
        document_schema = _require_int(raw.get("documentSchema"), field=f"notes[{index}].documentSchema", minimum=1)
        if document_schema != DOCUMENT_SCHEMA:
            raise NativeImportError("Portable note uses an unsupported native document schema.")
        state = raw.get("state")
        if state not in {"normal", "archived", "trashed"}:
            raise NativeImportError("Portable note contains an unsupported lifecycle state.")
        notes.append(
            {
                **raw,
                "_id": note_id,
                "_notebook_id": notebook_id,
                "_title": _require_string(raw.get("title"), field=f"notes[{index}].title", max_length=512, allow_empty=True),
                "_document": _validate_document(raw.get("document"), field=f"notes[{index}].document"),
                "_document_schema": document_schema,
                "_content_version": _require_int(raw.get("contentVersion"), field=f"notes[{index}].contentVersion", minimum=1),
                "_state": state,
                "_is_pinned": _require_bool(raw.get("isPinned"), field=f"notes[{index}].isPinned"),
                "_color": _validate_color(raw.get("color"), field=f"notes[{index}].color"),
                "_created_at": _parse_timestamp(raw.get("createdAt"), field=f"notes[{index}].createdAt"),
                "_updated_at": _parse_timestamp(raw.get("updatedAt"), field=f"notes[{index}].updatedAt"),
            }
        )

    tags: list[dict[str, Any]] = []
    tag_ids: set[UUID] = set()
    normalized_tags: set[str] = set()
    for index, raw in enumerate(raw_tags):
        tag_id = _parse_uuid(raw.get("id"), field=f"tags[{index}].id")
        if tag_id in tag_ids:
            raise NativeImportError("Portable library contains a duplicate tag identifier.")
        tag_ids.add(tag_id)
        name = _require_string(raw.get("name"), field=f"tags[{index}].name", max_length=128)
        normalized_name = _require_string(
            raw.get("normalizedName"), field=f"tags[{index}].normalizedName", max_length=128
        )
        if normalized_name != _normalized_name(name):
            raise NativeImportError("Portable tag normalized name disagrees with its display name.")
        if normalized_name in normalized_tags:
            raise NativeImportError("Portable library contains duplicate normalized tag names.")
        normalized_tags.add(normalized_name)
        tags.append(
            {
                **raw,
                "_id": tag_id,
                "_name": name,
                "_normalized_name": normalized_name,
                "_color": _validate_color(raw.get("color"), field=f"tags[{index}].color"),
                "_created_at": _parse_timestamp(raw.get("createdAt"), field=f"tags[{index}].createdAt"),
                "_updated_at": _parse_timestamp(raw.get("updatedAt"), field=f"tags[{index}].updatedAt"),
            }
        )

    note_tags: list[dict[str, Any]] = []
    note_tag_pairs: set[tuple[UUID, UUID]] = set()
    for index, raw in enumerate(raw_note_tags):
        note_id = _parse_uuid(raw.get("noteId"), field=f"noteTags[{index}].noteId")
        tag_id = _parse_uuid(raw.get("tagId"), field=f"noteTags[{index}].tagId")
        if note_id not in note_ids or tag_id not in tag_ids:
            raise NativeImportError("Portable note-tag relationship references data outside the library.")
        pair = (note_id, tag_id)
        if pair in note_tag_pairs:
            raise NativeImportError("Portable library contains a duplicate note-tag relationship.")
        note_tag_pairs.add(pair)
        note_tags.append(
            {
                **raw,
                "_note_id": note_id,
                "_tag_id": tag_id,
                "_created_at": _parse_timestamp(raw.get("createdAt"), field=f"noteTags[{index}].createdAt"),
            }
        )

    attachments: list[dict[str, Any]] = []
    attachment_ids: set[UUID] = set()
    attachment_ids_by_note: dict[UUID, set[UUID]] = {note_id: set() for note_id in note_ids}
    inline_safe_ids: set[UUID] = set()
    archive_paths: set[str] = set()
    for index, raw in enumerate(raw_attachments):
        attachment_id = _parse_uuid(raw.get("id"), field=f"attachments[{index}].id")
        note_id = _parse_uuid(raw.get("noteId"), field=f"attachments[{index}].noteId")
        if attachment_id in attachment_ids:
            raise NativeImportError("Portable library contains a duplicate attachment identifier.")
        if note_id not in note_ids:
            raise NativeImportError("Portable attachment references a note outside the library.")
        attachment_ids.add(attachment_id)
        attachment_ids_by_note[note_id].add(attachment_id)
        filename = _safe_filename(raw.get("filename"))
        media_type = _require_string(raw.get("mediaType"), field=f"attachments[{index}].mediaType", max_length=255)
        size_bytes = _require_int(raw.get("sizeBytes"), field=f"attachments[{index}].sizeBytes")
        sha256 = _require_sha256(raw.get("sha256"), field=f"attachments[{index}].sha256")
        archive_path = _safe_archive_path(raw.get("archivePath"), field=f"attachments[{index}].archivePath")
        expected_archive_path = f"attachments/{attachment_id}/{filename}"
        if archive_path != expected_archive_path:
            raise NativeImportError("Portable attachment archive path does not match its identifier and filename.")
        if archive_path in archive_paths:
            raise NativeImportError("Portable library contains a duplicate attachment archive path.")
        archive_paths.add(archive_path)
        extra_metadata = raw.get("extraMetadata")
        if not isinstance(extra_metadata, dict):
            raise NativeImportError("Portable attachment extraMetadata must be an object.")
        if media_type.casefold() in SAFE_INLINE_IMAGE_MEDIA_TYPES:
            inline_safe_ids.add(attachment_id)
        attachments.append(
            {
                **raw,
                "_id": attachment_id,
                "_note_id": note_id,
                "_filename": filename,
                "_media_type": media_type,
                "_size_bytes": size_bytes,
                "_sha256": sha256,
                "_archive_path": archive_path,
                "_extra_metadata": extra_metadata,
                "_created_at": _parse_timestamp(raw.get("createdAt"), field=f"attachments[{index}].createdAt"),
                "_updated_at": _parse_timestamp(raw.get("updatedAt"), field=f"attachments[{index}].updatedAt"),
            }
        )

    revisions: list[dict[str, Any]] = []
    revision_ids: set[UUID] = set()
    revision_numbers: set[tuple[UUID, int]] = set()
    revision_versions: set[tuple[UUID, int]] = set()
    note_versions = {item["_id"]: item["_content_version"] for item in notes}
    for index, raw in enumerate(raw_revisions):
        revision_id = _parse_uuid(raw.get("id"), field=f"revisions[{index}].id")
        note_id = _parse_uuid(raw.get("noteId"), field=f"revisions[{index}].noteId")
        if revision_id in revision_ids:
            raise NativeImportError("Portable library contains a duplicate revision identifier.")
        if note_id not in note_ids:
            raise NativeImportError("Portable revision references a note outside the library.")
        revision_ids.add(revision_id)
        revision_number = _require_int(raw.get("revisionNumber"), field=f"revisions[{index}].revisionNumber", minimum=1)
        content_version = _require_int(raw.get("contentVersion"), field=f"revisions[{index}].contentVersion", minimum=1)
        if content_version >= note_versions[note_id]:
            raise NativeImportError("Portable revision content version must precede the current note version.")
        if (note_id, revision_number) in revision_numbers or (note_id, content_version) in revision_versions:
            raise NativeImportError("Portable library contains duplicate revision ordering metadata.")
        revision_numbers.add((note_id, revision_number))
        revision_versions.add((note_id, content_version))
        document_schema = _require_int(raw.get("documentSchema"), field=f"revisions[{index}].documentSchema", minimum=1)
        if document_schema != DOCUMENT_SCHEMA:
            raise NativeImportError("Portable revision uses an unsupported native document schema.")
        change_summary = raw.get("changeSummary")
        if change_summary is not None and not isinstance(change_summary, str):
            raise NativeImportError("Portable revision changeSummary must be a string or null.")
        revisions.append(
            {
                **raw,
                "_id": revision_id,
                "_note_id": note_id,
                "_revision_number": revision_number,
                "_content_version": content_version,
                "_title": _require_string(raw.get("title"), field=f"revisions[{index}].title", max_length=512, allow_empty=True),
                "_document": _validate_document(raw.get("document"), field=f"revisions[{index}].document"),
                "_document_schema": document_schema,
                "_created_at": _parse_timestamp(raw.get("createdAt"), field=f"revisions[{index}].createdAt"),
                "_change_summary": change_summary,
            }
        )

    # Inline attachment nodes are durable references. A native re-import must not create a
    # document that points at a foreign note's attachment or a media type the renderer would
    # refuse to serve inline.
    for item in notes:
        referenced = attachment_image_ids(item["_document"])
        if not referenced.issubset(attachment_ids_by_note[item["_id"]]):
            raise NativeImportError("Portable note contains an inline attachment reference outside its own attachments.")
        if not referenced.issubset(inline_safe_ids):
            raise NativeImportError("Portable note contains an inline attachment with an unsafe media type.")
    for item in revisions:
        referenced = attachment_image_ids(item["_document"])
        if not referenced.issubset(attachment_ids_by_note[item["_note_id"]]):
            raise NativeImportError("Portable revision contains an inline attachment reference outside its note.")
        if not referenced.issubset(inline_safe_ids):
            raise NativeImportError("Portable revision contains an inline attachment with an unsafe media type.")

    migration_imports: list[dict[str, Any]] = []
    migration_import_ids: set[UUID] = set()
    for index, raw in enumerate(raw_migration_imports):
        import_id = _parse_uuid(raw.get("id"), field=f"migrationImports[{index}].id")
        if import_id in migration_import_ids:
            raise NativeImportError("Portable library contains a duplicate migration import identifier.")
        migration_import_ids.add(import_id)
        provider = _require_string(raw.get("provider"), field=f"migrationImports[{index}].provider", max_length=32)
        migration_imports.append(
            {
                **raw,
                "_id": import_id,
                "_provider": provider,
                "_source_export_sha256": _require_sha256(raw.get("sourceExportSha256"), field=f"migrationImports[{index}].sourceExportSha256"),
                "_manifest_sha256": _require_sha256(raw.get("manifestSha256"), field=f"migrationImports[{index}].manifestSha256"),
                "_evidence_sha256": _require_sha256(raw.get("evidenceSha256"), field=f"migrationImports[{index}].evidenceSha256"),
                "_source_exported_at": _parse_timestamp(raw.get("sourceExportedAt"), field=f"migrationImports[{index}].sourceExportedAt"),
                "_source_note_count": _require_int(raw.get("sourceNoteCount"), field=f"migrationImports[{index}].sourceNoteCount"),
                "_imported_note_count": _require_int(raw.get("importedNoteCount"), field=f"migrationImports[{index}].importedNoteCount"),
                "_conversion_profile": _require_string(raw.get("conversionProfile"), field=f"migrationImports[{index}].conversionProfile", max_length=64),
                "_created_at": _parse_timestamp(raw.get("createdAt"), field=f"migrationImports[{index}].createdAt"),
            }
        )

    migration_records: list[dict[str, Any]] = []
    migration_record_ids: set[UUID] = set()
    import_source_pairs: set[tuple[UUID, str]] = set()
    import_note_pairs: set[tuple[UUID, UUID]] = set()
    record_counts: dict[UUID, int] = {item["_id"]: 0 for item in migration_imports}
    for index, raw in enumerate(raw_migration_records):
        record_id = _parse_uuid(raw.get("id"), field=f"migrationNoteRecords[{index}].id")
        import_id = _parse_uuid(raw.get("importId"), field=f"migrationNoteRecords[{index}].importId")
        note_id = _parse_uuid(raw.get("noteId"), field=f"migrationNoteRecords[{index}].noteId")
        if record_id in migration_record_ids:
            raise NativeImportError("Portable library contains a duplicate migration provenance identifier.")
        if import_id not in migration_import_ids or note_id not in note_ids:
            raise NativeImportError("Portable migration provenance references data outside the library.")
        migration_record_ids.add(record_id)
        source_name = _require_string(raw.get("sourceName"), field=f"migrationNoteRecords[{index}].sourceName", max_length=512)
        source_uid = raw.get("sourceUid")
        if source_uid is not None:
            source_uid = _require_string(source_uid, field=f"migrationNoteRecords[{index}].sourceUid", max_length=255, allow_empty=True)
        source_order = _require_int(raw.get("sourceOrder"), field=f"migrationNoteRecords[{index}].sourceOrder")
        record_sha = _require_sha256(raw.get("recordSha256"), field=f"migrationNoteRecords[{index}].recordSha256")
        source_record = _require_object(raw.get("sourceRecord"), field=f"migrationNoteRecords[{index}].sourceRecord")
        unsigned = dict(source_record)
        embedded_sha = unsigned.pop("recordSha256", None)
        computed_sha = hashlib.sha256(_canonical_json_bytes(unsigned)).hexdigest()
        if embedded_sha != record_sha or computed_sha != record_sha:
            raise NativeImportError("Portable migration source record failed SHA-256 validation.")
        if (import_id, source_name) in import_source_pairs or (import_id, note_id) in import_note_pairs:
            raise NativeImportError("Portable migration provenance violates unique source/note mapping.")
        import_source_pairs.add((import_id, source_name))
        import_note_pairs.add((import_id, note_id))
        record_counts[import_id] += 1
        migration_records.append(
            {
                **raw,
                "_id": record_id,
                "_import_id": import_id,
                "_note_id": note_id,
                "_source_name": source_name,
                "_source_uid": source_uid,
                "_source_order": source_order,
                "_record_sha256": record_sha,
                "_source_record": source_record,
                "_created_at": _parse_timestamp(raw.get("createdAt"), field=f"migrationNoteRecords[{index}].createdAt"),
            }
        )
    for item in migration_imports:
        expected = item["_imported_note_count"]
        if record_counts[item["_id"]] != expected or item["_source_note_count"] != expected:
            raise NativeImportError("Portable migration import counts disagree with preserved source records.")

    return NativeImportPlan(
        path=path,
        verification=verification,
        library=library,
        source_account_id=source_account_id,
        source_username=source_username,
        notebooks=notebook_tuple,
        notes=tuple(notes),
        tags=tuple(tags),
        note_tags=tuple(note_tags),
        attachments=tuple(attachments),
        revisions=tuple(revisions),
        migration_imports=tuple(migration_imports),
        migration_records=tuple(migration_records),
    )


def load_native_import_plan(path: Path) -> NativeImportPlan:
    """Verify one portable ZIP and fully validate native records without target mutation."""

    source = path.expanduser()
    try:
        source_stat = source.lstat()
    except OSError as exc:
        raise NativeImportError("Portable bundle is unavailable.") from exc
    if stat.S_ISLNK(source_stat.st_mode) or not stat.S_ISREG(source_stat.st_mode):
        raise NativeImportError("Portable bundle must be a regular file, not a symbolic link.")

    try:
        verification = verify_export_bundle(source)
    except ExportError as exc:
        raise NativeImportError(str(exc)) from exc
    library = _read_library(source)
    return _validate_library_payload(library, path=source.resolve(strict=True), verification=verification)


def _target_data_count(db: Session, *, owner_id: UUID) -> int:
    models = (Notebook, Note, Tag, NoteTag, Attachment, NoteRevision, MigrationImport, MigrationNoteRecord)
    return sum(
        int(db.scalar(select(func.count()).select_from(model).where(getattr(model, "owner_id") == owner_id)) or 0)
        for model in models
    )


def _safe_storage_path(root: Path, storage_key: str) -> Path:
    resolved_root = root.expanduser().resolve()
    candidate = (resolved_root / storage_key).resolve()
    try:
        candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise NativeImportError("Generated attachment storage key escaped the configured attachment root.") from exc
    return candidate


def _stage_attachments(plan: NativeImportPlan, *, attachment_root: Path) -> list[_StagedAttachment]:
    root = attachment_root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    staged: list[_StagedAttachment] = []
    try:
        with zipfile.ZipFile(plan.path, mode="r") as archive:
            for item in plan.attachments:
                storage_key = f"{item['_target_owner_id']}/{item['_note_id']}/{item['_id']}" if "_target_owner_id" in item else None
                # owner ID is injected only by the target-writing function below.
                if storage_key is None:
                    raise NativeImportError("Native import attachment staging is missing target ownership context.")
                final_path = _safe_storage_path(root, storage_key)
                if final_path.exists():
                    raise NativeImportError("Generated native attachment destination already exists; import refused.")
                temporary_path = final_path.with_name(f".{final_path.name}.{uuid4().hex}.part")
                temporary_path.parent.mkdir(parents=True, exist_ok=True)
                digest = hashlib.sha256()
                size_bytes = 0
                try:
                    with archive.open(item["_archive_path"], "r") as source, temporary_path.open("xb") as target:
                        while chunk := source.read(_COPY_BUFFER_BYTES):
                            size_bytes += len(chunk)
                            digest.update(chunk)
                            target.write(chunk)
                        target.flush()
                        os.fsync(target.fileno())
                except (OSError, KeyError) as exc:
                    temporary_path.unlink(missing_ok=True)
                    raise NativeImportError("Unable to stage verified native attachment bytes.") from exc
                if size_bytes != item["_size_bytes"] or digest.hexdigest() != item["_sha256"]:
                    temporary_path.unlink(missing_ok=True)
                    raise NativeImportError("Portable attachment changed while native import was staging bytes.")
                staged.append(
                    _StagedAttachment(
                        attachment_id=item["_id"],
                        note_id=item["_note_id"],
                        temporary_path=temporary_path,
                        final_path=final_path,
                        archive_path=item["_archive_path"],
                    )
                )
    except Exception:
        for item in staged:
            item.temporary_path.unlink(missing_ok=True)
        raise
    return staged


def _assert_no_id_collisions(db: Session, plan: NativeImportPlan) -> None:
    checks = (
        (Notebook, [item["_id"] for item in plan.notebooks], "notebook"),
        (Note, [item["_id"] for item in plan.notes], "note"),
        (Tag, [item["_id"] for item in plan.tags], "tag"),
        (Attachment, [item["_id"] for item in plan.attachments], "attachment"),
        (NoteRevision, [item["_id"] for item in plan.revisions], "revision"),
        (MigrationImport, [item["_id"] for item in plan.migration_imports], "migration import"),
        (MigrationNoteRecord, [item["_id"] for item in plan.migration_records], "migration provenance"),
    )
    for model, identifiers, label in checks:
        if not identifiers:
            continue
        collision = db.scalar(select(model.id).where(model.id.in_(identifiers)).limit(1))
        if collision is not None:
            raise NativeImportError(
                f"Portable {label} identifier already exists in the target database; re-import refuses UUID remapping."
            )


def _topological_notebooks(plan: NativeImportPlan) -> list[dict[str, Any]]:
    remaining = {item["_id"]: item for item in plan.notebooks}
    ordered: list[dict[str, Any]] = []
    inserted: set[UUID] = set()
    while remaining:
        ready = [
            item for item in remaining.values()
            if item["_parent_id"] is None or item["_parent_id"] in inserted
        ]
        if not ready:
            raise NativeImportError("Portable notebook hierarchy could not be ordered safely.")
        ready.sort(key=lambda item: (item["_sort_order"], item["_name"], str(item["_id"])))
        for item in ready:
            ordered.append(item)
            inserted.add(item["_id"])
            remaining.pop(item["_id"])
    return ordered


def import_native_library(
    db: Session,
    *,
    owner: User,
    input_path: Path,
    attachment_root: Path,
) -> dict[str, Any]:
    """Restore one verified native library into an explicitly empty existing account.

    The portable artifact is fully verified and attachment bytes are staged before the target
    write lock is acquired. The database tables are then briefly write-locked, target emptiness
    and global UUID collisions are rechecked under that lock, rows are inserted in deterministic
    parent-before-child order, staged bytes are atomically moved into generated target-owned
    paths, and the transaction commits. A caught failure rolls back rows and removes newly
    created files. A process/power loss at the final rename/commit boundary can leave
    unreferenced bytes but will not commit metadata that points at bytes that were never staged.
    """

    if _target_data_count(db, owner_id=owner.id) != 0:
        raise NativeImportError(
            "Target account is not empty; native re-import was refused to prevent duplication or merging."
        )

    plan = load_native_import_plan(input_path)

    # Inject the selected target owner only into ephemeral in-memory records used for generated
    # filesystem locations. Account credentials/identity are never read from the bundle as
    # target authority.
    for item in plan.attachments:
        item["_target_owner_id"] = owner.id

    staged = _stage_attachments(plan, attachment_root=attachment_root)
    finalized_paths: list[Path] = []
    try:
        current_sha256, current_size = _hash_file(plan.path)
        if current_sha256 != plan.verification.sha256 or current_size != plan.verification.size_bytes:
            raise NativeImportError("Portable bundle changed after verification; import was refused.")

        # Keep the write lock short: expensive ZIP verification and byte staging are complete.
        # SHARE ROW EXCLUSIVE blocks concurrent INSERT/UPDATE/DELETE writers on these tables
        # while still allowing ordinary readers. The lock prevents the target from becoming
        # non-empty between the final emptiness check and commit.
        db.execute(
            text(
                "LOCK TABLE notebooks, notes, tags, note_tags, attachments, note_revisions, "
                "migration_imports, migration_note_records IN SHARE ROW EXCLUSIVE MODE"
            )
        )
        if _target_data_count(db, owner_id=owner.id) != 0:
            raise NativeImportError(
                "Target account became non-empty while import inputs were being staged; native re-import was refused."
            )
        _assert_no_id_collisions(db, plan)

        for item in _topological_notebooks(plan):
            row = Notebook(
                id=item["_id"],
                owner_id=owner.id,
                parent_id=item["_parent_id"],
                name=item["_name"],
                sort_order=item["_sort_order"],
                created_at=item["_created_at"],
                updated_at=item["_updated_at"],
            )
            db.add(row)
            db.flush([row])

        for item in plan.tags:
            row = Tag(
                id=item["_id"],
                owner_id=owner.id,
                name=item["_name"],
                normalized_name=item["_normalized_name"],
                color=item["_color"],
                created_at=item["_created_at"],
                updated_at=item["_updated_at"],
            )
            db.add(row)
            db.flush([row])

        for item in plan.notes:
            row = Note(
                id=item["_id"],
                owner_id=owner.id,
                notebook_id=item["_notebook_id"],
                title=item["_title"],
                document=item["_document"],
                document_schema=item["_document_schema"],
                content_version=item["_content_version"],
                state=item["_state"],
                is_pinned=item["_is_pinned"],
                color=item["_color"],
                created_at=item["_created_at"],
                updated_at=item["_updated_at"],
            )
            db.add(row)
            db.flush([row])

        for item in plan.migration_imports:
            row = MigrationImport(
                id=item["_id"],
                owner_id=owner.id,
                provider=item["_provider"],
                source_export_sha256=item["_source_export_sha256"],
                manifest_sha256=item["_manifest_sha256"],
                evidence_sha256=item["_evidence_sha256"],
                source_exported_at=item["_source_exported_at"],
                source_note_count=item["_source_note_count"],
                imported_note_count=item["_imported_note_count"],
                conversion_profile=item["_conversion_profile"],
                created_at=item["_created_at"],
            )
            db.add(row)
            db.flush([row])

        for item in plan.note_tags:
            db.add(
                NoteTag(
                    owner_id=owner.id,
                    note_id=item["_note_id"],
                    tag_id=item["_tag_id"],
                    created_at=item["_created_at"],
                )
            )

        for item in plan.revisions:
            db.add(
                NoteRevision(
                    id=item["_id"],
                    owner_id=owner.id,
                    note_id=item["_note_id"],
                    revision_number=item["_revision_number"],
                    content_version=item["_content_version"],
                    title=item["_title"],
                    document=item["_document"],
                    document_schema=item["_document_schema"],
                    created_at=item["_created_at"],
                    change_summary=item["_change_summary"],
                )
            )

        staged_by_id = {item.attachment_id: item for item in staged}
        for item in plan.attachments:
            staged_item = staged_by_id[item["_id"]]
            storage_key = f"{owner.id}/{item['_note_id']}/{item['_id']}"
            db.add(
                Attachment(
                    id=item["_id"],
                    owner_id=owner.id,
                    note_id=item["_note_id"],
                    filename=item["_filename"],
                    media_type=item["_media_type"],
                    size_bytes=item["_size_bytes"],
                    sha256=item["_sha256"],
                    storage_key=storage_key,
                    extra_metadata=item["_extra_metadata"],
                    created_at=item["_created_at"],
                    updated_at=item["_updated_at"],
                )
            )
            if staged_item.final_path != _safe_storage_path(attachment_root, storage_key):
                raise NativeImportError("Staged attachment destination disagrees with generated storage key.")

        for item in plan.migration_records:
            db.add(
                MigrationNoteRecord(
                    id=item["_id"],
                    import_id=item["_import_id"],
                    owner_id=owner.id,
                    note_id=item["_note_id"],
                    source_name=item["_source_name"],
                    source_uid=item["_source_uid"],
                    source_order=item["_source_order"],
                    record_sha256=item["_record_sha256"],
                    source_record=item["_source_record"],
                    created_at=item["_created_at"],
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
    finally:
        for item in plan.attachments:
            item.pop("_target_owner_id", None)

    return {
        "format": NATIVE_IMPORT_RESULT_FORMAT,
        "schemaVersion": NATIVE_IMPORT_RESULT_SCHEMA_VERSION,
        "source": {
            "bundleSha256": plan.verification.sha256,
            "bundleSizeBytes": plan.verification.size_bytes,
            "accountId": str(plan.source_account_id),
            "username": plan.source_username,
        },
        "target": {
            "accountId": str(owner.id),
            "username": owner.username,
        },
        "counts": {
            "notebooks": len(plan.notebooks),
            "notes": len(plan.notes),
            "tags": len(plan.tags),
            "noteTagRelationships": len(plan.note_tags),
            "attachments": len(plan.attachments),
            "revisions": len(plan.revisions),
            "migrationImports": len(plan.migration_imports),
            "migrationNoteRecords": len(plan.migration_records),
        },
        "identity": {
            "nativeObjectUuidsPreserved": True,
            "targetAccountCredentialImported": False,
            "sourceAccountCredentialPresentInBundle": False,
        },
        "validation": {
            "bundleVerifiedBeforeMutation": True,
            "bundleStableThroughAttachmentStaging": True,
            "attachmentBytesRehashedWhileStaging": True,
            "targetWasEmptyAtCommitBoundary": True,
            "uuidCollisionsRefused": True,
            "sourceMutationPerformed": False,
            "targetMutationPerformed": True,
        },
    }
