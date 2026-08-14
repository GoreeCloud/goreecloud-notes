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

The current UI is connected to real authenticated PostgreSQL-backed note persistence and supports notebook views, tag views, per-note notebook selection, per-note tag assignment, pin/unpin, Archive/restore, recoverable Trash, attachment upload/download/delete controls, and responsive/dark-mode presentation.

Rich editing uses open-source Tiptap/ProseMirror while keeping GoreeCloud's stored document representation independent from the editor library. The current browser editor uses explicit conflict-safe Save rather than automatic background autosave. Autosave may be added later only if the same optimistic-concurrency and conflict-recovery guarantees remain intact.

## Backend

FastAPI provides the versioned HTTP API. `/api/v1` is the first API namespace. Browser, web-clipper, and future mobile clients should use the same documented API contract instead of creating separate private backends.

The backend owns authentication, authorization, data validation, persistence rules, migration boundaries, notebook hierarchy rules, tag normalization, organizational filtering, search authorization, revision creation, Trash semantics, and attachment authorization.

## Database

PostgreSQL is the native relational store. SQLAlchemy is the initial ORM/data-access layer and Alembic is the migration boundary.

The current foundation schema directly represents GoreeCloud concepts rather than reproducing transitional Memos storage. Implemented entities are:

- users;
- user credentials;
- opaque authentication sessions;
- notebooks and notebook hierarchy;
- notes;
- tags and note-tag relationships;
- attachment metadata;
- immutable note revisions.

The reviewed migration line is:

- `0001_native_notes_schema`;
- `0002_authentication`;
- `0003_content_versions`;
- `0004_full_text_search`.

CI performs a PostgreSQL upgrade/check/downgrade/upgrade/check round trip so migration reversibility and SQLAlchemy metadata agreement are validated against a real PostgreSQL instance.

Shortcuts/favorites, note links, saved searches, reminders, and other later product concepts remain future schema work rather than foundation claims.

## Notebook Hierarchy

Notebooks are owner-scoped and may reference another owned notebook as their parent. The API validates the entire proposed parent chain before a re-parent operation and rejects self/descendant cycles.

Deleting a notebook preserves note content through `ON DELETE SET NULL`; notes return to the unfiled library rather than being deleted. Child notebooks are likewise promoted when their parent is removed. This keeps organization metadata subordinate to note durability.

## Tags and Cross-Notebook Organization

Tags are owner-scoped. Display names are Unicode-normalized and whitespace-normalized; a separate case-folded normalized name provides user-local uniqueness. `note_tags` carries the owner ID explicitly and assignment routes require both the note and tag to belong to the authenticated user.

Tag deletion removes assignment rows through referential cascade without deleting notes. Note listing can filter by one authorized tag ID. Richer boolean/multi-tag organization remains later product work.

## Native Document Contract

The note `document` column stores an application-owned, versioned JSON document envelope. The current format is `goreecloud.blocks` version 1. The purpose is to preserve a GoreeCloud data contract instead of making the database representation an undocumented serialization of Tiptap, ProseMirror, or another editor implementation.

The frontend explicitly converts between the GoreeCloud document contract and Tiptap/ProseMirror JSON. Supported foundation semantics include paragraphs, headings, bold, italic, strike, inline code, bullet and ordered lists, list items, blockquotes, code blocks, horizontal rules, hard breaks, and text nodes. The conversion layer also reads the earlier Milestone 0 paragraph representation for compatibility.

Future block types or editor changes require explicit GoreeCloud document-schema compatibility rather than silently changing the persisted format.

## Search

PostgreSQL is the native search engine. Migration `0004_full_text_search` adds a stored generated `tsvector` to each note and a GIN index over that vector. Search data is therefore derived from the authoritative title and structured document rather than accepted as a separately mutable client field.

The generated vector assigns higher weight to the note title and also indexes string values in the `goreecloud.blocks` JSON document. The initial text-search configuration is PostgreSQL `simple`, which avoids making an English-only stemming assumption for the family/private workspace.

`GET /api/v1/search/notes?q=...` uses `websearch_to_tsquery` and enforces authenticated owner scope before state, notebook, tag, and full-text criteria are applied. Foreign or nonexistent notebook/tag filter identifiers receive the same opaque not-found behavior used by the rest of the workspace API. Results are ordered by pin state, text-search rank, and recency.

The current browser still provides immediate local filtering over the loaded note set. Wiring that field to the indexed server-search API remains a separate UI/scaling step; the server-search foundation is already available to browser, extension, and future mobile clients.

A separate search engine must not be introduced until PostgreSQL search is demonstrated to be insufficient and the operational cost, indexing security, backup, restoration, and consistency implications are documented.

