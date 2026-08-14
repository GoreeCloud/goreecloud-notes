# Account Security and Credential Recovery

GoreeCloud Notes keeps account identity, password credentials, and browser sessions separate. This document records the Milestone 0 password-rotation and administrative-recovery behavior implemented on the native development branch.

## Password Policy

New or replacement passwords must contain at least 12 characters and no more than 1,024 characters. The same boundary is enforced by the administrative CLI and authenticated password-rotation API. Password whitespace is treated as password content and is not trimmed or normalized.

Passwords are stored only as salted, versioned `scrypt` hashes. Raw passwords are not stored in PostgreSQL, source control, application logs, change logs, or recovery metadata.

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

## Validation Requirements

The live Compose authentication gate must prove all of the following before this behavior is accepted:

- two simultaneous sessions can authenticate before rotation;
- password rotation without CSRF is rejected;
- an incorrect current password is rejected without mutation;
- reusing the current password as the replacement is rejected;
- successful rotation revokes both the initiating session and another concurrent session;
- the old password no longer authenticates;
- the rotated password does authenticate;
- administrative CLI reset revokes the newly authenticated session;
- the pre-reset password no longer authenticates;
- the recovered password authenticates;
- normal CSRF-protected logout and post-logout revocation still work afterward.

## Remaining Production Security Gates

This Milestone 0 slice does **not** make the authentication system production-ready by itself. Remaining work includes login abuse/rate limiting, administrator/account lifecycle controls, monitoring and audit requirements, final deployment/session policy, backup/restore handling for credential and session state, and private-publication validation.

Any future self-service recovery mechanism must be designed separately. It must not silently add email, SMS, hosted identity, or third-party recovery dependencies to the GoreeCloud Notes core product.
