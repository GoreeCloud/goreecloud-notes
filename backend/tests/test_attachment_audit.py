from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import uuid4

from app.attachment_audit import audit_attachment_records
from app.models import Attachment


def _fixture(root: Path) -> tuple[object, object, Attachment, bytes, Path]:
    owner_id = uuid4()
    note_id = uuid4()
    attachment_id = uuid4()
    payload = b"GoreeCloud Notes attachment integrity payload\n"
    storage_key = f"{owner_id}/{note_id}/{attachment_id}"
    path = root / storage_key
    path.parent.mkdir(parents=True)
    path.write_bytes(payload)
    attachment = Attachment(
        id=attachment_id,
        owner_id=owner_id,
        note_id=note_id,
        filename="integrity.txt",
        media_type="text/plain",
        size_bytes=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
        storage_key=storage_key,
        extra_metadata={},
    )
    return owner_id, note_id, attachment, payload, path


def test_attachment_audit_accepts_clean_owner_scoped_store(tmp_path: Path) -> None:
    root = tmp_path / "attachments"
    owner_id, note_id, attachment, payload, _ = _fixture(root)

    result = audit_attachment_records(
        owner_id=owner_id,
        attachments=[attachment],
        attachment_root=root,
        owned_note_ids={note_id},
    )

    assert result["clean"] is True
    assert result["issues"] == []
    assert result["summary"] == {
        "attachmentRecords": 1,
        "verifiedAttachments": 1,
        "metadataBytes": len(payload),
        "observedBytes": len(payload),
        "orphanFiles": 0,
        "issues": 0,
    }


def test_attachment_audit_detects_corruption_and_missing_bytes(tmp_path: Path) -> None:
    root = tmp_path / "attachments"
    owner_id, note_id, attachment, payload, path = _fixture(root)

    path.write_bytes(b"corrupted")
    corrupted = audit_attachment_records(
        owner_id=owner_id,
        attachments=[attachment],
        attachment_root=root,
        owned_note_ids={note_id},
    )
    corrupted_codes = {issue["code"] for issue in corrupted["issues"]}
    assert corrupted["clean"] is False
    assert "size_mismatch" in corrupted_codes
    assert "sha256_mismatch" in corrupted_codes

    path.unlink()
    missing = audit_attachment_records(
        owner_id=owner_id,
        attachments=[attachment],
        attachment_root=root,
        owned_note_ids={note_id},
    )
    assert missing["clean"] is False
    assert {issue["code"] for issue in missing["issues"]} == {"missing_bytes"}
    assert missing["summary"]["metadataBytes"] == len(payload)
    assert missing["summary"]["observedBytes"] == 0


def test_attachment_audit_detects_orphan_file_without_deleting_it(tmp_path: Path) -> None:
    root = tmp_path / "attachments"
    owner_id, note_id, attachment, _, _ = _fixture(root)
    orphan = root / str(owner_id) / "orphan-audit.bin"
    orphan.write_bytes(b"orphan")

    result = audit_attachment_records(
        owner_id=owner_id,
        attachments=[attachment],
        attachment_root=root,
        owned_note_ids={note_id},
    )

    assert result["clean"] is False
    assert result["summary"]["orphanFiles"] == 1
    assert any(issue["code"] == "orphan_file" for issue in result["issues"])
    assert orphan.read_bytes() == b"orphan"


def test_attachment_audit_rejects_invalid_ownership_and_storage_escape(tmp_path: Path) -> None:
    root = tmp_path / "attachments"
    owner_id, _, attachment, _, _ = _fixture(root)
    attachment.storage_key = "../../outside.bin"

    result = audit_attachment_records(
        owner_id=owner_id,
        attachments=[attachment],
        attachment_root=root,
        owned_note_ids=set(),
    )
    codes = {issue["code"] for issue in result["issues"]}

    assert result["clean"] is False
    assert "note_owner_mismatch" in codes
    assert "storage_key_mismatch" in codes
    assert "storage_escape" in codes


def test_attachment_audit_rejects_duplicate_storage_keys(tmp_path: Path) -> None:
    root = tmp_path / "attachments"
    owner_id, note_id, first, _, _ = _fixture(root)
    second = Attachment(
        id=uuid4(),
        owner_id=owner_id,
        note_id=note_id,
        filename="duplicate.txt",
        media_type="text/plain",
        size_bytes=first.size_bytes,
        sha256=first.sha256,
        storage_key=first.storage_key,
        extra_metadata={},
    )

    result = audit_attachment_records(
        owner_id=owner_id,
        attachments=[first, second],
        attachment_root=root,
        owned_note_ids={note_id},
    )
    codes = [issue["code"] for issue in result["issues"]]

    assert result["clean"] is False
    assert "duplicate_storage_key" in codes
    assert "storage_key_mismatch" in codes
