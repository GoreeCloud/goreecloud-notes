from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from app.migration.enex_normalization import (
    NORMALIZATION_FORMAT,
    build_enex_normalization,
    main as normalization_main,
    serialize_enex_normalization,
)
from app.migration.enex_resources import EVIDENCE_FILENAME, extract_enex_resources

FIXTURE = Path(__file__).parent / "fixtures" / "evernote_export.enex"
HELLO_SHA256 = "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
EXPECTED_ENML = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<!DOCTYPE en-note SYSTEM "http://xml.evernote.com/pub/enml2.dtd">'
    '<en-note>Hello<div>World</div></en-note>'
)


def _resource_evidence(tmp_path: Path, source: Path = FIXTURE) -> Path:
    root = tmp_path / "resource-evidence"
    extract_enex_resources(source, root)
    return root / EVIDENCE_FILENAME


def _no_resource_enex(tmp_path: Path) -> Path:
    path = tmp_path / "no-resource.enex"
    path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<en-export export-date="20260815T050000Z" application="Evernote/10.0" version="10.0">
  <note>
    <title>No resource</title>
    <content><![CDATA[<en-note>Plain note</en-note>]]></content>
    <created>20260814T120000Z</created>
    <updated>20260815T040000Z</updated>
  </note>
</en-export>
""",
        encoding="utf-8",
    )
    return path


def test_enex_normalization_is_deterministic_and_preserves_exact_enml(tmp_path: Path) -> None:
    evidence_path = _resource_evidence(tmp_path)

    first = build_enex_normalization(FIXTURE, resource_evidence_path=evidence_path)
    second = build_enex_normalization(FIXTURE, resource_evidence_path=evidence_path)

    assert first == second
    assert first["format"] == NORMALIZATION_FORMAT
    assert first["schemaVersion"] == 1
    assert first["validation"] == {
        "sourceMetadataValid": True,
        "sourceWarnings": first["validation"]["sourceWarnings"],
        "resourceEvidenceRequired": True,
        "resourceEvidenceValidated": True,
        "exactEnmlPreserved": True,
        "enmlConversionPerformed": False,
        "nativeDocumentCreated": False,
        "sourceMutationPerformed": False,
        "targetMutationPerformed": False,
    }

    note = first["notes"][0]
    assert note["content"]["enml"] == EXPECTED_ENML
    assert note["content"]["conversionStatus"] == "preserved-source-enml"
    assert note["timestamps"] == {
        "createdAt": "2026-08-14T12:00:00Z",
        "updatedAt": "2026-08-15T04:00:00Z",
        "deletedAt": None,
    }
    assert [tag["normalizedName"] for tag in note["tags"]] == ["research", "goreecloud"]
    resource = note["resources"][0]
    assert resource["binary"]["sha256"] == HELLO_SHA256
    assert resource["binary"]["sizeBytes"] == 5
    assert resource["source"]["fileName"] == "hello.txt"

    serialized = serialize_enex_normalization(first)
    assert json.loads(serialized) == first
    assert serialized == serialize_enex_normalization(second)


def test_enex_normalization_requires_resource_evidence_when_resources_exist() -> None:
    with pytest.raises(ValueError, match="requires the validated resource-evidence JSON"):
        build_enex_normalization(FIXTURE)


def test_enex_normalization_allows_resource_free_source_without_evidence(tmp_path: Path) -> None:
    source = _no_resource_enex(tmp_path)

    normalization = build_enex_normalization(source)

    assert normalization["inventory"]["resources"] == 0
    assert normalization["resourceEvidence"] is None
    assert normalization["validation"]["resourceEvidenceRequired"] is False
    assert normalization["validation"]["resourceEvidenceValidated"] is False
    assert normalization["notes"][0]["resources"] == []


def test_enex_normalization_refuses_evidence_from_different_source(tmp_path: Path) -> None:
    evidence_path = _resource_evidence(tmp_path)
    changed = tmp_path / "changed.enex"
    changed.write_text(
        FIXTURE.read_text(encoding="utf-8").replace("Migration Fixture", "Changed Fixture", 1),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="does not match the exact source ENEX fingerprint"):
        build_enex_normalization(changed, resource_evidence_path=evidence_path)


def test_enex_normalization_refuses_tampered_resource_evidence(tmp_path: Path) -> None:
    evidence_path = _resource_evidence(tmp_path)
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    payload["resources"][0]["output"]["sha256"] = "0" * 64
    tampered = tmp_path / "tampered-evidence.json"
    tampered.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="does not match the validated source resource bytes"):
        build_enex_normalization(FIXTURE, resource_evidence_path=tampered)


def test_enex_normalization_refuses_unsafe_resource_evidence_path(tmp_path: Path) -> None:
    evidence_path = _resource_evidence(tmp_path)
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    payload["resources"][0]["output"]["relativePath"] = "../escape.bin"
    tampered = tmp_path / "unsafe-evidence.json"
    tampered.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="unsafe generated relative path"):
        build_enex_normalization(FIXTURE, resource_evidence_path=tampered)


def test_enex_normalization_preserves_cdata_line_endings_exactly(tmp_path: Path) -> None:
    source = tmp_path / "line-endings.enex"
    source.write_bytes(
        b'<?xml version="1.0" encoding="UTF-8"?>\n'
        b'<en-export export-date="20260815T050000Z" application="Evernote/10.0" version="10.0">\n'
        b'<note><title>Line endings</title><content><![CDATA[<en-note>first\r\nsecond</en-note>]]></content>'
        b'<created>20260814T120000Z</created><updated>20260815T040000Z</updated></note>\n'
        b'</en-export>\n'
    )

    normalization = build_enex_normalization(source)

    enml = normalization["notes"][0]["content"]["enml"]
    assert enml == "<en-note>first\r\nsecond</en-note>"
    assert "\r\n" in enml


def test_enex_normalization_refuses_non_cdata_content_for_exact_preservation(tmp_path: Path) -> None:
    source = tmp_path / "encoded-content.enex"
    source.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<en-export export-date="20260815T050000Z" application="Evernote/10.0" version="10.0">
  <note>
    <title>Encoded content</title>
    <content>&lt;en-note&gt;Plain note&lt;/en-note&gt;</content>
    <created>20260814T120000Z</created>
    <updated>20260815T040000Z</updated>
  </note>
</en-export>
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="exactly one UTF-8 CDATA"):
        build_enex_normalization(source)


def test_enex_normalization_cli_emits_machine_readable_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    evidence_path = _resource_evidence(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "python -m app.migration.enex_normalization",
            str(FIXTURE),
            "--resource-evidence",
            str(evidence_path),
        ],
    )

    assert normalization_main() == 0
    stdout = capsys.readouterr().out
    normalization = json.loads(stdout)

    assert normalization["format"] == NORMALIZATION_FORMAT
    assert normalization["validation"]["exactEnmlPreserved"] is True
    assert normalization["validation"]["enmlConversionPerformed"] is False
    assert stdout == serialize_enex_normalization(normalization)
