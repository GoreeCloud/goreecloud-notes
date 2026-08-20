# Security Header Boundary

GoreeCloud Notes uses layered HTTP response hardening rather than treating one application middleware as the entire publication-security model.

## Application boundary

`backend/app/security_headers.py` applies conservative browser-facing headers to application responses and a stricter cache/CSP boundary to `/api/v1` responses.

Global response protections include:

- `Cross-Origin-Opener-Policy: same-origin`;
- `Cross-Origin-Resource-Policy: same-origin`;
- `Permissions-Policy` disabling browser capabilities that Notes does not require;
- `Referrer-Policy: no-referrer`;
- `X-Content-Type-Options: nosniff`; and
- `X-Frame-Options: DENY`.

Private API responses additionally receive the restrictive API CSP, `Pragma: no-cache`, `Expires: 0`, and a fail-safe private `no-store` policy when the route did not already provide a safe `no-store` contract.

Existing route-level `Cache-Control: no-store` values are preserved exactly. The middleware must not rewrite a safe established cache contract merely to normalize formatting.

## Why CORP is global

`Cross-Origin-Resource-Policy: same-origin` prevents unrelated origins from embedding browser-managed GoreeCloud Notes resources. It complements the existing `Cross-Origin-Opener-Policy: same-origin` process-isolation boundary without enabling cross-origin isolation features that Notes has not explicitly accepted.

This change does not add `Cross-Origin-Embedder-Policy`. Notes does not currently require SharedArrayBuffer or another capability that justifies imposing COEP and its stricter subresource requirements.

## Publication boundary

Application middleware does **not** claim responsibility for final browser-document publication policy. The production frontend/static-serving and reverse-proxy design remains a separate target-environment gate.

Before Stable production approval, the actual publication path must separately validate:

- the browser-document Content Security Policy appropriate to the final frontend assets and application behavior;
- HTTP Strict Transport Security at the approved HTTPS publication layer;
- exact Caddy routing and trusted-proxy behavior;
- private DNS and NetBird reconstruction;
- security-header preservation through the reverse proxy;
- publication-layer abuse controls and monitoring; and
- real browser/network acceptance against the exact deployed candidate.

A green source-level header test or Production Runtime Preflight does not grant production publication approval.

## Validation

`backend/tests/test_security_headers.py` protects the centralized response contract, including the global same-origin resource policy on private API, existing no-store API, and liveness responses.

The exact branch head under review must pass Continuous Integration before this source checkpoint is considered fully validated. Production Runtime Preflight uses synthetic production configuration and remains separate from live target-environment acceptance.
