from datetime import datetime, timedelta, timezone

import pytest

from app.browser_capture_intents import (
    BrowserCaptureIntentGuard,
    BrowserCaptureIntentRejected,
)


NOW = datetime(2026, 9, 1, 16, 0, tzinfo=timezone.utc)


def test_intent_is_owner_scoped_and_consumed_once():
    guard = BrowserCaptureIntentGuard()
    intent = guard.issue("owner-a", now=NOW)

    guard.consume("owner-a", intent.token, now=NOW + timedelta(seconds=1))

    with pytest.raises(BrowserCaptureIntentRejected):
        guard.consume("owner-a", intent.token, now=NOW + timedelta(seconds=2))


def test_cross_owner_attempt_does_not_consume_rightful_intent():
    guard = BrowserCaptureIntentGuard()
    intent = guard.issue("owner-a", now=NOW)

    with pytest.raises(BrowserCaptureIntentRejected):
        guard.consume("owner-b", intent.token, now=NOW + timedelta(seconds=1))

    guard.consume("owner-a", intent.token, now=NOW + timedelta(seconds=2))


def test_expired_and_unknown_intents_share_rejection_boundary():
    guard = BrowserCaptureIntentGuard()
    intent = guard.issue("owner-a", now=NOW, ttl=timedelta(seconds=5))

    with pytest.raises(BrowserCaptureIntentRejected, match="capture intent rejected"):
        guard.consume("owner-a", intent.token, now=NOW + timedelta(seconds=5))
    with pytest.raises(BrowserCaptureIntentRejected, match="capture intent rejected"):
        guard.consume("owner-a", "unknown-token", now=NOW + timedelta(seconds=5))


def test_guard_is_bounded_and_prunes_expired_intents():
    guard = BrowserCaptureIntentGuard(max_active=1)
    guard.issue("owner-a", now=NOW, ttl=timedelta(seconds=1))

    with pytest.raises(BrowserCaptureIntentRejected):
        guard.issue("owner-a", now=NOW)

    replacement = guard.issue("owner-a", now=NOW + timedelta(seconds=1))
    assert replacement.token


def test_guard_rejects_unreviewed_ttl_and_naive_time():
    guard = BrowserCaptureIntentGuard()
    with pytest.raises(ValueError):
        guard.issue("owner-a", now=NOW, ttl=timedelta(minutes=16))
    with pytest.raises(ValueError):
        guard.issue("owner-a", now=datetime(2026, 9, 1, 16, 0))
