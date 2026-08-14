"""Tests for the non-destructive production runtime preflight."""

from pathlib import Path

from app.config import Settings
from app.production_check import production_runtime_report


def _settings(tmp_path: Path) -> Settings:
    secret = tmp_path / "postgres_password"
    secret.write_text("production-only-secret\n", encoding="utf-8")
    secret.chmod(0o640)
    attachment_root = tmp_path / "attachments"
    attachment_root.mkdir()
    return Settings(
        _env_file=None,
        environment="production",
        allowed_origins="https://notes.goreecloud.com",
        trusted_proxy_cidrs="10.20.30.0/24",
        attachment_root=str(attachment_root),
        database_password_file=str(secret),
    )


def test_production_preflight_passes_only_static_runtime_boundary(tmp_path: Path) -> None:
    report = production_runtime_report(_settings(tmp_path))

    assert report["status"] == "pass"
    assert all(report["checks"].values())
    assert report["nonDestructive"] is True
    assert report["liveDependencyValidationPerformed"] is False
    assert report["productionApprovalGranted"] is False


def test_production_preflight_fails_when_secret_file_becomes_empty(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    Path(settings.database_password_file or "").write_text("", encoding="utf-8")

    report = production_runtime_report(settings)

    assert report["status"] == "fail"
    assert report["checks"]["databaseSecretFileReady"] is False
    assert report["productionApprovalGranted"] is False


def test_production_preflight_fails_when_attachment_root_is_missing(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    Path(settings.attachment_root).rmdir()

    report = production_runtime_report(settings)

    assert report["status"] == "fail"
    assert report["checks"]["attachmentRootReady"] is False


def test_production_preflight_rejects_world_readable_secret_file(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    secret = Path(settings.database_password_file or "")
    secret.chmod(0o644)

    report = production_runtime_report(settings)

    assert report["status"] == "fail"
    assert report["checks"]["databaseSecretFileReady"] is False
