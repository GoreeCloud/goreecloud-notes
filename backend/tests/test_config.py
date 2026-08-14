"""Tests for fail-closed GoreeCloud Notes runtime configuration."""

import pytest
from pydantic import ValidationError

from app.config import Settings


def _production_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "environment": "production",
        "allowed_origins": "https://notes.goreecloud.com",
        "trusted_proxy_cidrs": "10.20.30.0/24",
        "attachment_root": "/var/lib/goreecloud-notes/attachments",
        "database_password_file": "/run/secrets/postgres_password",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_development_defaults_remain_explicitly_permitted() -> None:
    settings = Settings(_env_file=None)

    assert settings.environment == "development"
    assert settings.secure_cookies is False
    assert settings.trusted_proxy_networks == ()
    assert settings.cors_origins == ["http://127.0.0.1:5173", "http://localhost:5173"]


def test_production_accepts_explicit_private_publication_boundary() -> None:
    settings = _production_settings()

    assert settings.is_production is True
    assert settings.secure_cookies is True
    assert settings.cors_origins == ["https://notes.goreecloud.com"]
    assert len(settings.trusted_proxy_networks) == 1


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"allowed_origins": "http://notes.goreecloud.com"}, "must use https"),
        ({"allowed_origins": "https://localhost"}, "must not use localhost"),
        ({"allowed_origins": "https://127.0.0.1"}, "must not use loopback"),
        ({"trusted_proxy_cidrs": ""}, "trusted proxy CIDRs"),
        ({"attachment_root": "./attachments"}, "attachment_root must be an absolute path"),
        ({"database_password_file": None}, "requires database_password_file"),
        ({"database_password_file": "secrets/postgres_password"}, "database_password_file must be an absolute path"),
    ],
)
def test_production_rejects_unresolved_security_or_storage_defaults(
    overrides: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        _production_settings(**overrides)


def test_credentialed_cors_rejects_wildcards_in_every_environment() -> None:
    with pytest.raises(ValidationError, match="wildcard CORS origins"):
        Settings(_env_file=None, allowed_origins="https://*.example.com")


def test_api_prefix_must_be_stable_absolute_path() -> None:
    with pytest.raises(ValidationError, match="api_prefix"):
        Settings(_env_file=None, api_prefix="api/v1")

    with pytest.raises(ValidationError, match="api_prefix"):
        Settings(_env_file=None, api_prefix="/api/v1/")
