from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.migration.manifest import build_memos_manifest, serialize_manifest

FIXTURE = Path(__file__).parent / "fixtures" / "memos_export_v1.json"


def test_manifest_is_deterministic_and_carries_source_fingerprint() -> None:
    first = build_memos_manifest(FIXTURE)
    second = build_memos_manifest(FIXTURE)

    assert serialize_manifest(first) == serialize_manifest(second)
    assert first["format"] == "goreecloud-notes-migration"
    assert first["schemaVersion"] == 1
    assert first["source"]["sha256"] == hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    assert first["source"]["sizeBytes"] == FIXTURE.stat().st_size
    assert first["validation"]["sourceMetadataValid"] is True
    assert first["validation"]["sourceMutationPerformed"] is False
    assert first["validation"]["targetMutationPerformed"] is False


def test_manifest_preserves_lifecycle_identity_content_and_binary_boundary() -> None:
    manifest = build_memos_manifest(FIXTURE)
    normal = next(note for note in manifest["notes"] if note["source"]["uid"] == "100")
    trashed = next(note for note in manifest["notes"] if note["source"]["uid"] == "101")

    assert normal["source"]["name"] == "memos/100"
    assert normal["source"]["state"] == "normal"
    assert normal["lifecycle"] == {"state": "active", "restoreTarget": None, "pinned": True}
    assert normal["content"]["markdownSha256"] == hashlib.sha256(normal["content"]["markdown"].encode()).hexdigest()
    assert len(normal["recordSha256"]) == 64

    attachment = normal["attachments"][0]
    assert attachment["source"]["name"] == "attachments/200"
    assert attachment["declaredSizeBytes"] == 68
    assert attachment["binary"] == {"status": "required", "sha256": None, "verifiedSizeBytes": None}

    relation = normal["relations"][0]
    assert relation["targetSourceMemo"] == "memos/101"
    assert relation["targetExported"] is True

    assert trashed["source"]["state"] == "trash"
    assert trashed["source"]["restoreTarget"] == "archived"
    assert trashed["lifecycle"] == {"state": "trashed", "restoreTarget": "archived", "pinned": False}


def test_external_attachment_remains_external_without_invented_checksum(tmp_path: Path) -> None:
    payload = json.loads(FIXTURE.read_text())
    payload["notes"][0]["attachments"][0]["externalLink"] = "https://example.invalid/reference.png"
    source = tmp_path / "external.json"
    source.write_text(json.dumps(payload))

    manifest = build_memos_manifest(source)
    attachment = manifest["notes"][0]["attachments"][0]

    assert attachment["externalLink"] == "https://example.invalid/reference.png"
    assert attachment["binary"] == {"status": "external", "sha256": None, "verifiedSizeBytes": None}
    assert manifest["validation"]["attachmentBinaryRecoveryRequired"] is False


def test_invalid_source_refuses_manifest_creation(tmp_path: Path) -> None:
    payload = json.loads(FIXTURE.read_text())
    payload["notes"][1]["uid"] = payload["notes"][0]["uid"]
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(payload))

    with pytest.raises(ValueError, match="Source metadata validation failed"):
        build_memos_manifest(invalid)
