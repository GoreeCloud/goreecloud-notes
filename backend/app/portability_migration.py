"""Migration-provenance preservation for native full-library exports.

The base portability layer owns native notes, organization, revisions, and attachment bytes.
This module adds owner-scoped migration provenance to that same verified bundle so an
imported library does not lose exact source records merely because it is later exported from
native GoreeCloud Notes.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from .migration.persistence import MigrationImport, MigrationNoteRecord
from .models import User
from .portability import ExportError, ExportResult, export_user_library, verify_export_bundle

_COPY_BUFFER_BYTES = 1024 * 1024
_LIBRARY_PATH = "library.json"
_BUNDLE_PATH = "bundle.json"


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
        raise ExportError("Migration provenance contains a value that cannot be represented safely as JSON.") from exc


def _iso(value: datetime, *, field: str) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ExportError(f"{field} must contain timezone information.")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_iso(value: object, *, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ExportError(f"{field} must be an ISO-8601 timestamp string.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ExportError(f"{field} is not a valid ISO-8601 timestamp.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ExportError(f"{field} must contain timezone information.")
    return parsed.astimezone(UTC)


def _load_provenance(
    db: Session,
    *,
    owner: User,
) -> tuple[tuple[MigrationImport, ...], tuple[MigrationNoteRecord, ...]]:
    imports = tuple(
        db.scalars(
            select(MigrationImport)
            .where(MigrationImport.owner_id == owner.id)
            .order_by(MigrationImport.created_at.asc(), MigrationImport.id.asc())
        )
    )
    records = tuple(
        db.scalars(
            select(MigrationNoteRecord)
            .where(MigrationNoteRecord.owner_id == owner.id)
            .order_by(
                MigrationNoteRecord.import_id.asc(),
                MigrationNoteRecord.source_order.asc(),
                MigrationNoteRecord.source_name.asc(),
            )
        )
    )
    return imports, records


def _validate_and_serialize_provenance(
    library: dict[str, object],
    *,
    owner: User,
    imports: tuple[MigrationImport, ...],
    records: tuple[MigrationNoteRecord, ...],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    raw_notes = library.get("notes")
    if not isinstance(raw_notes, list):
        raise ExportError("Portable library is missing its note collection.")
    note_ids = {
        str(item.get("id"))
        for item in raw_notes
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    if len(note_ids) != len(raw_notes):
        raise ExportError("Portable library contains a note without a unique identifier.")

    import_ids = {item.id for item in imports}
    records_by_import: dict[object, int] = {item.id: 0 for item in imports}

    serialized_imports: list[dict[str, object]] = []
    for item in imports:
        if item.owner_id != owner.id:
            raise ExportError("Migration import ownership escaped the requested export scope.")
        serialized_imports.append(
            {
                "id": str(item.id),
                "provider": item.provider,
                "sourceExportSha256": item.source_export_sha256,
                "manifestSha256": item.manifest_sha256,
                "evidenceSha256": item.evidence_sha256,
                "sourceExportedAt": _iso(item.source_exported_at, field="migrationImport.sourceExportedAt"),
                "sourceNoteCount": item.source_note_count,
                "importedNoteCount": item.imported_note_count,
                "conversionProfile": item.conversion_profile,
                "createdAt": _iso(item.created_at, field="migrationImport.createdAt"),
            }
        )

    serialized_records: list[dict[str, object]] = []
    for item in records:
        if item.owner_id != owner.id:
            raise ExportError("Migration note-record ownership escaped the requested export scope.")
        if item.import_id not in import_ids:
            raise ExportError("Migration note record references an import checkpoint outside the exported account.")
        if str(item.note_id) not in note_ids:
            raise ExportError("Migration note record references a native note outside the portable library.")
        if not isinstance(item.source_record, dict):
            raise ExportError("Migration note record does not contain a source object.")

        unsigned = dict(item.source_record)
        embedded_sha = unsigned.pop("recordSha256", None)
        computed_sha = hashlib.sha256(_canonical_json_bytes(unsigned)).hexdigest()
        if embedded_sha != item.record_sha256 or computed_sha != item.record_sha256:
            raise ExportError("Migration source record failed its preserved SHA-256 integrity check.")

        records_by_import[item.import_id] += 1
        serialized_records.append(
            {
                "id": str(item.id),
                "importId": str(item.import_id),
                "noteId": str(item.note_id),
                "sourceName": item.source_name,
                "sourceUid": item.source_uid,
                "sourceOrder": item.source_order,
                "recordSha256": item.record_sha256,
                "sourceRecord": item.source_record,
                "createdAt": _iso(item.created_at, field="migrationNoteRecord.createdAt"),
            }
        )

    for item in imports:
        record_count = records_by_import[item.id]
        if record_count != item.imported_note_count or record_count != item.source_note_count:
            raise ExportError("Migration import checkpoint count disagrees with preserved source records.")

    return serialized_imports, serialized_records


def _augment_library(
    library: dict[str, object],
    *,
    owner: User,
    imports: tuple[MigrationImport, ...],
    records: tuple[MigrationNoteRecord, ...],
) -> dict[str, object]:
    serialized_imports, serialized_records = _validate_and_serialize_provenance(
        library,
        owner=owner,
        imports=imports,
        records=records,
    )
    summary = library.get("summary")
    if not isinstance(summary, dict):
        raise ExportError("Portable library is missing its summary object.")

    augmented = dict(library)
    augmented_summary = dict(summary)
    augmented_summary["migrationImports"] = len(serialized_imports)
    augmented_summary["migrationNoteRecords"] = len(serialized_records)
    augmented["summary"] = augmented_summary
    augmented["migrationImports"] = serialized_imports
    augmented["migrationNoteRecords"] = serialized_records
    return augmented


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


def _write_json(
    archive: zipfile.ZipFile,
    *,
    path: str,
    payload: bytes,
    exported_at: datetime,
) -> None:
    archive.writestr(
        _zip_info(path, exported_at=exported_at, compress_type=zipfile.ZIP_DEFLATED),
        payload,
    )


def _hash_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size_bytes = 0
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(_COPY_BUFFER_BYTES):
                digest.update(chunk)
                size_bytes += len(chunk)
    except OSError as exc:
        raise ExportError("Unable to hash completed portable export.") from exc
    return digest.hexdigest(), size_bytes


def export_user_library_with_provenance(
    db: Session,
    *,
    owner: User,
    attachment_root: Path,
    output_path: Path,
    overwrite: bool = False,
) -> ExportResult:
    """Create one verified native bundle including exact migration provenance records."""

    output = output_path.expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and not overwrite:
        raise ExportError("Export output already exists; use explicit overwrite approval to replace it.")
    if output.exists() and not output.is_file():
        raise ExportError("Export output path is not a regular file.")

    imports, records = _load_provenance(db, owner=owner)
    base = output.with_name(f".{output.name}.{uuid4().hex}.base.part")
    rewritten = output.with_name(f".{output.name}.{uuid4().hex}.provenance.part")

    try:
        base_result = export_user_library(
            db,
            owner=owner,
            attachment_root=attachment_root,
            output_path=base,
            overwrite=False,
        )

        # The base archive is independently verified by export_user_library. Rebuild it
        # rather than appending, because duplicate ZIP member names are intentionally
        # rejected by the portable verifier.
        with zipfile.ZipFile(base, mode="r") as source:
            try:
                library = json.loads(source.read(_LIBRARY_PATH))
                bundle = json.loads(source.read(_BUNDLE_PATH))
            except (KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ExportError("Verified base export unexpectedly lost its manifest JSON.") from exc
            if not isinstance(library, dict) or not isinstance(bundle, dict):
                raise ExportError("Verified base export manifests must contain JSON objects.")

            exported_at = _parse_iso(library.get("exportedAt"), field="exportedAt")
            augmented = _augment_library(
                library,
                owner=owner,
                imports=imports,
                records=records,
            )
            library_bytes = _canonical_json_bytes(augmented)
            library_sha256 = hashlib.sha256(library_bytes).hexdigest()

            bundle_library = bundle.get("library")
            attachment_manifest = bundle.get("attachments")
            if not isinstance(bundle_library, dict) or not isinstance(attachment_manifest, list):
                raise ExportError("Verified base export bundle manifest is incomplete.")
            updated_bundle = dict(bundle)
            updated_bundle["library"] = {
                "path": _LIBRARY_PATH,
                "sha256": library_sha256,
                "sizeBytes": len(library_bytes),
            }
            updated_bundle["summary"] = augmented["summary"]
            bundle_bytes = _canonical_json_bytes(updated_bundle)

            with zipfile.ZipFile(rewritten, mode="x", allowZip64=True) as target:
                _write_json(
                    target,
                    path=_LIBRARY_PATH,
                    payload=library_bytes,
                    exported_at=exported_at,
                )
                for raw in attachment_manifest:
                    if not isinstance(raw, dict) or not isinstance(raw.get("path"), str):
                        raise ExportError("Verified base export contains invalid attachment manifest data.")
                    member_path = raw["path"]
                    try:
                        source_info = source.getinfo(member_path)
                        with source.open(source_info, "r") as source_member, target.open(
                            _zip_info(member_path, exported_at=exported_at, compress_type=zipfile.ZIP_STORED),
                            "w",
                        ) as target_member:
                            shutil.copyfileobj(source_member, target_member, length=_COPY_BUFFER_BYTES)
                    except KeyError as exc:
                        raise ExportError("Verified base export lost a declared attachment member.") from exc
                _write_json(
                    target,
                    path=_BUNDLE_PATH,
                    payload=bundle_bytes,
                    exported_at=exported_at,
                )

        verification = verify_export_bundle(rewritten)
        if verification.note_count != base_result.note_count or verification.attachment_count != base_result.attachment_count:
            raise ExportError("Migration-provenance rewrite changed native note or attachment counts.")
        os.replace(rewritten, output)
    except (OSError, zipfile.BadZipFile, ExportError):
        raise
    finally:
        base.unlink(missing_ok=True)
        rewritten.unlink(missing_ok=True)

    sha256, size_bytes = _hash_file(output)
    return ExportResult(
        output_path=output,
        sha256=sha256,
        size_bytes=size_bytes,
        note_count=verification.note_count,
        attachment_count=verification.attachment_count,
    )
