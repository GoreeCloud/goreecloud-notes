from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from app.models import Attachment, Note, Notebook, NoteRevision, NoteTag, Tag, User
from app.portability import ExportError, LibrarySnapshot, verify_export_bundle, write_library_export


def _timestamp() -> datetime:
    return datetime(2026, 8, 14, 18, 0, tzinfo=UTC)


def _snapshot(root: Path) -> tuple[LibrarySnapshot, bytes, Attachment]:
    now = _timestamp()
    owner_id = uuid4()
    notebook_id = uuid4()
    note_id = uuid4()
    tag_id = uuid4()
    attachment_id = uuid4()

    owner = User(
        id=owner_id,
        username="export-owner",
        username_normalized="export-owner",
        display_name="Export Owner",
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    notebook = Notebook(
        id=notebook_id,
        owner_id=owner_id,
        parent_id=None,
        name="Portable Notebook",
        sort_order=10,
        created_at=now,
        updated_at=now,
    )
    document = {
        "format": "goreecloud.blocks",
        "version": 1,
        "blocks": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "Portable export body"}],
            },
            {
                "type": "attachmentImage",
                "attachment_id": str(attachment_id),
                "alt": "Portable image",
            },
        ],
    }
    note = Note(
        id=note_id,
        owner_id=owner_id,
        notebook_id=notebook_id,
        title="Portable note",
        document=document,
        document_schema=1,
        content_version=2,
        state="normal",
        is_pinned=True,
        color="#112233",
        created_at=now,
        updated_at=now,
    )
    tag = Tag(
        id=tag_id,
        owner_id=owner_id,
        name="Export",
        normalized_name="export",
        color="#445566",
        created_at=now,
        updated_at=now,
    )
    note_tag = NoteTag(
        owner_id=owner_id,
        note_id=note_id,
        tag_id=tag_id,
        created_at=now,
    )

    attachment_bytes = b"GoreeCloud Notes portable attachment bytes\n"
    storage_key = f"{owner_id}/{note_id}/{attachment_id}"
    attachment_path = root / storage_key
    attachment_path.parent.mkdir(parents=True)
    attachment_path.write_bytes(attachment_bytes)
    attachment = Attachment(
        id=attachment_id,
        owner_id=owner_id,
        note_id=note_id,
        filename="portable.txt",
        media_type="text/plain",
        size_bytes=len(attachment_bytes),
        sha256=hashlib.sha256(attachment_bytes).hexdigest(),
        storage_key=storage_key,
        extra_metadata={"purpose": "portability-test"},
        created_at=now,
        updated_at=now,
    )
    revision = NoteRevision(
        id=uuid4(),
        owner_id=owner_id,
        note_id=note_id,
        revision_number=1,
        content_version=1,
        title="Portable note before edit",
        document={
            "format": "goreecloud.blocks",
            "version": 1,
            "blocks": [{"type": "paragraph", "content": [{"type": "text", "text": "Original"}]}],
        },
        document_schema=1,
        created_at=now,
        change_summary="Pre-change snapshot",
    )
    return (
        LibrarySnapshot(
            owner=owner,
            notebooks=(notebook,),
            notes=(note,),
            tags=(tag,),
            note_tags=(note_tag,),
            attachments=(attachment,),
            revisions=(revision,),
        ),
        attachment_bytes,
        attachment,
    )


def test_export_bundle_preserves_library_and_verified_attachment_bytes(tmp_path: Path) -> None:
    attachment_root = tmp_path / "attachments"
    snapshot, attachment_bytes, attachment = _snapshot(attachment_root)
    output = tmp_path / "library.zip"

    result = write_library_export(
        snapshot,
        attachment_root=attachment_root,
        output_path=output,
        exported_at=_timestamp(),
    )

    assert result.output_path == output
    assert result.note_count == 1
    assert result.attachment_count == 1
    assert result.size_bytes == output.stat().st_size
    assert result.sha256 == hashlib.sha256(output.read_bytes()).hexdigest()

    verified = verify_export_bundle(output)
    assert verified.sha256 == result.sha256
    assert verified.note_count == 1
    assert verified.attachment_count == 1

    with zipfile.ZipFile(output) as archive:
        library_bytes = archive.read("library.json")
        library = json.loads(library_bytes)
        bundle = json.loads(archive.read("bundle.json"))

        assert library["format"] == "goreecloud-notes-native-export"
        assert library["schemaVersion"] == 1
        assert library["source"] == {
            "application": "GoreeCloud Notes",
            "dataModel": "native",
            "sourceMutationPerformed": False,
        }
        assert library["account"]["username"] == "export-owner"
        assert library["summary"] == {
            "attachments": 1,
            "noteTagRelationships": 1,
            "notebooks": 1,
            "notes": 1,
            "revisions": 1,
            "tags": 1,
        }
        assert library["notes"][0]["document"] == snapshot.notes[0].document
        assert library["noteTags"][0] == {
            "createdAt": "2026-08-14T18:00:00Z",
            "noteId": str(snapshot.notes[0].id),
            "tagId": str(snapshot.tags[0].id),
        }
        assert library["revisions"][0]["title"] == "Portable note before edit"
        assert library["attachments"][0]["sha256"] == attachment.sha256
        assert library["attachments"][0]["sizeBytes"] == len(attachment_bytes)
        archive_path = library["attachments"][0]["archivePath"]
        assert archive.read(archive_path) == attachment_bytes

        assert bundle["library"]["sha256"] == hashlib.sha256(library_bytes).hexdigest()
        assert bundle["attachments"][0]["path"] == archive_path
        assert set(archive.namelist()) == {"bundle.json", "library.json", archive_path}

    serialized = output.read_bytes()
    assert attachment.storage_key.encode() not in serialized
    assert b"goreecloud_notes_session" not in serialized
    assert b"password_hash" not in serialized


def test_export_refuses_existing_output_without_explicit_overwrite(tmp_path: Path) -> None:
    attachment_root = tmp_path / "attachments"
    snapshot, _, _ = _snapshot(attachment_root)
    output = tmp_path / "library.zip"
    output.write_bytes(b"existing")

    with pytest.raises(ExportError, match="already exists"):
        write_library_export(snapshot, attachment_root=attachment_root, output_path=output)

    assert output.read_bytes() == b"existing"


def test_export_fails_closed_when_attachment_bytes_do_not_match_metadata(tmp_path: Path) -> None:
    attachment_root = tmp_path / "attachments"
    snapshot, _, attachment = _snapshot(attachment_root)
    (attachment_root / attachment.storage_key).write_bytes(b"corrupted")
    output = tmp_path / "library.zip"

    with pytest.raises(ExportError, match="byte size|SHA-256"):
        write_library_export(snapshot, attachment_root=attachment_root, output_path=output)

    assert not output.exists()


def test_export_rejects_attachment_storage_escape(tmp_path: Path) -> None:
    attachment_root = tmp_path / "attachments"
    snapshot, _, attachment = _snapshot(attachment_root)
    attachment.storage_key = "../../outside"
    output = tmp_path / "library.zip"

    with pytest.raises(ExportError, match="escapes"):
        write_library_export(snapshot, attachment_root=attachment_root, output_path=output)

    assert not output.exists()
