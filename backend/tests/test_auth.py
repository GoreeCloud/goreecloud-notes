"""Tests for GoreeCloud Notes authentication primitives."""

from app.auth import hash_password, normalize_username, secret_digest, verify_password


def test_password_hash_round_trip_and_wrong_password_rejection() -> None:
    encoded = hash_password("correct horse battery staple")

    assert encoded.startswith("scrypt-v1$")
    assert "correct horse battery staple" not in encoded
    assert verify_password("correct horse battery staple", encoded) is True
    assert verify_password("wrong password", encoded) is False


def test_password_verification_rejects_malformed_or_unknown_formats() -> None:
    assert verify_password("anything", "not-a-password-hash") is False
    assert verify_password("anything", "unknown$32768$8$1$Zm9v$YmFy") is False


def test_username_normalization_is_casefolded_trimmed_and_unicode_normalized() -> None:
    assert normalize_username("  LaDamian  ") == "ladamian"
    assert normalize_username("Ａlice") == "alice"


def test_session_secret_digest_is_stable_and_does_not_preserve_secret() -> None:
    digest = secret_digest("browser-secret")

    assert len(digest) == 64
    assert digest == secret_digest("browser-secret")
    assert digest != "browser-secret"
