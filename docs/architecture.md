# GoreeCloud Notes Architecture

## Role

GoreeCloud Notes is the native GoreeCloud note-taking, knowledge-management, and personal-productivity application. It is an original GoreeCloud-owned product rather than a continuation of the Memos source architecture.

## Architectural Goals

The architecture must prioritize:

- privacy by default;
- individual user isolation;
- durable data ownership;
- portable exports;
- migration and replacement capability;
- independent backup and restoration;
- API stability for browser, extension, and future mobile clients;
- clear separation of persistent data, attachments, application code, and secrets;
- accessible and responsive Glaze UI presentation.

## Component Model

```text
Web/PWA                       Future clients
React + TypeScript            Firefox extension / mobile
        |                              |
        +----------- HTTPS API --------+
                       |
                       v
                 FastAPI / Python
                       |
           +-----------+-----------+
           |                       |
           v                       v
      PostgreSQL             Attachment storage
           |
           v
 Indexed full-text search
```

## Frontend

The web frontend uses React, TypeScript, and Vite. The authenticated Glaze UI uses the intended three-pane desktop model:

1. navigation, account context, and saved organization shortcuts;
2. note list, Quick Notes capture, or notebook/tag management;
3. focused editor workspace or organization guidance.

The current UI is connected to real authenticated PostgreSQL-backed note persistence and supports notebook views, tag views, per-note notebook selection, per-note tag assignment, notebook rename/re-parent/reorder, tag rename/recolor, pin/unpin, Archive/restore, recoverable Trash, server-backed search, attachment upload/download/delete, private raster thumbnails, attachment-ID inline raster images, immutable revision history/recovery, and responsive/dark-mode presentation.

Rich editing uses open-source Tiptap/ProseMirror while keeping GoreeCloud's stored document representation independent from the editor library. The current browser editor uses explicit conflict-safe Save rather than automatic background autosave. Autosave may be added later only if the same optimistic-concurrency and conflict-recovery guarantees remain intact.

## Backend

FastAPI provides the versioned HTTP API. `/api/v1` is the first API namespace. Browser, web-clipper, and future mobile clients should use the same documented API contract instead of creating separate private backends.

The backend owns authentication, bounded login-abuse controls, trusted-proxy interpretation, authorization, document-schema validation, data validation, persistence rules, migration boundaries, notebook hierarchy rules, tag normalization, organizational filtering, search authorization, revision creation/restoration, Trash semantics, attachment authorization, inline attachment-reference validation, and reference-aware attachment deletion protection.

## Database

PostgreSQL is the native relational store. SQLAlchemy is the initial ORM/data-access layer and Alembic is the migration boundary.

The current foundation schema directly represents GoreeCloud concepts rather than reproducing transitional Memos storage. Implemented entities are:

- users;
- user credentials;
- opaque authentication sessions;
- short-lived opaque login-rate buckets;
- notebooks and notebook hierarchy;
- notes;
- tags and note-tag relationships;
- attachment metadata;
- immutable note revisions.

The reviewed migration line is:

- `0001_native_notes_schema`;
- `0002_authentication`;
- `0003_content_versions`;
- `0004_full_text_search`;
- `0005_login_abuse_controls`.

CI performs a PostgreSQL upgrade/check/downgrade/upgrade/check round trip so migration reversibility and SQLAlchemy metadata agreement are validated against a real PostgreSQL instance.

Shortcuts/favorites, note links, saved searches, reminders, and other later product concepts remain future schema work rather than foundation claims.

## Notebook Hierarchy

Notebooks are owner-scoped and may reference another owned notebook as their parent. The API validates the entire proposed parent chain before a re-parent operation and rejects self/descendant cycles.

The Glaze UI supports notebook rename, re-parenting, and explicit numeric `sort_order`. Descendants are excluded from the browser parent picker while server-side hierarchy validation remains authoritative.

Deleting a notebook preserves note content through `ON DELETE SET NULL`; notes return to the unfiled library rather than being deleted. Child notebooks are likewise promoted when their parent is removed, and the browser reloads the authoritative notebook collection after deletion. This keeps organization metadata subordinate to note durability.

