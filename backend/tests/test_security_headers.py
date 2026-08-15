"""Tests for centralized privacy-first HTTP response headers."""

from fastapi import FastAPI, Response
from fastapi.testclient import TestClient

from app.security_headers import PrivateResponseHeadersMiddleware


def _client() -> TestClient:
    app = FastAPI()
    app.add_middleware(PrivateResponseHeadersMiddleware, api_prefix="/api/v1")

    @app.get("/api/v1/private")
    def private_response(response: Response) -> dict[str, str]:
        # Prove the centralized private boundary wins over an accidentally cacheable route.
        response.headers["Cache-Control"] = "public, max-age=3600"
        return {"status": "ok"}

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return TestClient(app)


def test_private_api_responses_are_non_cacheable_and_browser_hardened() -> None:
    response = _client().get("/api/v1/private")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["pragma"] == "no-cache"
    assert response.headers["expires"] == "0"
    assert response.headers["content-security-policy"] == (
        "default-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    )
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["cross-origin-opener-policy"] == "same-origin"
    assert "camera=()" in response.headers["permissions-policy"]
    assert "microphone=()" in response.headers["permissions-policy"]


def test_liveness_keeps_global_hardening_without_private_api_cache_policy() -> None:
    response = _client().get("/health")

    assert response.status_code == 200
    assert "cache-control" not in response.headers
    assert "content-security-policy" not in response.headers
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
