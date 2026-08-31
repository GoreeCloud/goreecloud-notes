from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from app.migration.evidence import serialize_evidence, verify_attachment_binaries
from app.migration.manifest import build_memos_manifest, serialize_manifest

EXPORT_FIXTURE = Path(__file__).parent / "fixtures" / "memos_export_v1.json"
PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Z8XcAAAAASUVORK5CYII="
)
PNG_SHA256 = "489b326e81d3ef516100495b2b2ea91199dafa1f57b7e78bcebddda1bbe36e13"


def _write_inputs(tmp_path: Path, *, include_mapping: bool = True) -> tuple[Path, Path, Path]:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(serialize_manifest(build_memos_manifest(EXPORT_FIXTURE)))

    evidence_root = tmp_path / "attachment-bytes"
    evidence_root.mkdir()
    (evidence_root / "fixture.png").write_bytes(PNG_BYTES)

    attachment_map = {
        "format": "goreecloud-notes-attachment-map",
        "schemaVersion": 1,
        "attachments": (
            [{"sourceName": "attachments/200", "relativePath": "fixture.png"}]
            if include_mapping
            else []
        ),
    }
    map_path = tmp_path / "attachment-map.json"
    map_path.write_text(json.dumps(attachment_map))
    return manifest_path, map_path, evidence_root


def test_attachment_evidence_verifies_bytes_without_mutation_or_absolute_paths(tmp_path: Path) -> None:
    manifest_path, map_path, evidence_root = _write_inputs(tmp_path)

    evidence = verify_attachment_binaries(manifest_path, map_path, evidence_root)

    assert evidence["verification"] == {
        "complete": True,
        "requiredAttachments": 1,
        "verifiedAttachments": 1,
        "missingAttachments": 0,
        "sourceMutationPerformed": False,
        "targetMutationPerformed": False,
    }
    attachment = evidence["attachments"][0]
    assert attachment["sourceName"] == "attachments/200"
    assert attachment["relativePath"] == "fixture.png"
    assert attachment["declaredSizeBytes"] == 68
    assert attachment["verifiedSizeBytes"] == 68
    assert attachment["sha256"] == PNG_SHA256
    assert str(evidence_root) not in serialize_evidence(evidence)


def test_missing_mapping_produces_explicit_incomplete_evidence(tmp_path: Path) -> None:
    manifest_path, map_path, evidence_root = _write_inputs(tmp_path, include_mapping=False)

    evidence = verify_attachment_binaries(manifest_path, map_path, evidence_root)

    assert evidence["verification"]["complete"] is False
    assert evidence["verification"]["missingAttachments"] == 1
    assert evidence["missingSourceNames"] == ["attachments/200"]
    assert evidence["attachments"] == []


def test_size_mismatch_is_rejected(tmp_path: Path) -> None:
    manifest_path, map_path, evidence_root = _write_inputs(tmp_path)
    (evidence_root / "fixture.png").write_bytes(PNG_BYTES + b"tamper")

    with pytest.raises(ValueError, match="does not match declared size"):
        verify_attachment_binaries(manifest_path, map_path, evidence_root)


def test_symlink_evidence_is_rejected(tmp_path: Path) -> None:
    manifest_path, map_path, evidence_root = _write_inputs(tmp_path)
    real_file = evidence_root / "real.png"
    real_file.write_bytes(PNG_BYTES)
    (evidence_root / "fixture.png").unlink()
    (evidence_root / "fixture.png").symlink_to(real_file.name)

    with pytest.raises(ValueError, match="symbolic link"):
        verify_attachment_binaries(manifest_path, map_path, evidence_root)


def test_tampered_manifest_record_is_rejected(tmp_path: Path) -> None:
    manifest_path, map_path, evidence_root = _write_inputs(tmp_path)
    manifest = json.loads(manifest_path.read_text())
    manifest["notes"][0]["content"]["markdown"] += " tampered"
    manifest_path.write_text(json.dumps(manifest))

    with pytest.raises(ValueError, match="recordSha256"):
        verify_attachment_binaries(manifest_path, map_path, evidence_root)
