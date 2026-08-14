"""Authentication and browser-session security for GoreeCloud Notes."""

from __future__ import annotations

from base64 import urlsafe_b64decode, urlsafe_b64encode
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256, scrypt
from hmac import compare_digest
from secrets import token_bytes, token_urlsafe
from unicodedata import normalize
from uuid import UUID

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .database import get_db
from .models import AuthSession, User, UserCredential

SESSION_COOKIE_NAME = "goreecloud_notes_session"
CSRF_COOKIE_NAME = "goreecloud_notes_csrf"
CSRF_HEADER_NAME = "X-CSRF-Token"
MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 1024

_SCRYPT_N = 32_768
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 64
_SCRYPT_MAXMEM = 64 * 1024 * 1024
_PASSWORD_FORMAT = "scrypt-v1"
_DUMMY_PASSWORD_SALT = b"goreecloud-notes-login-failure"


@dataclass(frozen=True, slots=True)
class AuthContext:
    """Authenticated user plus the server-side session that proved identity."""

    user: User
    session: AuthSession


@dataclass(frozen=True, slots=True)
class IssuedSession:
    """Raw browser secrets produced for one newly created session."""

    token: str
    csrf_token: str
    expires_at: datetime


def normalize_username(username: str) -> str:
    """Return the stable comparison form used for account lookup."""

    return normalize("NFKC", username).strip().casefold()


def validate_password(password: str) -> None:
    """Enforce the shared password boundary used by API and CLI mutations."""

    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must contain at least {MIN_PASSWORD_LENGTH} characters.")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise ValueError(f"Password must not exceed {MAX_PASSWORD_LENGTH} characters.")


def _encode_bytes(value: bytes) -> str:
    return urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode_bytes(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return urlsafe_b64decode(value + padding)


def _derive_password(password: str, *, salt: bytes, length: int = _SCRYPT_DKLEN) -> bytes:
    return scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=length,
        maxmem=_SCRYPT_MAXMEM,
    )


def hash_password(password: str) -> str:
    """Hash a password using salted scrypt and a versioned storage envelope."""

    validate_password(password)

    salt = token_bytes(16)
    derived = _derive_password(password, salt=salt)
    return "$".join(
        (
            _PASSWORD_FORMAT,
            str(_SCRYPT_N),
            str(_SCRYPT_R),
            str(_SCRYPT_P),
            _encode_bytes(salt),
            _encode_bytes(derived),
        )
    )


def verify_password(password: str, encoded_hash: str) -> bool:
    """Verify a password without raising for malformed stored values."""

    try:
        algorithm, raw_n, raw_r, raw_p, raw_salt, raw_expected = encoded_hash.split("$", maxsplit=5)
        if algorithm != _PASSWORD_FORMAT:
            return False

        n = int(raw_n)
        r = int(raw_r)
        p = int(raw_p)
        if (n, r, p) != (_SCRYPT_N, _SCRYPT_R, _SCRYPT_P):
            return False

        salt = _decode_bytes(raw_salt)
        expected = _decode_bytes(raw_expected)
        actual = _derive_password(password, salt=salt, length=len(expected))
    except (TypeError, ValueError):
        return False

    return compare_digest(actual, expected)


def _run_dummy_password_work(password: str) -> None:
    """Pay the normal scrypt cost for an unknown account without storing output."""

    _derive_password(password, salt=_DUMMY_PASSWORD_SALT)


def secret_digest(secret: str) -> str:
    """Return the irreversible database representation of a session secret."""

    return sha256(secret.encode("utf-8")).hexdigest()


def _credential_for_user(db: Session, user_id: UUID) -> UserCredential | None:
    return db.scalar(select(UserCredential).where(UserCredential.user_id == user_id))


def verify_user_password(db: Session, *, user: User, password: str) -> bool:
    """Verify one authenticated user's current password."""

    credential = _credential_for_user(db, user.id)
    return credential is not None and verify_password(password, credential.password_hash)


def revoke_user_sessions(db: Session, *, user_id: UUID) -> None:
    """Revoke every server-side browser session for one account."""

    db.execute(delete(AuthSession).where(AuthSession.user_id == user_id))


