"""Privacy-first HTTP response hardening for the GoreeCloud Notes API."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

_API_CONTENT_SECURITY_POLICY = (
    "default-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)

_GLOBAL_SECURITY_HEADERS = {
    "Cross-Origin-Opener-Policy": "same-origin",
    "Permissions-Policy": (
        "accelerometer=(), autoplay=(), camera=(), geolocation=(), gyroscope=(), "
        "magnetometer=(), microphone=(), payment=(), usb=()"
    ),
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}


class PrivateResponseHeadersMiddleware(BaseHTTPMiddleware):
    """Apply conservative browser headers and disable caching for private API data.

    GoreeCloud Notes is a private knowledge application. API responses may contain
    note content, account state, search results, attachment metadata, or export data,
    so the API path is always treated as non-cacheable even when an individual route
    forgets to set a cache policy. Frontend document CSP/HSTS remain publication-layer
    responsibilities because the final static-serving and Caddy topology are separate
    production gates.
    """

    def __init__(self, app, *, api_prefix: str) -> None:  # type: ignore[no-untyped-def]
        super().__init__(app)
        self.api_prefix = api_prefix.rstrip("/")

    def _is_api_path(self, path: str) -> bool:
        return path == self.api_prefix or path.startswith(f"{self.api_prefix}/")

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)

        for name, value in _GLOBAL_SECURITY_HEADERS.items():
            response.headers[name] = value

        if self._is_api_path(request.url.path):
            response.headers["Cache-Control"] = "private, no-store"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            response.headers["Content-Security-Policy"] = _API_CONTENT_SECURITY_POLICY

        return response
