# Account Security and Credential Recovery

GoreeCloud Notes keeps account identity, password credentials, browser sessions, and temporary login-abuse state separate. This document records the Milestone 0 password-rotation, administrative-recovery, and bounded login-protection behavior implemented on the native development branch.

## Password Policy

New or replacement passwords must contain at least 12 characters and no more than 1,024 characters. The same boundary is enforced by the administrative CLI and authenticated password-rotation API. Password whitespace is treated as password content and is not trimmed or normalized.

Passwords are stored only as salted, versioned `scrypt` hashes. Raw passwords are not stored in PostgreSQL, source control, application logs, change logs, or recovery metadata. Failed login paths retain the scrypt verification cost for known, inactive, and unknown accounts so account state is not deliberately exposed through a cheap unknown-account path.

## Authenticated Password Rotation

`POST /api/v1/auth/password` requires:

- a live authenticated browser session;
- the matching CSRF cookie/header pair;
- the account's current password;
- a valid replacement password different from the current password.

A successful rotation replaces the password hash, updates `password_changed_at`, revokes **every** server-side browser session for the account, expires the current browser cookies, and returns HTTP `204`.

Revoking all sessions is deliberate. A password change is treated as a credential-security event, so previously authenticated browsers do not remain trusted after the credential changes. The user must sign in again with the replacement password.

Wrong-current-password and same-password attempts do not mutate credentials or sessions.

## Administrative Recovery

There is still no public registration, password-reset email flow, or recovery-token endpoint. Administrative recovery is performed locally on the GoreeCloud Notes server with:

```bash
python -m app.cli reset-password --username <username>
```

For non-interactive protected automation, `--password-stdin` reads exactly one replacement password line from standard input.

The command:

1. normalizes the supplied username using the same NFKC/trim/case-fold comparison used for login;
2. resolves the existing private account;
3. validates and hashes the replacement password;
4. updates the account credential timestamp;
5. revokes every existing browser session for that account in the same database transaction.

The command does not create an administrator API, recovery token, email dependency, or permanent bootstrap credential.

## Bounded Login-Abuse Controls

The login endpoint maintains short-lived PostgreSQL rate state for two independent scopes:

- **source + normalized account** — default threshold: 5 failed attempts inside a 5-minute window;
- **source-wide** — default threshold: 20 failed attempts inside the same 5-minute window.

Reaching either threshold starts a temporary default 5-minute cooldown. A blocked login returns HTTP `429` with an integer `Retry-After` header and `Cache-Control: no-store`. Cooldown expiration is automatic; there is no permanent account lockout or administrator unlock requirement.

Successful authentication clears only the matching source+account bucket. Source-wide failure history remains until its window/cooldown/TTL expires so rotating usernames cannot trivially evade source-wide protection.

Persisted rate state stores SHA-256-derived opaque bucket keys plus bounded counters/timestamps. Clear usernames and source IP-address strings are not columns in the rate-state table. These digests are a data-minimization measure, not a claim that low-entropy source addresses are cryptographically anonymous.

Expired rate state is pruned during login checks. The default state TTL is 24 hours and is configurable independently from the failure window/cooldown.

## Trusted Proxy Boundary

`X-Forwarded-For` is ignored unless the direct TCP peer belongs to an explicitly configured `GOREECLOUD_NOTES_TRUSTED_PROXY_CIDRS` network.

The default trusted-proxy list is empty. Production CIDRs must not be guessed from documentation or development networking; they must be set only after the exact private Caddy/publication topology is verified.

For an accepted trusted-proxy chain, GoreeCloud Notes selects the rightmost untrusted address as the effective client source. A malformed forwarded chain falls back to the direct peer. Invalid configured CIDRs fail application configuration validation instead of silently weakening the boundary.

## Validation Requirements

The live Compose authentication/security gates must prove all of the following before this behavior is accepted:

- two simultaneous sessions can authenticate before password rotation;
- password rotation without CSRF is rejected;
- an incorrect current password is rejected without mutation;
- reusing the current password as the replacement is rejected;
- successful rotation revokes both the initiating session and another concurrent session;
- the old password no longer authenticates;
- the rotated password does authenticate;
- administrative CLI reset revokes the newly authenticated session;
- the pre-reset password no longer authenticates;
- the recovered password authenticates;
- normal CSRF-protected logout and post-logout revocation still work afterward;
- source+account failures remain generic until the configured threshold, then produce bounded HTTP `429` with `Retry-After`;
- a correct password cannot bypass an active cooldown;
- authentication succeeds automatically after cooldown expiry;
- rotating unknown usernames cannot evade the source-wide threshold;
- an untrusted direct peer cannot bypass a source cooldown by spoofing `X-Forwarded-For`;
- malformed and trusted proxy-chain source-selection behavior is covered by unit tests;
- persisted rate-state structure contains opaque digest keys rather than clear account/source identifier columns.

## Remaining Production Security Gates

This Milestone 0 work does **not** make the authentication system production-ready by itself. Remaining work includes production publication-layer abuse controls, final administrator/account lifecycle controls, monitoring and audit requirements, session visibility/revocation UI if justified, final deployment/session policy, backup/restore handling for credential/session/rate state, and private-publication validation.

Any future self-service recovery mechanism must be designed separately. It must not silently add email, SMS, hosted identity, or third-party recovery dependencies to the GoreeCloud Notes core product.