def replace_user_password(db: Session, *, user: User, new_password: str) -> None:
    """Replace credential material and revoke every existing browser session.

    This primitive is shared by authenticated password rotation and the private
    administrative CLI recovery path. It intentionally does not commit so the
    caller controls transaction boundaries.
    """

    validate_password(new_password)
    credential = _credential_for_user(db, user.id)
    if credential is None:
        raise ValueError("Account credential is unavailable.")

    credential.password_hash = hash_password(new_password)
    credential.password_changed_at = datetime.now(UTC)
    revoke_user_sessions(db, user_id=user.id)
    db.flush()


def authenticate_user(db: Session, *, username: str, password: str) -> User | None:
    """Authenticate one active account with a generic failure path."""

    normalized = normalize_username(username)
    if not normalized or not password:
        return None

    row = db.execute(
        select(User, UserCredential)
        .join(UserCredential, UserCredential.user_id == User.id)
        .where(User.username_normalized == normalized)
    ).first()

    if row is None:
        _run_dummy_password_work(password)
        return None

    user, credential = row
    password_matches = verify_password(password, credential.password_hash)
    if not user.is_active or not password_matches:
        return None

    return user


def issue_session(db: Session, *, user: User, settings: Settings) -> IssuedSession:
    """Create one opaque database-backed browser session."""

    now = datetime.now(UTC)
    db.execute(delete(AuthSession).where(AuthSession.expires_at <= now))

    token = token_urlsafe(48)
    csrf_token = token_urlsafe(32)
    expires_at = now + timedelta(seconds=settings.session_ttl_seconds)
    db.add(
        AuthSession(
            user_id=user.id,
            token_hash=secret_digest(token),
            csrf_token_hash=secret_digest(csrf_token),
            expires_at=expires_at,
        )
    )
    db.flush()
    return IssuedSession(token=token, csrf_token=csrf_token, expires_at=expires_at)


def set_session_cookies(response: Response, issued: IssuedSession, settings: Settings) -> None:
    """Write the HttpOnly session cookie and readable double-submit CSRF cookie."""

    cookie_args = {
        "max_age": settings.session_ttl_seconds,
        "secure": settings.secure_cookies,
        "samesite": "strict",
        "path": "/",
    }
    response.set_cookie(
        SESSION_COOKIE_NAME,
        issued.token,
        httponly=True,
        **cookie_args,
    )
    response.set_cookie(
        CSRF_COOKIE_NAME,
        issued.csrf_token,
        httponly=False,
        **cookie_args,
    )


def clear_session_cookies(response: Response, settings: Settings) -> None:
    """Expire both browser authentication cookies."""

    response.delete_cookie(
        SESSION_COOKIE_NAME,
        path="/",
        secure=settings.secure_cookies,
        httponly=True,
        samesite="strict",
    )
    response.delete_cookie(
        CSRF_COOKIE_NAME,
        path="/",
        secure=settings.secure_cookies,
        httponly=False,
        samesite="strict",
    )


def get_current_auth_context(
    request: Request,
    db: Session = Depends(get_db),
) -> AuthContext:
    """Require a live opaque session and an active user."""

    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required")

    now = datetime.now(UTC)
    row = db.execute(
        select(AuthSession, User)
        .join(User, User.id == AuthSession.user_id)
        .where(
            AuthSession.token_hash == secret_digest(token),
            AuthSession.expires_at > now,
            User.is_active.is_(True),
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required")

    session, user = row
    return AuthContext(user=user, session=session)


def require_csrf(
    request: Request,
    context: AuthContext = Depends(get_current_auth_context),
) -> AuthContext:
    """Require the CSRF cookie/header pair for authenticated state changes."""

    cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
    header_token = request.headers.get(CSRF_HEADER_NAME)
    if (
        not cookie_token
        or not header_token
        or not compare_digest(cookie_token, header_token)
        or not compare_digest(secret_digest(header_token), context.session.csrf_token_hash)
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="csrf validation failed")

    return context


def revoke_session(db: Session, context: AuthContext) -> None:
    """Delete one authenticated session from the server-side session store."""

    db.delete(context.session)
