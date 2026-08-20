from pathlib import Path

from fastapi.testclient import TestClient

from app import main
from app.main import app

client = TestClient(app)


def test_health_is_non_sensitive_and_available() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "goreecloud-notes-api",
    }


def test_attachment_storage_readiness_requires_existing_directory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    ready_root = tmp_path / "attachments"
    ready_root.mkdir()
    monkeypatch.setattr(main.settings, "attachment_root", str(ready_root))

    assert main._attachment_storage_ready() is True

    missing_root = tmp_path / "missing"
    monkeypatch.setattr(main.settings, "attachment_root", str(missing_root))
    assert main._attachment_storage_ready() is False

    file_root = tmp_path / "not-a-directory"
    file_root.write_text("not storage", encoding="utf-8")
    monkeypatch.setattr(main.settings, "attachment_root", str(file_root))
    assert main._attachment_storage_ready() is False


def test_attachment_storage_readiness_rejects_symlink_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    actual_root = tmp_path / "actual"
    actual_root.mkdir()
    linked_root = tmp_path / "linked"
    linked_root.symlink_to(actual_root, target_is_directory=True)
    monkeypatch.setattr(main.settings, "attachment_root", str(linked_root))

    assert main._attachment_storage_ready() is False


def test_versioned_api_metadata() -> None:
    response = client.get("/api/v1/meta")

    assert response.status_code == 200
    assert response.json() == {
        "product": "GoreeCloud Notes",
        "api_version": "v1",
        "status": "native-foundation",
    }
