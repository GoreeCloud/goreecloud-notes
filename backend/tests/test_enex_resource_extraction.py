from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from app.migration.__main__ import main as migration_main
from app.migration.enex_resources import (
    EVIDENCE_FILENAME,
    extract_enex_resources,
    serialize_enex_resource_evidence,
)

FIXTURE = Path(__file__).parent / "fixtures" / "evernote_export.enex"
HELLO_SHA256 = "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"


def _duplicate_resource_enex(tmp_path: Path) -> Path:
    path = tmp_path / "duplicate.enex"
    resource = """
    <resource>
      <data encoding="base64" hash="5d41402abc4b2a76b9719d911017c592">aGVsbG8=</data>
      <mime>text/plain</mime>
      <resource-attributes><file-name>hello.txt</file-name></resource-attributes>
    </resource>
"""
    path.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<en-export export-date="20260815T050000Z" application="Evernote/10.0" version="10.0">
  <note>
    <title>Duplicate Resource Fixture</title>
    <content><![CDATA[<en-note>duplicate resources</en-note>]]></content>
{resource}{resource}  </note>
</en-export>
""",
        encoding="utf-8",
    )
    return path


def test_enex_resource_extraction_is_deterministic_and_hash_evidenced(tmp_path: Path) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"

    first = extract_enex_resources(FIXTURE, first_root)
    second = extract_enex_resources(FIXTURE, second_root)

    assert first == second
    assert first["format"] == "goreecloud-notes-enex-resource-evidence"
    assert first["schemaVersion"] == 1
    assert first["extraction"] == {
        "complete": True,
        "resourceCount": 1,
        "extractedBytes": 5,
        "evidenceFile": EVIDENCE_FILENAME,
        "sourceMutationPerformed": False,
        "targetDatabaseMutationPerformed": False,
        "outputOverwritePerformed": False,
    }

    resource = first["resources"][0]
    assert resource["source"] == {
        "fileName": "hello.txt",
        "evernoteMd5": "5d41402abc4b2a76b9719d911017c592",
    }
    assert resource["output"]["sha256"] == HELLO_SHA256
    assert resource["output"]["sizeBytes"] == 5
    assert resource["duplicateOf"] is None

    extracted = first_root / resource["output"]["relativePath"]
    assert extracted.read_bytes() == b"hello"

    evidence_text = (first_root / EVIDENCE_FILENAME).read_text(encoding="utf-8")
    assert evidence_text == serialize_enex_resource_evidence(first)
    assert json.loads(evidence_text) == first


def test_enex_resource_extraction_records_duplicate_content_without_path_collision(tmp_path: Path) -> None:
    source = _duplicate_resource_enex(tmp_path)
    evidence = extract_enex_resources(source, tmp_path / "output")

    assert evidence["extraction"]["resourceCount"] == 2
    first, second = evidence["resources"]
    assert first["output"]["sha256"] == HELLO_SHA256
    assert second["output"]["sha256"] == HELLO_SHA256
    assert first["output"]["relativePath"] != second["output"]["relativePath"]
    assert second["duplicateOf"] == first["output"]["relativePath"]


def test_enex_resource_extraction_refuses_preexisting_output_root(tmp_path: Path) -> None:
    output = tmp_path / "output"
    output.mkdir()

    with pytest.raises(ValueError, match="must not already exist"):
        extract_enex_resources(FIXTURE, output)

    assert list(output.iterdir()) == []


def test_enex_resource_extraction_refuses_symbolic_link_output(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    output = tmp_path / "output"
    output.symlink_to(real, target_is_directory=True)

    with pytest.raises(ValueError, match="must not be a symbolic link"):
        extract_enex_resources(FIXTURE, output)


def test_enex_resource_extraction_refuses_oversized_resource_before_writing(tmp_path: Path) -> None:
    output = tmp_path / "output"

    with pytest.raises(ValueError, match="per-resource limit"):
        extract_enex_resources(FIXTURE, output, max_resource_bytes=4)

    assert not output.exists()


def test_enex_resource_extraction_refuses_excessive_resource_count_before_writing(tmp_path: Path) -> None:
    source = _duplicate_resource_enex(tmp_path)
    output = tmp_path / "output"

    with pytest.raises(ValueError, match="resource extraction limit"):
        extract_enex_resources(source, output, max_resources=1)

    assert not output.exists()


def test_enex_resource_extraction_requires_metadata_valid_source(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.enex"
    invalid.write_text(
        FIXTURE.read_text(encoding="utf-8").replace(
            'hash="5d41402abc4b2a76b9719d911017c592"',
            'hash="00000000000000000000000000000000"',
            1,
        ),
        encoding="utf-8",
    )
    output = tmp_path / "output"

    with pytest.raises(ValueError, match="metadata-valid"):
        extract_enex_resources(invalid, output)

    assert not output.exists()


def test_enex_resource_extraction_cli_emits_same_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = tmp_path / "cli-output"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "python -m app.migration",
            "extract-enex-resources",
            str(FIXTURE),
            str(output),
        ],
    )

    assert migration_main() == 0
    stdout = capsys.readouterr().out
    evidence = json.loads(stdout)

    assert evidence["format"] == "goreecloud-notes-enex-resource-evidence"
    assert evidence["extraction"]["complete"] is True
    assert stdout == (output / EVIDENCE_FILENAME).read_text(encoding="utf-8")
