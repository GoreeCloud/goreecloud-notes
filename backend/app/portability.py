"""Portable full-library export for native GoreeCloud Notes.

The export bundle is deliberately independent from PostgreSQL storage layout and the
private attachment filesystem layout. It preserves user-owned knowledge data and the
attachment bytes required to reconstruct that knowledge without exporting credentials,
opaque browser sessions, login-abuse state, or derived search indexes.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import BinaryIO
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Attachment, Note, Notebook, NoteRevision, NoteTag, Tag, User

EXPORT_FORMAT = "goreecloud-notes-native-export"
EXPORT_SCHEMA_VERSION = 1
BUNDLE_FORMAT = "goreecloud-notes-native-export-bundle"
BUNDLE_SCHEMA_VERSION = 1
_LIBRARY_PATH = "library.json"
_BUNDLE_PATH = "bundle.json"
_COPY_BUFFER_BYTES = 1024 * 1024


class ExportError(ValueError):
    """Raised when a portable export cannot be created or verified safely."""


@dataclass(frozen=True, slots=True)
class LibrarySnapshot:
    """One owner-scoped, read-only application snapshot prepared for export."""

    owner: User
    notebooks: tuple[Notebook, ...]
    notes: tuple[Note, ...]
    tags: tuple[Tag, ...]
    note_tags: tuple[NoteTag, ...]
    attachments: tuple[Attachment, ...]
    revisions: tuple[NoteRevision, ...]


@dataclass(frozen=True, slots=True)
class ExportResult:
    """Integrity summary for one successfully created portable bundle."""

    output_path: Path
    sha256: str
    size_bytes: int
    note_count: int
    attachment_count: int


@dataclass(frozen=True, slots=True)
class BundleVerification:
    """Integrity summary returned after validating an existing export bundle."""

    path: Path
    sha256: str
    size_bytes: int
    note_count: int
    attachment_count: int


def _require_aware_datetime(value: datetime, *, field: str) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ExportError(f"{field} must contain timezone information.")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


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
        raise ExportError("Export data contains a value that cannot be represented safely as JSON.") from exc


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
        raise ExportError(f"Unable to read export input: {path.name}") from exc


def _safe_filename(value: str) -> str:
    if not value or len(value) > 512:
        raise ExportError("Attachment filename is invalid.")
    if Path(value).name != value or "/" in value or "\\" in value or value in {".", ".."}:
        raise ExportError("Attachment filename contains a path component.")
    if "\x00" in value:
        raise ExportError("Attachment filename contains an invalid null byte.")
    return value


def _safe_attachment_path(root: Path, storage_key: str) -> Path:
    if not storage_key or "\x00" in storage_key:
        raise ExportError("Attachment storage key is invalid.")

    raw_key = Path(storage_key)
    if raw_key.is_absolute():
        raise ExportError("Attachment storage key must remain relative to the attachment root.")

    resolved_root = root.expanduser().resolve()
    candidate = (resolved_root / raw_key).resolve()
    try:
        candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise ExportError("Attachment storage key escapes the configured attachment root.") from exc

    if not candidate.is_file():
        raise ExportError("Attachment bytes are unavailable for a required export record.")
    return candidate


def _safe_archive_path(value: str) -> str:
    path = PurePosixPath(value)
    if path.is_absolute() or not value or any(part in {"", ".", ".."} for part in path.parts):
        raise ExportError("Export bundle contains an unsafe archive member path.")
    return path.as_posix()


def _attachment_archive_path(attachment: Attachment) -> str:
    filename = _safe_filename(attachment.filename)
    return f"attachments/{attachment.id}/{filename}"


def load_library_snapshot(db: Session, *, owner: User) -> LibrarySnapshot:
    """Load one complete owner-scoped knowledge snapshot without mutating source data."""

    owner_id = owner.id
    notebooks = tuple(
        db.scalars(
            select(Notebook)
            .where(Notebook.owner_id == owner_id)
            .order_by(Notebook.sort_order.asc(), Notebook.name.asc(), Notebook.id.asc())
        )
    )
    notes = tuple(
        db.scalars(
            select(Note)
            .where(Note.owner_id == owner_id)
            .order_by(Note.created_at.asc(), Note.id.asc())
        )
    )
    tags = tuple(
        db.scalars(
            select(Tag)
            .where(Tag.owner_id == owner_id)
            .order_by(Tag.normalized_name.asc(), Tag.id.asc())
        )
    )
    note_tags = tuple(
        db.scalars(
            select(NoteTag)
            .where(NoteTag.owner_id == owner_id)
            .order_by(NoteTag.note_id.asc(), NoteTag.tag_id.asc())
        )
    )
    attachments = tuple(
        db.scalars(
            select(Attachment)
            .where(Attachment.owner_id == owner_id)
            .order_by(Attachment.note_id.asc(), Attachment.created_at.asc(), Attachment.id.asc())
        )
    )
    revisions = tuple(
        db.scalars(
            select(NoteRevision)
            .where(NoteRevision.owner_id == owner_id)
            .order_by(NoteRevision.note_id.asc(), NoteRevision.revision_number.asc())
        )
    )
    return LibrarySnapshot(
        owner=owner,
        notebooks=notebooks,
        notes=notes,
        tags=tags,
        note_tags=note_tags,
        attachments=attachments,
        revisions=revisions,
    )


def _validate_snapshot_relationships(snapshot: LibrarySnapshot) -> None:
    owner_id = snapshot.owner.id
    notebook_ids = {item.id for item in snapshot.notebooks}
    note_ids = {item.id for item in snapshot.notes}
    tag_ids = {item.id for item in snapshot.tags}

    for notebook in snapshot.notebooks:
        if notebook.owner_id != owner_id:
            raise ExportError("Notebook ownership escaped the requested export scope.")
        if notebook.parent_id is not None and notebook.parent_id not in notebook_ids:
            raise ExportError("Notebook hierarchy contains an unresolved parent reference.")

    for note in snapshot.notes:
        if note.owner_id != owner_id:
            raise ExportError("Note ownership escaped the requested export scope.")
        if note.notebook_id is not None and note.notebook_id not in notebook_ids:
            raise ExportError("Note contains an unresolved notebook reference.")

    for tag in snapshot.tags:
        if tag.owner_id != owner_id:
            raise ExportError("Tag ownership escaped the requested export scope.")

    for relationship in snapshot.note_tags:
        if relationship.owner_id != owner_id:
            raise ExportError("Note-tag ownership escaped the requested export scope.")
        if relationship.note_id not in note_ids or relationship.tag_id not in tag_ids:
            raise ExportError("Note-tag relationship contains an unresolved reference.")

    for attachment in snapshot.attachments:
        if attachment.owner_id != owner_id or attachment.note_id not in note_ids:
            raise ExportError("Attachment relationship escaped the requested export scope.")

    for revision in snapshot.revisions:
        if revision.owner_id != owner_id or revision.note_id not in note_ids:
            raise ExportError("Revision relationship escaped the requested export scope.")


def _attachment_evidence(snapshot: LibrarySnapshot, *, attachment_root: Path) -> list[dict[str, object]]:
    evidence: list[dict[str, object]] = []
    seen_archive_paths: set[str] = set()

    for attachment in snapshot.attachments:
        path = _safe_attachment_path(attachment_root, attachment.storage_key)
        archive_path = _safe_archive_path(_attachment_archive_path(attachment))
        if archive_path in seen_archive_paths:
            raise ExportError("Two attachments resolved to the same export archive path.")
        seen_archive_paths.add(archive_path)

        sha256, size_bytes = _hash_file(path)
        if size_bytes != attachment.size_bytes:
            raise ExportError("Attachment byte size does not match stored metadata.")
        if sha256 != attachment.sha256:
            raise ExportError("Attachment SHA-256 does not match stored metadata.")

        evidence.append(
            {
                "id": str(attachment.id),
                "noteId": str(attachment.note_id),
                "filename": attachment.filename,
                "mediaType": attachment.media_type,
                "sizeBytes": size_bytes,
                "sha256": sha256,
                "archivePath": archive_path,
                "sourcePath": path,
            }
        )
    return evidence


def _build_library_payload(
    snapshot: LibrarySnapshot,
    *,
    exported_at: datetime,
    attachment_evidence: list[dict[str, object]],
) -> dict[str, object]:
    _validate_snapshot_relationships(snapshot)
    attachment_by_id = {UUID(str(item["id"])): item for item in attachment_evidence}

    return {
        "format": EXPORT_FORMAT,
        "schemaVersion": EXPORT_SCHEMA_VERSION,
        "exportedAt": _require_aware_datetime(exported_at, field="exportedAt"),
        "source": {
            "application": "GoreeCloud Notes",
            "dataModel": "native",
            "sourceMutationPerformed": False,
        },
        "account": {
            "id": str(snapshot.owner.id),
            "username": snapshot.owner.username,
            "displayName": snapshot.owner.display_name,
            "createdAt": _require_aware_datetime(snapshot.owner.created_at, field="account.createdAt"),
            "updatedAt": _require_aware_datetime(snapshot.owner.updated_at, field="account.updatedAt"),
        },
        "summary": {
            "notebooks": len(snapshot.notebooks),
            "notes": len(snapshot.notes),
            "tags": len(snapshot.tags),
            "noteTagRelationships": len(snapshot.note_tags),
            "attachments": len(snapshot.attachments),
            "revisions": len(snapshot.revisions),
        },
        "notebooks": [
            {
                "id": str(item.id),
                "parentId": str(item.parent_id) if item.parent_id else None,
                "name": item.name,
                "sortOrder": item.sort_order,
                "createdAt": _require_aware_datetime(item.created_at, field="notebook.createdAt"),
                "updatedAt": _require_aware_datetime(item.updated_at, field="notebook.updatedAt"),
            }
            for item in snapshot.notebooks
        ],
        "notes": [
            {
                "id": str(item.id),
                "notebookId": str(item.notebook_id) if item.notebook_id else None,
                "title": item.title,
                "document": item.document,
                "documentSchema": item.document_schema,
                "contentVersion": item.content_version,
                "state": item.state,
                "isPinned": item.is_pinned,
                "color": item.color,
                "createdAt": _require_aware_datetime(item.created_at, field="note.createdAt"),
                "updatedAt": _require_aware_datetime(item.updated_at, field="note.updatedAt"),
            }
            for item in snapshot.notes
        ],
        "tags": [
            {
                "id": str(item.id),
                "name": item.name,
                "normalizedName": item.normalized_name,
                "color": item.color,
                "createdAt": _require_aware_datetime(item.created_at, field="tag.createdAt"),
                "updatedAt": _require_aware_datetime(item.updated_at, field="tag.updatedAt"),
            }
            for item in snapshot.tags
        ],
        "noteTags": [
            {
                "noteId": str(item.note_id),
                "tagId": str(item.tag_id),
                "createdAt": _require_aware_datetime(item.created_at, field="noteTag.createdAt"),
            }
            for item in snapshot.note_tags
        ],
        "attachments": [
            {
                "id": str(item.id),
                "noteId": str(item.note_id),
                "filename": item.filename,
                "mediaType": item.media_type,
                "sizeBytes": item.size_bytes,
                "sha256": item.sha256,
                "archivePath": str(attachment_by_id[item.id]["archivePath"]),
                "extraMetadata": item.extra_metadata,
                "createdAt": _require_aware_datetime(item.created_at, field="attachment.createdAt"),
                "updatedAt": _require_aware_datetime(item.updated_at, field="attachment.updatedAt"),
            }
            for item in snapshot.attachments
        ],
        "revisions": [
            {
                "id": str(item.id),
                "noteId": str(item.note_id),
                "revisionNumber": item.revision_number,
                "contentVersion": item.content_version,
                "title": item.title,
                "document": item.document,
                "documentSchema": item.document_schema,
                "createdAt": _require_aware_datetime(item.created_at, field="revision.createdAt"),
                "changeSummary": item.change_summary,
            }
            for item in snapshot.revisions
        ],
    }


def _zip_info(path: str, *, exported_at: datetime, compress_type: int) -> zipfile.ZipInfo:
    timestamp = exported_at.astimezone(UTC)
    year = max(timestamp.year, 1980)
    info = zipfile.ZipInfo(
        filename=path,
        date_time=(year, timestamp.month, timestamp.day, timestamp.hour, timestamp.minute, timestamp.second),
    )
    info.compress_type = compress_type
    info.external_attr = 0o600 << 16
    return info


def _write_bytes(
    archive: zipfile.ZipFile,
    *,
    archive_path: str,
    payload: bytes,
    exported_at: datetime,
) -> None:
    archive.writestr(
        _zip_info(archive_path, exported_at=exported_at, compress_type=zipfile.ZIP_DEFLATED),
        payload,
    )


def _write_file(
    archive: zipfile.ZipFile,
    *,
    archive_path: str,
    source_path: Path,
    exported_at: datetime,
) -> None:
    info = _zip_info(archive_path, exported_at=exported_at, compress_type=zipfile.ZIP_STORED)
    try:
        with source_path.open("rb") as source, archive.open(info, "w") as target:
            shutil.copyfileobj(source, target, length=_COPY_BUFFER_BYTES)
    except OSError as exc:
        raise ExportError("Attachment bytes became unavailable while the export was being written.") from exc


def write_library_export(
    snapshot: LibrarySnapshot,
    *,
    attachment_root: Path,
    output_path: Path,
    overwrite: bool = False,
    exported_at: datetime | None = None,
) -> ExportResult:
    """Create and verify an atomic full-library ZIP export for one account."""

    exported_at = exported_at or datetime.now(UTC)
    if exported_at.tzinfo is None or exported_at.utcoffset() is None:
        raise ExportError("Export timestamp must contain timezone information.")

    output = output_path.expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and not overwrite:
        raise ExportError("Export output already exists; use explicit overwrite approval to replace it.")
    if output.exists() and not output.is_file():
        raise ExportError("Export output path is not a regular file.")

    _validate_snapshot_relationships(snapshot)
    evidence = _attachment_evidence(snapshot, attachment_root=attachment_root)
    library_payload = _build_library_payload(
        snapshot,
        exported_at=exported_at,
        attachment_evidence=evidence,
    )
    library_bytes = _canonical_json_bytes(library_payload)
    library_sha256 = hashlib.sha256(library_bytes).hexdigest()

    bundle_payload = {
        "format": BUNDLE_FORMAT,
        "schemaVersion": BUNDLE_SCHEMA_VERSION,
        "library": {
            "path": _LIBRARY_PATH,
            "sha256": library_sha256,
            "sizeBytes": len(library_bytes),
        },
        "attachments": [
            {
                "id": item["id"],
                "path": item["archivePath"],
                "sha256": item["sha256"],
                "sizeBytes": item["sizeBytes"],
            }
            for item in evidence
        ],
        "summary": library_payload["summary"],
    }
    bundle_bytes = _canonical_json_bytes(bundle_payload)

    temporary = output.with_name(f".{output.name}.{uuid4().hex}.part")
    try:
        with zipfile.ZipFile(temporary, mode="x", allowZip64=True) as archive:
            _write_bytes(archive, archive_path=_LIBRARY_PATH, payload=library_bytes, exported_at=exported_at)
            for item in evidence:
                _write_file(
                    archive,
                    archive_path=str(item["archivePath"]),
                    source_path=Path(str(item["sourcePath"])),
                    exported_at=exported_at,
                )
            _write_bytes(archive, archive_path=_BUNDLE_PATH, payload=bundle_bytes, exported_at=exported_at)

        verify_export_bundle(temporary)
        os.replace(temporary, output)
    except (OSError, zipfile.BadZipFile, ExportError):
        temporary.unlink(missing_ok=True)
        raise

    bundle_sha256, bundle_size = _hash_file(output)
    return ExportResult(
        output_path=output,
        sha256=bundle_sha256,
        size_bytes=bundle_size,
        note_count=len(snapshot.notes),
        attachment_count=len(snapshot.attachments),
    )


def export_user_library(
    db: Session,
    *,
    owner: User,
    attachment_root: Path,
    output_path: Path,
    overwrite: bool = False,
) -> ExportResult:
    """Load one user library from PostgreSQL and create a verified portable bundle."""

    snapshot = load_library_snapshot(db, owner=owner)
    return write_library_export(
        snapshot,
        attachment_root=attachment_root,
        output_path=output_path,
        overwrite=overwrite,
    )


def _read_json_member(archive: zipfile.ZipFile, path: str) -> dict[str, object]:
    try:
        payload = archive.read(path)
        decoded = json.loads(payload)
    except (KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExportError(f"Export bundle member {path!r} is missing or invalid JSON.") from exc
    if not isinstance(decoded, dict):
        raise ExportError(f"Export bundle member {path!r} must contain a JSON object.")
    return decoded


def _member_hash(archive: zipfile.ZipFile, path: str) -> tuple[str, int]:
    try:
        with archive.open(path, "r") as handle:
            return _hash_stream(handle)
    except KeyError as exc:
        raise ExportError(f"Export bundle is missing required member {path!r}.") from exc


def verify_export_bundle(path: Path) -> BundleVerification:
    """Verify bundle structure, hashes, attachment bytes, and cross-file metadata."""

    source = path.expanduser()
    if not source.is_file():
        raise ExportError("Export bundle is not a readable regular file.")

    try:
        with zipfile.ZipFile(source, mode="r") as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise ExportError("Export bundle contains duplicate archive member names.")
            for name in names:
                _safe_archive_path(name)

            bundle = _read_json_member(archive, _BUNDLE_PATH)
            if bundle.get("format") != BUNDLE_FORMAT or bundle.get("schemaVersion") != BUNDLE_SCHEMA_VERSION:
                raise ExportError("Export bundle format or schema version is unsupported.")

            raw_library = bundle.get("library")
            raw_attachments = bundle.get("attachments")
            if not isinstance(raw_library, dict) or not isinstance(raw_attachments, list):
                raise ExportError("Export bundle manifest is incomplete.")

            library_path = _safe_archive_path(str(raw_library.get("path", "")))
            if library_path != _LIBRARY_PATH:
                raise ExportError("Export bundle library member path is invalid.")
            library_sha256, library_size = _member_hash(archive, library_path)
            if library_sha256 != raw_library.get("sha256") or library_size != raw_library.get("sizeBytes"):
                raise ExportError("Export library JSON failed SHA-256 or size verification.")

            library = _read_json_member(archive, library_path)
            if library.get("format") != EXPORT_FORMAT or library.get("schemaVersion") != EXPORT_SCHEMA_VERSION:
                raise ExportError("Export library format or schema version is unsupported.")

            library_attachments = library.get("attachments")
            library_notes = library.get("notes")
            if not isinstance(library_attachments, list) or not isinstance(library_notes, list):
                raise ExportError("Export library is missing required note or attachment collections.")

            expected_names = {_BUNDLE_PATH, _LIBRARY_PATH}
            manifest_by_id: dict[str, dict[str, object]] = {}
            for raw in raw_attachments:
                if not isinstance(raw, dict):
                    raise ExportError("Export attachment manifest contains an invalid record.")
                attachment_id = str(raw.get("id", ""))
                member_path = _safe_archive_path(str(raw.get("path", "")))
                if not attachment_id or attachment_id in manifest_by_id:
                    raise ExportError("Export attachment manifest contains a missing or duplicate identifier.")
                if not member_path.startswith("attachments/"):
                    raise ExportError("Export attachment member is outside the attachment namespace.")
                sha256, size_bytes = _member_hash(archive, member_path)
                if sha256 != raw.get("sha256") or size_bytes != raw.get("sizeBytes"):
                    raise ExportError("Export attachment failed SHA-256 or size verification.")
                manifest_by_id[attachment_id] = raw
                expected_names.add(member_path)

            if set(names) != expected_names:
                raise ExportError("Export bundle contains undeclared or missing archive members.")

            if len(library_attachments) != len(manifest_by_id):
                raise ExportError("Export library and bundle manifest disagree on attachment count.")
            for raw in library_attachments:
                if not isinstance(raw, dict):
                    raise ExportError("Export library attachment collection contains an invalid record.")
                attachment_id = str(raw.get("id", ""))
                manifest = manifest_by_id.get(attachment_id)
                if manifest is None:
                    raise ExportError("Export library attachment is absent from the bundle manifest.")
                if (
                    raw.get("archivePath") != manifest.get("path")
                    or raw.get("sha256") != manifest.get("sha256")
                    or raw.get("sizeBytes") != manifest.get("sizeBytes")
                ):
                    raise ExportError("Export attachment metadata disagrees with verified bundle evidence.")

            summary = library.get("summary")
            if not isinstance(summary, dict):
                raise ExportError("Export library summary is missing.")
            if summary.get("notes") != len(library_notes) or summary.get("attachments") != len(library_attachments):
                raise ExportError("Export library summary counts do not match exported collections.")

    except zipfile.BadZipFile as exc:
        raise ExportError("Export bundle is not a valid ZIP archive.") from exc

    bundle_sha256, bundle_size = _hash_file(source)
    return BundleVerification(
        path=source,
        sha256=bundle_sha256,
        size_bytes=bundle_size,
        note_count=len(library_notes),
        attachment_count=len(library_attachments),
    )
