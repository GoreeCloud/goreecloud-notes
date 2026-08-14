from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.migration.persistence import MigrationImport, MigrationNoteRecord
from app.models import User
from app.portability import ExportError
from app.portability_migration import _augment_library


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _fixture() -> tuple[User, dict[str, object], MigrationImport, MigrationNoteRecord]:
    now = datetime(2026, 8, 14, 18, 30, tzinfo=UTC)
    owner_id = uuid4()
    note_id = uuid4()
    import_id = uuid4()

    owner = User(
        id=owner_id,
        username="portable-migration-owner",
        username_normalized="portable-migration-owner",
        display_name="Portable Migration Owner",
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    library: dict[str, object] = {
        "format": "goreecloud-notes-native-export",
        "schemaVersion": 1,
        "summary": {
            "notebooks": 0,
            "notes": 1,
            "tags": 0,
            "noteTagRelationships": 0,
            "attachments": 0,
            "revisions": 0,
        },
        "notes": [{"id": str(note_id), "title": "Imported note"}],
    }

    unsigned_source = {
        "source": {"name": "memos/100", "uid": "fixture-uid", "order": 0},
        "content": {
            "title": "Migration fixture",
            "markdown": "# Migration fixture\n\nNative migration inventory.",
            "markdownSha256": hashlib.sha256(
                b"# Migration fixture\n\nNative migration inventory."
            ).hexdigest(),
        },
        "lifecycle": {
            "state": "active",
            "sourceState": "NORMAL",
            "restoreTarget": None,
            "pinned": True,
        },
        "metadata": {
            "visibility": "PRIVATE",
            "color": "blue",
            "tags": ["goreecloud", "migration"],
            "createTime": "2026-08-12T16:00:00Z",
            "updateTime": "2026-08-12T16:30:00Z",
            "location": {"placeholder": "preserved"},
            "sourceMetadata": None,
        },
        "attachments": [],
        "relations": [{"type": "REFERENCE", "relatedMemo": "memos/101"}],
    }
    record_sha256 = _canonical_sha256(unsigned_source)
    source_record = dict(unsigned_source)
    source_record["recordSha256"] = record_sha256

    migration_import = MigrationImport(
        id=import_id,
        owner_id=owner_id,
        provider="memos",
        source_export_sha256="a" * 64,
        manifest_sha256="b" * 64,
        evidence_sha256="c" * 64,
        source_exported_at=now,
        source_note_count=1,
        imported_note_count=1,
        conversion_profile="literal-markdown-lines-v1",
        created_at=now,
    )
    record = MigrationNoteRecord(
        id=uuid4(),
        import_id=import_id,
        owner_id=owner_id,
        note_id=note_id,
        source_name="memos/100",
        source_uid="fixture-uid",
        source_order=0,
        record_sha256=record_sha256,
        source_record=source_record,
        created_at=now,
    )
    return owner, library, migration_import, record


def test_portable_library_preserves_exact_migration_provenance() -> None:
    owner, library, migration_import, record = _fixture()

    augmented = _augment_library(
        library,
        owner=owner,
        imports=(migration_import,),
        records=(record,),
    )

    assert augmented["summary"] == {
        "attachments": 0,
        "migrationImports": 1,
        "migrationNoteRecords": 1,
        "noteTagRelationships": 0,
        "notebooks": 0,
        "notes": 1,
        "revisions": 0,
        "tags": 0,
    }
    assert augmented["migrationImports"] == [
        {
            "id": str(migration_import.id),
            "provider": "memos",
            "sourceExportSha256": "a" * 64,
            "manifestSha256": "b" * 64,
            "evidenceSha256": "c" * 64,
            "sourceExportedAt": "2026-08-14T18:30:00Z",
            "sourceNoteCount": 1,
            "importedNoteCount": 1,
            "conversionProfile": "literal-markdown-lines-v1",
            "createdAt": "2026-08-14T18:30:00Z",
        }
    ]
    exported_record = augmented["migrationNoteRecords"][0]
    assert exported_record["importId"] == str(migration_import.id)
    assert exported_record["noteId"] == str(record.note_id)
    assert exported_record["sourceName"] == "memos/100"
    assert exported_record["recordSha256"] == record.record_sha256
    assert exported_record["sourceRecord"] == record.source_record
    assert exported_record["sourceRecord"]["metadata"]["color"] == "blue"
    assert exported_record["sourceRecord"]["metadata"]["location"] == {"placeholder": "preserved"}
    assert exported_record["sourceRecord"]["relations"] == [
        {"type": "REFERENCE", "relatedMemo": "memos/101"}
    ]


def test_portable_library_rejects_tampered_migration_source_record() -> None:
    owner, library, migration_import, record = _fixture()
    record.source_record["content"]["markdown"] = "tampered"

    with pytest.raises(ExportError, match="SHA-256 integrity"):
        _augment_library(
            library,
            owner=owner,
            imports=(migration_import,),
            records=(record,),
        )


def test_portable_library_rejects_incomplete_migration_provenance() -> None:
    owner, library, migration_import, record = _fixture()
    migration_import.imported_note_count = 2

    with pytest.raises(ExportError, match="count disagrees"):
        _augment_library(
            library,
            owner=owner,
            imports=(migration_import,),
            records=(record,),
        )
