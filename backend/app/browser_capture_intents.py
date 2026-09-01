"""Replay-safe in-process intent guard for future GoreeCloud Browser capture writes.

This module deliberately stores no captured page content. It provides a bounded Development
primitive for issuing and consuming opaque one-time intents while production persistence,
transport authorization, and the write endpoint remain fail-closed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from threading import Lock

DEFAULT_INTENT_TTL = timedelta(minutes=5)
MAX_INTENT_TTL = timedelta(minutes=15)
MAX_ACTIVE_INTENTS = 4096
TOKEN_BYTES = 32


class BrowserCaptureIntentRejected(ValueError):
    """Raised for expired, replayed, unknown, or cross-owner capture intents."""


@dataclass(frozen=True, slots=True)
class BrowserCaptureIntent:
    token: str
    expires_at: datetime


@dataclass(slots=True)
class _StoredIntent:
    owner_id: str
    expires_at: datetime


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("capture intent time must include timezone information")
    return value.astimezone(timezone.utc)


def _token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class BrowserCaptureIntentGuard:
    """Bounded, process-local one-time intent guard.

    Only owner ID, opaque-token digest, and expiry are retained. Consumed intents are removed
    immediately, making replay, cross-owner reuse, expiry, and unknown tokens indistinguishable
    through one rejection boundary.
    """

    def __init__(self, *, max_active: int = MAX_ACTIVE_INTENTS) -> None:
        if max_active <= 0 or max_active > MAX_ACTIVE_INTENTS:
            raise ValueError("max_active must be within the reviewed intent bound")
        self._max_active = max_active
        self._intents: dict[str, _StoredIntent] = {}
        self._lock = Lock()

    def issue(
        self,
        owner_id: str,
        *,
        now: datetime,
        ttl: timedelta = DEFAULT_INTENT_TTL,
    ) -> BrowserCaptureIntent:
        owner_id = owner_id.strip()
        if not owner_id:
            raise ValueError("capture intent owner is required")
        if ttl <= timedelta(0) or ttl > MAX_INTENT_TTL:
            raise ValueError("capture intent TTL is outside the reviewed bound")
        issued_at = _aware_utc(now)
        expires_at = issued_at + ttl

        with self._lock:
            self._prune_locked(issued_at)
            if len(self._intents) >= self._max_active:
                raise BrowserCaptureIntentRejected("capture intent unavailable")
            token = secrets.token_urlsafe(TOKEN_BYTES)
            digest = _token_digest(token)
            while digest in self._intents:
                token = secrets.token_urlsafe(TOKEN_BYTES)
                digest = _token_digest(token)
            self._intents[digest] = _StoredIntent(owner_id=owner_id, expires_at=expires_at)

        return BrowserCaptureIntent(token=token, expires_at=expires_at)

    def consume(self, owner_id: str, token: str, *, now: datetime) -> None:
        owner_id = owner_id.strip()
        token = token.strip()
        checked_at = _aware_utc(now)
        if not owner_id or not token:
            raise BrowserCaptureIntentRejected("capture intent rejected")

        digest = _token_digest(token)
        with self._lock:
            stored = self._intents.pop(digest, None)
            self._prune_locked(checked_at)

        if stored is None or stored.owner_id != owner_id or stored.expires_at <= checked_at:
            raise BrowserCaptureIntentRejected("capture intent rejected")

    def _prune_locked(self, now: datetime) -> None:
        expired = [digest for digest, stored in self._intents.items() if stored.expires_at <= now]
        for digest in expired:
            self._intents.pop(digest, None)
