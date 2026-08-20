"""Target-writing half of the controlled Memos migration pipeline.

The validation and equivalence helpers live in :mod:`app.migration.importer`. This module
keeps the target mutation boundary small and explicit: the import checkpoint, native note,
and newly created tag parents are flushed before any provenance, note-tag, or attachment
rows are allowed to reference them.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from ..documents import DOCUMENT_SCHEMA
from ..models import Attachment, Note, NoteTag, Tag, User
from .importer import (
    CONVERSION_PROFILE,
    DEFAULT_MAX_INPUT_BYTES,
    IMPORT_RESULT_FORMAT,
    IMPORT_RESULT_SCHEMA_VERSION,
    MigrationImportError,
    _StagedAttachment,
    _clean_filename,
    _clean_name,
    _copy_evidence_to_temporary,
    _hash_file,
    _native_color,
    _parse_timestamp,
    _preflight_note,
    _read_json,
    _resolve_evidence_file,
    _safe_storage_path,
    _target_data_count,
    _validate_evidence,
    _validate_evidence_root,
    _validate_manifest,
    markdown_to_literal_document,
)
from .persistence import MigrationImport, MigrationNoteRecord


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
    """Import one validated Memos manifest into an explicitly empty native account.

    Parent rows are deliberately flushed before dependent rows. This is not left to implicit
    ORM ordering because the migration records use explicit UUID foreign keys rather than
    object relationships. The complete database import remains one transaction.
    """

    if max_input_bytes <= 0:
        raise MigrationImportError("Input-size limit must be positive.")
    if _target_data_count(db, owner_id=owner.id) != 0:
        raise MigrationImportError(
            "Target account is not empty; migration import was refused to prevent duplication or merging."
        )

    manifest, manifest_raw = _read_json(
        manifest_path,
        label="Migration manifest",
        max_bytes=max_input_bytes,
    )
    manifest_sha256, notes = _validate_manifest(manifest, manifest_raw)
    source = manifest["source"]
    source_export_sha256 = source["sha256"]
    source_exported_at = _parse_timestamp(source.get("exportedAt"), field="source.exportedAt")

    evidence, evidence_raw = _read_json(
        evidence_path,
        label="Attachment evidence",
        max_bytes=max_input_bytes,
    )
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

    # Re-hash every source attachment before target mutation begins. The staged copy is
    # independently hashed again while it is written so a changed evidence file fails closed.
    evidence_paths: dict[str, Path] = {}
    for source_name, expected in evidence_by_name.items():
        evidence_file = _resolve_evidence_file(
            resolved_evidence_root,
            expected.relative_path,
        )
        digest, size_bytes = _hash_file(evidence_file)
        if digest != expected.sha256 or size_bytes != expected.size_bytes:
            raise MigrationImportError(
                f"Attachment evidence bytes no longer match verified evidence for {source_name!r}."
            )
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
        # Flush the import checkpoint first because every provenance row references it.
        checkpoint = MigrationImport(
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
        db.add(checkpoint)
        db.flush([checkpoint])

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
            deferred_relations += len(note.get("relations", []))

            created_at = _parse_timestamp(
                metadata["createTime"],
                field=f"{source_name}.createTime",
            )
            updated_at = _parse_timestamp(
                metadata["updateTime"],
                field=f"{source_name}.updateTime",
            )
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
            # The note must exist before provenance, tag assignments, and attachments can
            # safely reference its explicit UUID.
            db.flush([native_note])

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

            assigned_tag_ids: set[UUID] = set()
            for source_tag in metadata["tags"]:
                display_name = _clean_name(source_tag, field="tag", max_length=128)
                normalized = display_name.casefold()
                tag_id = tag_ids.get(normalized)
                if tag_id is None:
                    tag_id = uuid4()
                    tag_ids[normalized] = tag_id
                    source_tag_display[normalized] = display_name
                    native_tag = Tag(
                        id=tag_id,
                        owner_id=owner.id,
                        name=display_name,
                        normalized_name=normalized,
                        color=None,
                    )
                    db.add(native_tag)
                    # NoteTag uses raw foreign-key UUIDs, so make the tag parent explicit.
                    db.flush([native_tag])
                if tag_id in assigned_tag_ids:
                    continue
                assigned_tag_ids.add(tag_id)
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
                temporary_path = final_path.with_name(
                    f".{final_path.name}.{uuid4().hex}.part"
                )
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

        # At this point every raw UUID parent has already been persisted in the open
        # transaction, so the remaining dependent rows can be flushed deterministically.
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
