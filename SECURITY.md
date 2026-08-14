# Security

GoreeCloud Notes is a privacy-first application intended to hold personal and family knowledge. Security defects that could expose note content, attachments, credentials, sessions, authorization boundaries, exports, backups, or migration data are treated as high-impact issues.

## Repository Security Rules

- Never commit reusable passwords, tokens, API keys, private keys, session values, database credentials, or production secrets.
- Never commit real private note content or personal/family data as test fixtures.
- Use synthetic development data.
- Keep backend services loopback-only or private during development.
- Treat every note, attachment, notebook, tag, export, search result, and revision as user-scoped data unless an explicit sharing model is implemented and authorized.
- Re-check authorization at mutation, attachment-reference, search, restore, import, and export boundaries rather than trusting browser state.
- Keep migration tooling read-safe by default and validate source/target counts and ownership before retirement of a source system.
- Reject unsupported document generations rather than silently dropping fields or nodes an older client cannot understand.
- Do not render arbitrary external image URLs as native inline-note content.

## Implemented Authentication Boundary

Milestone 0 includes a private authentication foundation; this does not by itself authorize production publication.

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

Authentication success never implies unrestricted access to another user's notes, notebooks, tags, attachments, exports, revisions, search results, or embedded attachment references.

Workspace queries scope database access to the authenticated user's UUID. Cross-user note, notebook, tag, revision, search-filter, and attachment references use opaque failure behavior where appropriate rather than revealing another user's object ownership. Notebook parent references, note notebook assignments, tag filters, note/tag assignments, revision reads/restores, search scopes, attachment byte access, and inline attachment references all re-check ownership server-side. Mutations require both a live authenticated session and CSRF validation.

Notebook hierarchy validation also rejects self/descendant cycles. Tag uniqueness is user-local after Unicode/case/whitespace normalization, preventing visually duplicated organization entries from bypassing the intended namespace.

CI validates these boundaries against a live PostgreSQL/Compose environment with synthetic users, including cross-user organization, note, search, attachment, preview, and mutation attempts.

## Native Document Security Boundary

`goreecloud.blocks` is an application-owned security and portability boundary, not merely a browser serialization convenience.

The backend canonicalizes the current version-1 document format and rejects unsupported document versions, unsupported node types, invalid node placement, unsupported marks, unknown fields, invalid attachment UUIDs, excessive nesting, excessive node count, and excessive text size. An incompatible document is rejected instead of being partially saved after unknown content is discarded.

The browser conversion layer follows the same fail-closed principle for unknown document generations. The server remains authoritative because browser validation can never be treated as an authorization or integrity control.

Inline images are represented by GoreeCloud attachment UUIDs, not by arbitrary URLs. Before saving a native `attachmentImage` block, the server requires the referenced attachment to belong to the authenticated user, belong to the same note, and use an approved passive-raster media type.

## Attachment and Inline-Rendering Security

Attachment filenames are metadata only. Filesystem paths use server-generated storage keys and path-boundary checks. Uploads are streamed, size-limited, SHA-256 hashed, atomically finalized, and stored under the non-root API account in the development stack.

Ordinary attachment downloads remain authenticated. The separate inline preview path is restricted to AVIF, GIF, JPEG, PNG, and WebP. SVG, HTML, PDF, text, and other non-allowlisted formats do not become browser-renderable merely because they were uploaded; the preview route returns HTTP `415` for them.

Preview responses use private no-store caching, `X-Content-Type-Options: nosniff`, and `Cross-Origin-Resource-Policy: same-origin`. The browser derives inline-image `src` values from this same-origin authenticated preview route. Native note documents do not store filesystem paths, object-storage URLs, signed URLs, or arbitrary remote image URLs.

Attachment deletion is reference-aware. If the current note document or a retained immutable revision still references an attachment, deletion fails with HTTP `409`. This prevents a file-management action from silently corrupting current or recoverable historical note content.

Malware scanning/quarantine, active-content sanitization, PDF/office-document preview, final production storage, storage quotas, resumable large-object upload, and production attachment backup/restore are separate gates and are not implied by safe raster support.

## Recoverable Note State and Revision Security

The ordinary note delete endpoint moves a note into native `trashed` state instead of hard-deleting the row. Archive/restore and pin state use explicit native fields. Content/title edits preserve immutable pre-change revision snapshots.

Revision restore is owner-scoped, CSRF-protected, and optimistic-concurrency protected. A stale restore receives HTTP `409`. The server snapshots current content before an actual restore, preserves prior immutable history, and revalidates the historical document plus inline attachment dependencies before accepting it.

Permanent native-note deletion, individual revision deletion, final retention, and reference-aware garbage-collection policy remain intentionally unavailable until production recovery requirements are approved.

## Current Limitations

The authentication and ownership foundation is still development-stage. Production approval additionally requires review and validation of:

- rate limiting / brute-force protections at the application and publication layers;
- password reset and credential rotation workflows;
- production account bootstrap and administrative recovery;
- session maintenance and revocation operations;
- final Python dependency-locking strategy;
- production attachment storage, malware scanning/quarantine, quotas, and backup/restore;
- active-content/PDF/document preview policy;
- resumable or large-object upload requirements;
- export authorization and portable attachment packaging;
- permanent-delete, revision-retention, and reference-aware garbage-collection policy;
- backup and isolated restoration;
- Memos migration and rollback;
- monitoring and alerting;
- private Caddy/NetBird publication;
- final production images and configuration review.

## Production Gate

Production publication is not approved until authentication, authorization, session storage, CSRF behavior, document compatibility, database protection, attachment storage, backup, restoration, migration, monitoring, and private-service publication have been reviewed and validated together.
