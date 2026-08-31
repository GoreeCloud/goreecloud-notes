import asyncio
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app import portability_api
from app.portability import ExportError, ExportResult


def _fixed_temp_directory(monkeypatch: pytest.MonkeyPatch, path: Path) -> None:
    def create_temp_directory(*, prefix: str) -> str:
        assert prefix == "goreecloud-notes-export-"
        path.mkdir()
        return str(path)

    monkeypatch.setattr(portability_api.tempfile, "mkdtemp", create_temp_directory)


def test_download_filename_uses_utc_and_no_user_input() -> None:
    value = portability_api._download_filename(datetime(2026, 8, 14, 20, 5, 6, tzinfo=UTC))
    assert value == "goreecloud-notes-library-20260814T200506Z.zip"


def test_browser_export_returns_verified_zip_and_removes_temporary_copy(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    temporary_directory = tmp_path / "browser-export"
    _fixed_temp_directory(monkeypatch, temporary_directory)
    attachment_root = tmp_path / "attachments"
    attachment_root.mkdir()
    monkeypatch.setattr(
        portability_api,
        "get_settings",
        lambda: SimpleNamespace(attachment_root=str(attachment_root)),
    )

    def fake_export(db, *, owner, attachment_root, output_path, overwrite):
        assert db == "db"
        assert owner.username == "ladamian"
        assert attachment_root == tmp_path / "attachments"
        assert overwrite is False
        output_path.write_bytes(b"PK\x03\x04verified-export")
        return ExportResult(
            output_path=output_path,
            sha256="a" * 64,
            size_bytes=19,
            note_count=3,
            attachment_count=1,
        )

    monkeypatch.setattr(portability_api, "export_user_library_with_provenance", fake_export)
    context = SimpleNamespace(user=SimpleNamespace(username="ladamian"))

    response = portability_api.download_library_export(db="db", context=context)
    response_path = Path(response.path)

    assert response.media_type == "application/zip"
    assert response.headers["cache-control"] == "no-store, max-age=0"
    assert response.headers["pragma"] == "no-cache"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-goreecloud-export-sha256"] == "a" * 64
    assert "attachment; filename=\"goreecloud-notes-library-" in response.headers["content-disposition"]
    assert response_path.read_bytes() == b"PK\x03\x04verified-export"

    assert response.background is not None
    asyncio.run(response.background())
    assert not temporary_directory.exists()


def test_browser_export_validation_failure_is_opaque_and_cleans_up(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    temporary_directory = tmp_path / "failed-browser-export"
    _fixed_temp_directory(monkeypatch, temporary_directory)
    monkeypatch.setattr(
        portability_api,
        "get_settings",
        lambda: SimpleNamespace(attachment_root=str(tmp_path / "attachments")),
    )

    def fail_export(*args, **kwargs):
        raise ExportError("internal attachment path escaped the root")

    monkeypatch.setattr(portability_api, "export_user_library_with_provenance", fail_export)
    context = SimpleNamespace(user=SimpleNamespace(username="ladamian"))

    with pytest.raises(HTTPException) as caught:
        portability_api.download_library_export(db="db", context=context)

    assert caught.value.status_code == 409
    assert caught.value.detail == "library export could not be completed because stored data failed export validation"
    assert caught.value.headers == {"Cache-Control": "no-store"}
    assert not temporary_directory.exists()
