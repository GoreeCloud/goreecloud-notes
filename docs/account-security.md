# Account Security and Credential Recovery

GoreeCloud Notes keeps account identity, password credentials, browser sessions, temporary login-abuse state, and portable user-data export concerns separate. This document records the Milestone 0 password-rotation, administrative-recovery, bounded login-protection, and Account & Security browser behavior implemented on the native development branch.

## Password Policy

New or replacement passwords must contain at least 12 characters and no more than 1,024 characters. The same boundary is enforced by the administrative CLI, authenticated password-rotation API, and browser Account & Security form. Password whitespace is treated as password content and is not trimmed or normalized.

Passwords are stored only as salted, versioned `scrypt` hashes. Raw passwords are not stored in PostgreSQL, source control, application logs, change logs, or recovery metadata. Failed login paths retain the scrypt verification cost for known, inactive, and unknown accounts so account state is not deliberately exposed through a cheap unknown-account path.

## Account & Security Browser Page

The Glaze UI exposes the authenticated account-security surface at:

```text
#account-security
```

The Notes workspace provides an **Account & Security** launcher that opens the page in a separate browser tab. This is deliberate while the editor uses explicit conflict-safe Save rather than autosave: opening account settings must not unmount the current Notes workspace and silently discard an unsaved draft.

Before exposing authenticated controls, the page calls the existing `/api/v1/auth/me` boundary and confirms that the browser still has a live server-side session. The page shows the current account identity and does not expose password controls to an unauthenticated browser.

The password form uses browser `current-password` and `new-password` autocomplete semantics and keeps current, replacement, and confirmation values only in React component state. The client checks the same 12-to-1,024-character password boundary enforced by the server, rejects a mismatched confirmation, and rejects obvious current-password reuse before submission. The backend remains authoritative for all credential validation and mutation.

If a password change succeeds, every account session has already been revoked by the server and the current browser cookies have already been expired. The page therefore clears its local password state and returns to a sign-in-required state instead of issuing a misleading second logout request.

The same page also exposes the user-facing **Download full library** portability control. That operation is independently authenticated and CSRF protected, uses the existing verified portable-export layer, and does not require the user to enter a password into the export workflow. Portable-export details and exclusions are documented in `docs/portable-export.md`.

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
- persisted rate-state structure contains opaque digest keys rather than clear account/source identifier columns;
- the browser Account & Security implementation compiles and lints through the locked frontend dependency graph; and
- the browser portable-export control remains behind authenticated session plus CSRF protection and does not weaken the portable-export integrity boundary.

## Remaining Production Security Gates

This Milestone 0 work does **not** make the authentication system production-ready by itself. Remaining work includes production publication-layer abuse controls, final administrator/account lifecycle controls, monitoring and audit requirements, session visibility/revocation UI if justified, final deployment/session policy, backup/restore handling for credential/session/rate state, and private-publication validation.

Any future self-service recovery mechanism must be designed separately. It must not silently add email, SMS, hosted identity, or third-party recovery dependencies to the GoreeCloud Notes core product.
