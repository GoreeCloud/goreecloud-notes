from __future__ import annotations

import json
from pathlib import Path

from app.migration.memos import inspect_memos_export

FIXTURE = Path(__file__).parent / "fixtures" / "memos_export_v1.json"


def test_schema_v1_inventory_is_read_only_and_preserves_expected_counts() -> None:
    report = inspect_memos_export(FIXTURE)

    assert report.metadata_valid is True
    assert report.note_count == 2
    assert report.state_counts == {"normal": 1, "trash": 1}
    assert report.unique_tag_count == 2
    assert report.attachment_count == 1
    assert report.local_attachment_count == 1
    assert report.external_attachment_count == 0
    assert report.relation_count == 1
    assert report.relation_type_counts == {"REFERENCE": 1}
    assert report.attachment_binary_recovery_required is True
    assert report.to_dict()["validation"]["sourceMutationPerformed"] is False
    assert any(issue.code == "attachment-binaries-require-separate-recovery" for issue in report.issues)


def test_duplicate_identity_and_invalid_trash_restore_target_fail_validation(tmp_path: Path) -> None:
    payload = json.loads(FIXTURE.read_text())
    payload["notes"][1]["name"] = payload["notes"][0]["name"]
    payload["notes"][1]["uid"] = payload["notes"][0]["uid"]
    payload["notes"][1]["restoreTarget"] = "trash"
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(payload))

    report = inspect_memos_export(invalid)

    assert report.metadata_valid is False
    codes = {issue.code for issue in report.issues if issue.severity == "error"}
    assert {"duplicate-note-name", "duplicate-note-uid", "invalid-restore-target"} <= codes


def test_naive_timestamps_are_rejected(tmp_path: Path) -> None:
    payload = json.loads(FIXTURE.read_text())
    payload["exportedAt"] = "2026-08-14T15:00:00"
    invalid = tmp_path / "naive.json"
    invalid.write_text(json.dumps(payload))

    report = inspect_memos_export(invalid)

    assert report.metadata_valid is False
    assert any(issue.code == "naive-timestamp" and issue.path == "$.exportedAt" for issue in report.issues)


def test_unexported_relation_target_is_warning_not_metadata_failure(tmp_path: Path) -> None:
    payload = json.loads(FIXTURE.read_text())
    payload["notes"][0]["relations"][0]["relatedMemo"] = "memos/comment-999"
    warning = tmp_path / "warning.json"
    warning.write_text(json.dumps(payload))

    report = inspect_memos_export(warning)

    assert report.metadata_valid is True
    assert any(issue.code == "relation-target-not-exported" for issue in report.issues)
