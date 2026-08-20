"""Unit tests for login-abuse source handling and opaque rate signals."""

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.login_security import (
    request_source,
    source_account_bucket_key,
    source_bucket_key,
)


def _request(*, direct_host: str, forwarded_for: str | None = None) -> SimpleNamespace:
    headers: dict[str, str] = {}
    if forwarded_for is not None:
        headers["x-forwarded-for"] = forwarded_for
    return SimpleNamespace(
        client=SimpleNamespace(host=direct_host),
        headers=headers,
    )


def test_untrusted_direct_peer_cannot_spoof_forwarded_source() -> None:
    settings = Settings(_env_file=None, trusted_proxy_cidrs="")
    request = _request(direct_host="127.0.0.1", forwarded_for="203.0.113.50")

    assert request_source(request, settings) == "127.0.0.1"


def test_trusted_proxy_chain_selects_rightmost_untrusted_address() -> None:
    settings = Settings(_env_file=None, trusted_proxy_cidrs="10.0.0.0/8")
    request = _request(
        direct_host="10.0.0.10",
        forwarded_for="198.51.100.7, 10.0.0.20",
    )

    assert request_source(request, settings) == "198.51.100.7"


def test_malformed_forwarded_chain_falls_back_to_direct_trusted_peer() -> None:
    settings = Settings(_env_file=None, trusted_proxy_cidrs="10.0.0.0/8")
    request = _request(
        direct_host="10.0.0.10",
        forwarded_for="not-an-ip, 10.0.0.20",
    )

    assert request_source(request, settings) == "10.0.0.10"


def test_all_trusted_forwarded_chain_uses_leftmost_address() -> None:
    settings = Settings(_env_file=None, trusted_proxy_cidrs="10.0.0.0/8")
    request = _request(
        direct_host="10.0.0.10",
        forwarded_for="10.0.0.30, 10.0.0.20",
    )

    assert request_source(request, settings) == "10.0.0.30"


def test_invalid_trusted_proxy_cidr_fails_configuration_validation() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, trusted_proxy_cidrs="definitely-not-a-cidr")


def test_bucket_keys_are_stable_opaque_and_username_normalized() -> None:
    source_key = source_bucket_key("198.51.100.7")
    account_key = source_account_bucket_key("198.51.100.7", " Alice ")
    equivalent_account_key = source_account_bucket_key("198.51.100.7", "alice")

    assert len(source_key) == 64
    assert len(account_key) == 64
    assert source_key != account_key
    assert account_key == equivalent_account_key
    assert "198.51.100.7" not in source_key
    assert "198.51.100.7" not in account_key
    assert "alice" not in account_key
