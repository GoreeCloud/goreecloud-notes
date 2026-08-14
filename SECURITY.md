# Security

GoreeCloud Notes is a privacy-first application intended to hold personal and family knowledge. Security defects that could expose note content, attachments, credentials, sessions, authorization boundaries, exports, backups, or migration data are treated as high-impact issues.

## Repository Security Rules

- Never commit reusable passwords, tokens, API keys, private keys, session values, database credentials, or production secrets.
- Never commit real private note content or personal/family data as test fixtures.
- Use synthetic development data.
- Keep backend services loopback-only or private during development.
- Treat every note, attachment, notebook, tag, export, search result, and revision as user-scoped data unless an explicit sharing model is implemented and authorized.
- Re-check authorization at the mutation and export boundaries rather than trusting browser state.
- Keep migration tooling read-safe by default and validate source/target counts and ownership before retirement of a source system.

## Implemented Authentication Boundary

Milestone 0 now includes a private authentication foundation; this does not by itself authorize production publication.

- There is no open user-registration endpoint.
- Accounts are created through the server-side administrative CLI.
- Account identity and password credential material are stored in separate tables.
- Passwords use salted, versioned `scrypt` hashes; plaintext passwords are never stored.
- Successful logins issue cryptographically random opaque session and CSRF secrets.
- Only SHA-256 digests of those browser secrets are persisted in PostgreSQL.
- The session secret is sent only in an HTTP-only cookie.
- Cookies use `SameSite=Strict` and become `Secure` automatically outside the development environment.
- Authenticated browser mutations require a matching CSRF cookie/header pair and the matching server-stored digest.
- Logout deletes the server-side session; removing a browser cookie alone is not the revocation mechanism.
- Expired sessions are rejected and are pruned during session issuance.
- Authentication endpoints use `Cache-Control: no-store` for identity/session responses.

The current default session lifetime is 12 hours and is configurable through deployment configuration.

## Authorization and User Isolation

Authentication success never implies unrestricted access to another user's notes, notebooks, tags, attachments, exports, revisions, or search results.

Workspace queries scope database access to the authenticated user's UUID. Cross-user note, notebook, and tag references use not-found responses instead of revealing whether another user's object exists. Notebook parent references, note notebook assignments, tag filters, note/tag assignments, and revision reads all re-check ownership server-side. Mutations require both a live authenticated session and CSRF validation.

Notebook hierarchy validation also rejects self/descendant cycles. Tag uniqueness is user-local after Unicode/case/whitespace normalization, preventing visually duplicated organization entries from bypassing the intended namespace.

CI validates these boundaries against a live PostgreSQL/Compose environment with two synthetic users. The current integration script proves the second user cannot read or overwrite the first user's note, cannot create content in the first user's notebook, cannot use the first user's tag as a note-list filter, and does not receive the first user's note in ordinary listings. The owner path separately validates tag assignment/removal, tag-filtered listings, notebook deletion without note loss, and tag deletion without note loss.

## Recoverable Note State

The ordinary note delete endpoint moves a note into native `trashed` state instead of hard-deleting the row. Archive/restore and pin state use explicit native fields. Content/title edits preserve immutable pre-change revision snapshots. Permanent-delete and revision-retention/coalescing policy remain future security/recovery gates.

## Current Limitations

The authentication and ownership foundation is still development-stage. Production approval additionally requires review and validation of:

- rate limiting / brute-force protections at the application and publication layers;
- password reset and credential rotation workflows;
- production account bootstrap and administrative recovery;
- session maintenance and revocation operations;
- attachment byte storage and authorization;
- production-grade search and export authorization paths;
- permanent-delete and revision-retention policy;
- backup and isolated restoration;
- Memos migration and rollback;
- monitoring and alerting;
- private Caddy/NetBird publication;
- final production image and configuration review.

## Production Gate

Production publication is not approved until authentication, authorization, session storage, CSRF behavior, database protection, attachment storage, backup, restoration, migration, monitoring, and private-service publication have been reviewed and validated together.
