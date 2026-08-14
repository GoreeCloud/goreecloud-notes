from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from app.models import Attachment, Note, Notebook, NoteRevision, NoteTag, Tag, User
from app.native_import import NativeImportError, _validate_library_payload, load_native_import_plan
from app.portability import LibrarySnapshot, verify_export_bundle, write_library_export


def _timestamp() -> datetime:
    return datetime(2026, 8, 14, 20, 30, tzinfo=UTC)


def _portable_bundle(tmp_path: Path) -> Path:
    now = _timestamp()
    attachment_root = tmp_path / "source-attachments"
    owner_id = uuid4()
    notebook_id = uuid4()
    note_id = uuid4()
    tag_id = uuid4()
    attachment_id = uuid4()

    owner = User(
        id=owner_id,
        username="native-import-source",
        username_normalized="native-import-source",
        display_name="Native Import Source",
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    notebook = Notebook(
        id=notebook_id,
        owner_id=owner_id,
        parent_id=None,
        name="Recovery Notebook",
        sort_order=5,
        created_at=now,
        updated_at=now,
    )
    document = {
        "format": "goreecloud.blocks",
        "version": 1,
        "blocks": [
            {"type": "paragraph", "content": [{"type": "text", "text": "Portable recovery"}]},
            {"type": "attachmentImage", "attachment_id": str(attachment_id), "alt": "Recovered image"},
        ],
    }
    note = Note(
        id=note_id,
        owner_id=owner_id,
        notebook_id=notebook_id,
        title="Native recovery note",
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
        name="Recovery",
        normalized_name="recovery",
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
    attachment_bytes = (
        b"\x89PNG\r\n\x1a\n"
        b"GoreeCloud Notes native import fixture bytes"
    )
    storage_key = f"{owner_id}/{note_id}/{attachment_id}"
    source_file = attachment_root / storage_key
    source_file.parent.mkdir(parents=True)
    source_file.write_bytes(attachment_bytes)
    attachment = Attachment(
        id=attachment_id,
        owner_id=owner_id,
        note_id=note_id,
        filename="recovered.png",
        media_type="image/png",
        size_bytes=len(attachment_bytes),
        sha256=hashlib.sha256(attachment_bytes).hexdigest(),
        storage_key=storage_key,
        extra_metadata={"purpose": "native-import-test"},
        created_at=now,
        updated_at=now,
    )
    revision = NoteRevision(
        id=uuid4(),
        owner_id=owner_id,
        note_id=note_id,
        revision_number=1,
        content_version=1,
        title="Native recovery note before edit",
        document={
            "format": "goreecloud.blocks",
            "version": 1,
            "blocks": [{"type": "paragraph", "content": [{"type": "text", "text": "Earlier"}]}],
        },
        document_schema=1,
        created_at=now,
        change_summary="Pre-change snapshot",
    )
    snapshot = LibrarySnapshot(
        owner=owner,
        notebooks=(notebook,),
        notes=(note,),
        tags=(tag,),
        note_tags=(note_tag,),
        attachments=(attachment,),
        revisions=(revision,),
    )
    output = tmp_path / "native-library.zip"
    write_library_export(
        snapshot,
        attachment_root=attachment_root,
        output_path=output,
        exported_at=now,
    )
    return output


def test_native_import_plan_accepts_verified_native_bundle(tmp_path: Path) -> None:
    bundle = _portable_bundle(tmp_path)
    plan = load_native_import_plan(bundle)

    assert plan.source_username == "native-import-source"
    assert len(plan.notebooks) == 1
    assert len(plan.notes) == 1
    assert len(plan.tags) == 1
    assert len(plan.note_tags) == 1
    assert len(plan.attachments) == 1
    assert len(plan.revisions) == 1
    assert plan.migration_imports == ()
    assert plan.migration_records == ()
    assert plan.notes[0]["_document"] == plan.library["notes"][0]["document"]
    assert plan.attachments[0]["_media_type"] == "image/png"


def test_native_import_plan_rejects_summary_mismatch_after_bundle_verification(tmp_path: Path) -> None:
    bundle = _portable_bundle(tmp_path)
    verification = verify_export_bundle(bundle)
    plan = load_native_import_plan(bundle)
    tampered = dict(plan.library)
    tampered_summary = dict(tampered["summary"])
    tampered_summary["tags"] = 99
    tampered["summary"] = tampered_summary

    with pytest.raises(NativeImportError, match="summary count for tags"):
        _validate_library_payload(tampered, path=bundle, verification=verification)


def test_native_import_plan_rejects_wrong_note_attachment_scope(tmp_path: Path) -> None:
    bundle = _portable_bundle(tmp_path)
    verification = verify_export_bundle(bundle)
    plan = load_native_import_plan(bundle)
    tampered = dict(plan.library)
    note = dict(tampered["notes"][0])
    document = dict(note["document"])
    blocks = [dict(item) for item in document["blocks"]]
    blocks[1] = dict(blocks[1])
    blocks[1]["attachment_id"] = str(uuid4())
    document["blocks"] = blocks
    note["document"] = document
    tampered["notes"] = [note]

    with pytest.raises(NativeImportError, match="inline attachment reference"):
        _validate_library_payload(tampered, path=bundle, verification=verification)


def test_native_import_refuses_symbolic_link_bundle(tmp_path: Path) -> None:
    bundle = _portable_bundle(tmp_path)
    link = tmp_path / "linked-library.zip"
    link.symlink_to(bundle)

    with pytest.raises(NativeImportError, match="symbolic link"):
        load_native_import_plan(link)