## Tags and Cross-Notebook Organization

Tags are owner-scoped. Display names are Unicode-normalized and whitespace-normalized; a separate case-folded normalized name provides user-local uniqueness. `note_tags` carries the owner ID explicitly and assignment routes require both the note and tag to belong to the authenticated user.

Tag rename/recolor preserves note assignments. Color metadata is limited to portable six-digit sRGB hexadecimal values or no custom color. Tag deletion removes assignment rows through referential cascade without deleting notes. Note listing and indexed search can filter by one authorized tag ID. Richer boolean/multi-tag organization remains later product work.

## Native Document Contract

The note `document` column stores an application-owned, versioned JSON document envelope. The current format is `goreecloud.blocks` version 1 with `document_schema` 1. The purpose is to preserve a GoreeCloud data contract instead of making the database representation an undocumented serialization of Tiptap, ProseMirror, or another editor implementation.

Both client and server understand the native contract, but the backend is authoritative. The server canonicalizes supported documents and rejects unknown document versions, unsupported nodes, invalid node placement, unsupported text marks, invalid attachment references, unknown fields, excessive nesting, excessive node count, and excessive text size rather than silently discarding content. This fail-closed behavior protects future document generations from data loss caused by older clients.

The frontend explicitly converts between the GoreeCloud document contract and Tiptap/ProseMirror JSON. Supported foundation semantics include paragraphs, headings, bold, italic, strike, inline code, bullet and ordered lists, list items, blockquotes, code blocks, horizontal rules, hard breaks, text nodes, and attachment-ID raster image blocks. The conversion layer also reads the earlier Milestone 0 paragraph representation for compatibility.

An inline image is stored as an `attachmentImage` block containing a GoreeCloud attachment UUID and alt text. The persisted document does not store an arbitrary external image URL, filesystem path, object-storage location, signed URL, or Tiptap-specific image payload. The browser derives the same-origin authenticated preview URL at render time.

Future block types or editor changes require explicit GoreeCloud document-schema compatibility rather than silently changing the persisted format.

## Search

PostgreSQL is the native search engine. Migration `0004_full_text_search` adds a stored generated `tsvector` to each note and a GIN index over that vector. Search data is therefore derived from the authoritative title and structured document rather than accepted as a separately mutable client field.

The generated vector assigns higher weight to the note title and also indexes string values in the `goreecloud.blocks` JSON document. The initial text-search configuration is PostgreSQL `simple`, which avoids making an English-only stemming assumption for the family/private workspace.

`GET /api/v1/search/notes?q=...` uses `websearch_to_tsquery` and enforces authenticated owner scope before state, notebook, tag, and full-text criteria are applied. Foreign or nonexistent notebook/tag filter identifiers receive the same opaque not-found behavior used by the rest of the workspace API. Results are ordered by pin state, text-search rank, and recency.

The browser sends non-empty search queries to this indexed endpoint after a 250 ms debounce, preserves the current lifecycle/notebook/tag scope, ignores stale responses after query or view changes, aligns with the server's 200-character query ceiling, reports search failures separately, and returns to the ordinary loaded view when the query is cleared.

A separate search engine must not be introduced until PostgreSQL search is demonstrated to be insufficient and the operational cost, indexing security, backup, restoration, and consistency implications are documented.

## Attachments and Inline Images

Attachment bytes live outside ordinary relational rows in GoreeCloud-managed filesystem storage during the development foundation. PostgreSQL stores ownership, note relationship, original filename metadata, checksum, size, media type, storage key, and additional metadata.

Storage keys are generated by the server; client filenames are never accepted as filesystem locations. Uploads stream into a temporary file, enforce the configured development size ceiling, compute SHA-256 and byte size, and finalize atomically only after validation. Storage-path resolution verifies that generated paths remain inside the configured attachment root.

Attachment listing, upload, download, preview, and deletion are authenticated and owner-scoped. Cross-user and nonexistent note/attachment identifiers remain opaque. Deletion is CSRF-protected. The development Compose volume is prepared for the non-root API account, and live CI verifies persisted bytes are owned by that account.

