from __future__ import annotations

from pathlib import Path

import pytest

from app.migration.enex import inspect_enex_export

FIXTURE = Path(__file__).parent / "fixtures" / "evernote_export.enex"


def test_enex_inventory_is_read_only_and_preserves_expected_counts() -> None:
    report = inspect_enex_export(FIXTURE)

    assert report.metadata_valid is True
    assert report.note_count == 2
    assert report.deleted_note_count == 1
    assert report.unique_tag_count == 2
    assert report.resource_count == 1
    assert report.embedded_resource_bytes == 5
    assert report.resource_mime_type_counts == {"text/plain": 1}
    assert report.resource_extraction_required is True
    assert report.to_dict()["export"]["exportedAt"] == "2026-08-15T05:00:00Z"
    assert report.to_dict()["validation"]["sourceMutationPerformed"] is False
    assert report.to_dict()["validation"]["targetMutationPerformed"] is False
    assert any(
        issue.code == "embedded-resources-require-controlled-extraction"
        for issue in report.issues
    )


def test_invalid_enex_timestamp_is_reported_without_mutation(tmp_path: Path) -> None:
    payload = FIXTURE.read_text(encoding="utf-8").replace(
        'export-date="20260815T050000Z"',
        'export-date="2026-08-15T05:00:00Z"',
        1,
    )
    invalid = tmp_path / "invalid.enex"
    invalid.write_text(payload, encoding="utf-8")

    report = inspect_enex_export(invalid)

    assert report.metadata_valid is False
    assert any(
        issue.code == "invalid-enex-timestamp" and issue.path == "$.@export-date"
        for issue in report.issues
    )
    assert report.to_dict()["validation"]["sourceMutationPerformed"] is False
    assert report.to_dict()["validation"]["targetMutationPerformed"] is False


def test_resource_hash_mismatch_fails_metadata_validation(tmp_path: Path) -> None:
    payload = FIXTURE.read_text(encoding="utf-8").replace(
        'hash="5d41402abc4b2a76b9719d911017c592"',
        'hash="00000000000000000000000000000000"',
        1,
    )
    invalid = tmp_path / "bad-resource.enex"
    invalid.write_text(payload, encoding="utf-8")

    report = inspect_enex_export(invalid)

    assert report.metadata_valid is False
    assert any(issue.code == "resource-hash-mismatch" for issue in report.issues)


def test_entity_declaration_is_refused_before_xml_parsing(tmp_path: Path) -> None:
    dangerous = tmp_path / "entity.enex"
    dangerous.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE en-export [
  <!ENTITY example "entity-content">
]>
<en-export export-date="20260815T050000Z" application="Evernote" version="1">
  <note><title>&example;</title><content><![CDATA[<en-note>safe</en-note>]]></content></note>
</en-export>
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="entity declaration"):
        inspect_enex_export(dangerous)


def test_symlink_source_is_refused(tmp_path: Path) -> None:
    real = tmp_path / "real.enex"
    real.write_bytes(FIXTURE.read_bytes())
    link = tmp_path / "linked.enex"
    link.symlink_to(real)

    with pytest.raises(ValueError, match="symbolic link"):
        inspect_enex_export(link)
