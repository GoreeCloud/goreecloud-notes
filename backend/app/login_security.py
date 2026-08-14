"""Bounded login abuse controls for GoreeCloud Notes.

The limiter intentionally protects both a source+account signal and a source-wide
signal. It never permanently locks an account, and forwarded client addresses are
trusted only when the direct peer belongs to an explicitly configured proxy CIDR.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from ipaddress import IPv4Address, IPv6Address, ip_address
from math import ceil

from fastapi import Request
from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, delete, select, text
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.orm import Mapped, Session, mapped_column

from .auth import normalize_username
from .config import Settings
from .database import Base


class LoginRateBucket(Base):
    """Short-lived, data-minimized failure state for login throttling."""

    __tablename__ = "login_rate_buckets"
    __table_args__ = (
        CheckConstraint(
            "scope IN ('source', 'source_account')",
            name="ck_login_rate_buckets_scope",
        ),
        CheckConstraint("failure_count >= 0", name="ck_login_rate_buckets_failure_count_nonnegative"),
        Index("ix_login_rate_buckets_expires_at", "expires_at"),
    )

    bucket_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    blocked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


@dataclass(frozen=True, slots=True)
class LoginRateState:
    """Rate-limit decision returned to the login route."""

    retry_after_seconds: int | None = None

    @property
    def blocked(self) -> bool:
        return self.retry_after_seconds is not None


def _in_trusted_networks(address: IPv4Address | IPv6Address, settings: Settings) -> bool:
    return any(address in network for network in settings.trusted_proxy_networks)


def request_source(request: Request, settings: Settings) -> str:
    """Return the canonical login source without trusting spoofable forwarding.

    `X-Forwarded-For` is considered only when the direct TCP peer is inside an
    explicitly configured trusted proxy CIDR. A malformed forwarded chain falls
    back to the direct peer rather than guessing. When trusted proxies form a
    chain, the rightmost untrusted address is the effective source.
    """

    direct_host = request.client.host if request.client is not None else "unknown"
    try:
        direct_address = ip_address(direct_host)
    except ValueError:
        return direct_host

    forwarded = request.headers.get("x-forwarded-for")
    if not forwarded or not _in_trusted_networks(direct_address, settings):
        return direct_address.compressed

    try:
        forwarded_addresses = [
            ip_address(part.strip())
            for part in forwarded.split(",")
            if part.strip()
        ]
    except ValueError:
        return direct_address.compressed

    if not forwarded_addresses:
        return direct_address.compressed

    for address in reversed(forwarded_addresses):
        if not _in_trusted_networks(address, settings):
            return address.compressed

    return forwarded_addresses[0].compressed


def _signal_digest(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def source_bucket_key(source: str) -> str:
    return _signal_digest(f"source\x00{source}")


def source_account_bucket_key(source: str, username: str) -> str:
    return _signal_digest(f"source-account\x00{source}\x00{normalize_username(username)}")


def _bucket_expiry(now: datetime, settings: Settings) -> datetime:
    return now + timedelta(seconds=settings.login_rate_state_ttl_seconds)


def _ensure_bucket(
    db: Session,
    *,
    bucket_key: str,
    scope: str,
    now: datetime,
    settings: Settings,
) -> LoginRateBucket:
    """Create a bucket race-safely, then lock it for mutation."""

    db.execute(
        postgresql_insert(LoginRateBucket)
        .values(
            bucket_key=bucket_key,
            scope=scope,
            failure_count=0,
            window_started_at=now,
            expires_at=_bucket_expiry(now, settings),
        )
        .on_conflict_do_nothing(index_elements=[LoginRateBucket.bucket_key])
    )
    bucket = db.scalar(
        select(LoginRateBucket)
        .where(LoginRateBucket.bucket_key == bucket_key)
        .with_for_update()
    )
    if bucket is None:  # pragma: no cover - defensive database invariant
        raise RuntimeError("login rate bucket could not be resolved")
    return bucket


def _refresh_bucket_window(bucket: LoginRateBucket, now: datetime, settings: Settings) -> None:
    window = timedelta(seconds=settings.login_rate_window_seconds)
    if bucket.window_started_at + window <= now:
        bucket.failure_count = 0
        bucket.window_started_at = now
        bucket.blocked_until = None

    if bucket.blocked_until is not None and bucket.blocked_until <= now:
        bucket.failure_count = 0
        bucket.window_started_at = now
        bucket.blocked_until = None

    bucket.expires_at = _bucket_expiry(now, settings)


def _retry_after(bucket: LoginRateBucket, now: datetime) -> int | None:
    if bucket.blocked_until is None or bucket.blocked_until <= now:
        return None
    return max(1, ceil((bucket.blocked_until - now).total_seconds()))


def check_login_rate_limit(
    db: Session,
    *,
    source: str,
    username: str,
    settings: Settings,
) -> LoginRateState:
    """Return a pre-authentication throttling decision and prune stale state."""

    now = datetime.now(UTC)
    db.execute(delete(LoginRateBucket).where(LoginRateBucket.expires_at <= now))

    retry_after_values: list[int] = []
    for key, scope in (
        (source_bucket_key(source), "source"),
        (source_account_bucket_key(source, username), "source_account"),
    ):
        bucket = db.scalar(
            select(LoginRateBucket)
            .where(LoginRateBucket.bucket_key == key)
            .with_for_update()
        )
        if bucket is None:
            continue
        _refresh_bucket_window(bucket, now, settings)
        retry_after = _retry_after(bucket, now)
        if retry_after is not None:
            retry_after_values.append(retry_after)

    if retry_after_values:
        return LoginRateState(retry_after_seconds=max(retry_after_values))
    return LoginRateState()


def record_login_failure(
    db: Session,
    *,
    source: str,
    username: str,
    settings: Settings,
) -> LoginRateState:
    """Record one generic login failure and apply bounded cooldowns."""

    now = datetime.now(UTC)
    retry_after_values: list[int] = []
    bucket_specs = (
        (
            source_bucket_key(source),
            "source",
            settings.login_rate_source_failures,
        ),
        (
            source_account_bucket_key(source, username),
            "source_account",
            settings.login_rate_account_failures,
        ),
    )

    for key, scope, threshold in bucket_specs:
        bucket = _ensure_bucket(
            db,
            bucket_key=key,
            scope=scope,
            now=now,
            settings=settings,
        )
        _refresh_bucket_window(bucket, now, settings)
        bucket.failure_count += 1
        bucket.last_failed_at = now
        bucket.expires_at = _bucket_expiry(now, settings)
        if bucket.failure_count >= threshold:
            bucket.blocked_until = now + timedelta(seconds=settings.login_rate_cooldown_seconds)
        retry_after = _retry_after(bucket, now)
        if retry_after is not None:
            retry_after_values.append(retry_after)

    if retry_after_values:
        return LoginRateState(retry_after_seconds=max(retry_after_values))
    return LoginRateState()


def record_login_success(
    db: Session,
    *,
    source: str,
    username: str,
) -> None:
    """Clear only the successful source+account bucket.

    Source-wide failure history intentionally remains so rotating usernames does
    not evade the source-wide protection.
    """

    db.execute(
        delete(LoginRateBucket).where(
            LoginRateBucket.bucket_key == source_account_bucket_key(source, username)
        )
    )