Private inline preview is intentionally limited to AVIF, GIF, JPEG, PNG, and WebP. Preview responses use private no-store caching, `nosniff`, and same-origin resource policy. SVG, HTML, PDF, text, and other non-allowlisted formats remain download-only and receive HTTP `415` from the preview endpoint.

Inline images reuse the same passive-raster security boundary. Before accepting an `attachmentImage` block, the server verifies that the referenced attachment belongs to the authenticated user, belongs to the same note, and has an approved raster media type. Missing, foreign, wrong-note, and non-raster references fail with HTTP `422`. The browser image source is derived from the authenticated preview endpoint, so arbitrary external image URLs are not part of the native document model.

Attachment deletion is reference-aware. An attachment that is still referenced by the current document or any retained immutable revision returns HTTP `409` instead of deleting bytes that recoverable note content still requires. Revision restore likewise revalidates its historical document and attachment references before applying the restore.

The detailed contract is documented in `docs/attachments.md`.

PDF/office-document preview, SVG sanitization, OCR, resumable/large-object upload, malware scanning/quarantine, final production object-storage policy, final production storage paths, storage quotas, reference-aware garbage collection after retention policy approval, and production backup/restore validation remain future gates.

## Authentication, Login Protection, and Authorization

The browser authentication model is implemented as individual accounts with opaque database-backed sessions. GoreeCloud Notes does not expose an open registration endpoint; accounts are created through an administrative server-side CLI.

Password credentials are stored separately from account identity and use a salted, versioned `scrypt` password hash. Browser sessions use random opaque secrets. PostgreSQL stores only SHA-256 digests of the session and CSRF secrets, so the raw active browser secrets are not persisted.

The browser receives an HTTP-only session cookie plus a CSRF cookie. Cookies use `SameSite=Strict`; `Secure` is enabled automatically outside development. Authenticated state-changing requests must pass the CSRF cookie value in the `X-CSRF-Token` header and match the stored digest. Logout deletes the server-side session.

Authenticated password rotation requires the current password and CSRF, rejects reuse of the current password, updates `password_changed_at`, revokes every browser session for that account, and expires the initiating browser cookies. Private administrative recovery is available through `python -m app.cli reset-password`; it replaces the account credential and revokes every existing browser session in the same transaction without creating a public recovery endpoint or hosted identity dependency.

Migration `0005_login_abuse_controls` adds short-lived login-rate buckets. The login path evaluates both source+normalized-account and source-wide failure scopes. Default development policy is a 5-minute window, 5 source+account failures, 20 source-wide failures, a 5-minute cooldown, and 24-hour state TTL. Thresholds are deployment settings, but cooldown is always temporary: the application does not permanently lock an account.

Rate-state rows store opaque SHA-256-derived bucket keys plus scope/counter/timestamp state rather than clear username or source-address columns. The digests are a data-minimization measure, not a claim that low-entropy network addresses become anonymous. Successful login clears only the matching source+account bucket; source-wide history remains so username rotation does not trivially bypass the source-wide boundary.

Forwarded source addresses are fail-closed. `X-Forwarded-For` is ignored unless the direct peer belongs to `GOREECLOUD_NOTES_TRUSTED_PROXY_CIDRS`, whose default is empty. A trusted chain selects the rightmost untrusted address; malformed chains fall back to the direct peer; invalid configured CIDRs fail configuration validation. Production proxy CIDRs remain a target-environment value that must be verified, not guessed in source.

Authorization is server-side and owner-scoped. Notes, notebooks, tags, revisions, search filters, attachments, and inline attachment references are resolved against the authenticated user. The API deliberately returns the same not-found response for nonexistent objects and objects owned by another user where identifier opacity is appropriate so object IDs are not useful as an ownership-enumeration signal.

## Note Lifecycle, Concurrency, and Revision History

Ordinary `DELETE /api/v1/notes/{id}` does not hard-delete a note. It changes native state to `trashed`, preserving recoverability. The UI also supports Archive/restore and pin/unpin through explicit native fields.