## Attachments

Attachment bytes live outside ordinary relational rows in GoreeCloud-managed filesystem storage during the development foundation. PostgreSQL stores ownership, note relationship, original filename metadata, checksum, size, media type, storage key, and additional metadata.

Storage keys are generated by the server; client filenames are never accepted as filesystem locations. Uploads stream into a temporary file, enforce the configured development size ceiling, compute SHA-256 and byte size, and finalize atomically only after validation. Storage-path resolution verifies that generated paths remain inside the configured attachment root.

Attachment listing, upload, download, and deletion are authenticated and owner-scoped. Cross-user and nonexistent note/attachment identifiers remain opaque. Deletion is CSRF-protected. The development Compose volume is prepared for the non-root API account, and live CI verifies persisted bytes are owned by that account and removed during an authorized delete.

Attachment previews, inline-image embedding, resumable/large-object upload, malware scanning, production object-storage policy, final production storage paths, and backup/restore validation remain future gates.

## Authentication and Authorization

The browser authentication model is implemented as individual accounts with opaque database-backed sessions. GoreeCloud Notes does not expose an open registration endpoint; accounts are created through an administrative server-side CLI.

Password credentials are stored separately from account identity and use a salted, versioned `scrypt` password hash. Browser sessions use random opaque secrets. PostgreSQL stores only SHA-256 digests of the session and CSRF secrets, so the raw active browser secrets are not persisted.

The browser receives an HTTP-only session cookie plus a CSRF cookie. Cookies use `SameSite=Strict`; `Secure` is enabled automatically outside development. Authenticated state-changing requests must pass the CSRF cookie value in the `X-CSRF-Token` header and match the stored digest. Logout deletes the server-side session.

Authorization is server-side and owner-scoped. Notes, notebooks, tags, revisions, search filters, and attachments are resolved against the authenticated user. The API deliberately returns the same not-found response for nonexistent objects and objects owned by another user so identifiers are not useful as an ownership-enumeration signal.

## Note Lifecycle, Concurrency, and Revision History

Ordinary `DELETE /api/v1/notes/{id}` does not hard-delete a note. It changes native state to `trashed`, preserving recoverability. The UI also supports Archive/restore and pin/unpin through explicit native fields.

Every note has a positive `content_version`. Content-changing PATCH operations must include the version read by the client. If the server has advanced, the request returns HTTP `409` instead of silently overwriting another edit. The current browser enters an explicit conflict state and requires a reload of the current server version before editing continues.

Title/document/document-schema edits preserve immutable pre-change snapshots in `note_revisions`. Snapshots are coalesced by a configurable minimum interval so frequent saves do not create unbounded revision churn. Revision listing is owner-scoped. Revision restore UI and the final long-term revision-retention/permanent-delete policy remain open before production approval.

## CI Validation Architecture

Live integration checks are stored in versioned scripts:

- `scripts/ci_validate_auth.sh` validates account creation, login, current-session identity, CSRF rejection, authenticated logout, and session revocation;
- `scripts/ci_validate_workspace.sh` validates notebook hierarchy/cycle rules, normalized tag uniqueness, tag assignment/filtering, cross-user note/notebook/tag isolation, content versions, revision coalescing, stale-write rejection, pinning, notebook deletion without note loss, tag cleanup, Archive/restore, and recoverable Trash;
- `scripts/ci_validate_search.sh` validates indexed title/body/phrase/web-style queries, generated-vector refresh after edits, cross-user search isolation, and live generated-column/GIN-index presence;
- `scripts/ci_validate_attachments.sh` validates private attachment upload/list/download/delete, checksum/size integrity, filename/path protections, CSRF enforcement, cross-user opacity, non-root byte ownership, and authorized cleanup.

These scripts execute against the same Docker Compose/PostgreSQL stack used by the workflow rather than a reduced mock persistence layer.

## API Compatibility

The server API is versioned because the planned Firefox extension and future mobile applications must not require a backend redesign. Breaking changes require an intentional version/migration strategy.

## Deployment

The foundation Compose stack contains PostgreSQL and the API, plus a development attachment volume. PostgreSQL is not published to the host and the API is loopback-only. The frontend remains a Vite development process during this foundation phase.

A production web-serving model, frontend image, Caddy route, final attachment storage path or object-storage decision, backup sources, restoration procedure, and final Docker image digests require separate validation before deployment.

## Transitional Memos Boundary

`GoreeCloud/memos` remains a separate source system. Native development does not authorize modifying or deleting its database, attachments, or deployment. The transition requires a repeatable importer and validation of note counts, content, metadata, ownership, attachments, searchability, and exportability before Memos retirement.