Every note has a positive `content_version`. Content-changing PATCH operations must include the version read by the client. If the server has advanced, the request returns HTTP `409` instead of silently overwriting another edit. The current browser enters an explicit conflict state and requires a reload of the current server version before editing continues.

Title/document/document-schema edits preserve immutable pre-change snapshots in `note_revisions`. Ordinary snapshots are coalesced by a configurable minimum interval so frequent saves do not create unbounded revision churn. Revision listing is owner-scoped.

Revision restore is a new conflict-safe content write. It requires the exact current content version, always preserves current content as a pre-restore snapshot when a change is applied, increments the content version, preserves prior immutable history, restores only content-bearing fields, and leaves notebook placement, tags, lifecycle state, pinning, color, attachments, and ownership unchanged. A historical document with an unsupported schema or unavailable inline image dependency is not restored as knowingly broken content.

Milestone 0 retains revisions and exposes neither permanent note deletion nor individual revision deletion. Final production retention, garbage-collection, and permanent-deletion semantics remain open until backup, restoration, attachment, synchronization, recovery, and authorization behavior are approved and validated.

## CI Validation Architecture

Live integration checks are stored in versioned scripts:

- `scripts/ci_validate_auth.sh` validates account creation, concurrent sessions, login/current-session identity, CSRF, password rotation, global session revocation, administrative password recovery, logout, and post-revocation behavior;
- `scripts/ci_validate_login_security.sh` validates bounded source+account and source-wide cooldowns, `Retry-After`, automatic recovery, username-rotation resistance, and rejection of spoofed forwarded sources from an untrusted direct peer;
- `scripts/ci_validate_workspace.sh` validates notebook hierarchy/cycle rules, normalized tag uniqueness, tag assignment/filtering, cross-user note/notebook/tag isolation, content versions, revision coalescing, stale-write rejection, conflict-safe revision restore, pinning, notebook deletion without note loss, tag cleanup, Archive/restore, and recoverable Trash;
- `scripts/ci_validate_organization_management.sh` validates notebook rename/re-parent/reorder and ordered listing, tag rename/recolor/clear-color, normalized-name and assignment propagation, duplicate rejection, and cross-user mutation opacity;
- `scripts/ci_validate_search.sh` validates indexed title/body/phrase/web-style queries, generated-vector refresh after edits, cross-user search isolation, and live generated-column/GIN-index presence;
- `scripts/ci_validate_attachments.sh` validates private attachment upload/list/download/delete, checksum/size integrity, filename/path protections, CSRF enforcement, safe raster preview bytes and headers, cross-user opacity, non-root byte ownership, native inline-image reference validation, unsupported document rejection, and reference-aware deletion protection.

Backend unit tests separately exercise document canonicalization, legacy compatibility, strict invalid-document rejection, tolerant attachment-reference discovery, trusted/untrusted proxy source selection, malformed forwarded-chain fallback, CIDR validation, and opaque rate-key normalization.

These checks execute against the same Docker Compose/PostgreSQL stack used by the workflow rather than a reduced mock persistence layer.

## API Compatibility

The server API is versioned because the planned Firefox extension and future mobile applications must not require a backend redesign. Breaking changes require an intentional version/migration strategy.

The application-owned document contract is separately versioned from the HTTP namespace. An API-compatible client must not silently rewrite an unknown document version.

## Deployment

The foundation Compose stack contains PostgreSQL and the API, plus a development attachment volume. PostgreSQL is not published to the host and the API is loopback-only. The frontend remains a Vite development process during this foundation phase.

A production web-serving model, frontend image, Caddy route, verified trusted-proxy CIDRs, final attachment storage path or object-storage decision, backup sources, restoration procedure, malware-scanning policy, and final Docker image digests require separate validation before deployment.

## Transitional Memos Boundary

`GoreeCloud/memos` remains a separate source system. Native development does not authorize modifying or deleting its database, attachments, or deployment. The transition requires a repeatable importer and validation of note counts, content, metadata, ownership, attachment binaries, inline-reference mapping, searchability, and exportability before Memos retirement.

The transitional JSON export is not a complete attachment migration by itself because attachment binary payloads must be inventoried and copied directly from the source environment.
