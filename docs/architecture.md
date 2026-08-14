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
     Search / metadata
```

## Frontend

The web frontend uses React, TypeScript, and Vite. The authenticated Glaze UI uses the intended three-pane desktop model:

1. navigation, account context, and saved organization shortcuts;
2. note list, Quick Notes capture, or notebook/tag management;
3. focused editor workspace or organization guidance.

The foundation UI is connected to real authenticated PostgreSQL-backed note persistence and now supports notebook views, tag views, per-note notebook selection, per-note tag assignment, pin/unpin, Archive/restore, and recoverable Trash. Separate Glaze styling covers organization management while preserving the responsive/dark-mode foundation.

The current title/body editor remains deliberately a simple bridge over the application-owned structured document contract. It is not the final rich-text editor. Rich-text dependency selection, richer block semantics, autosave, and full editor acceptance remain separate gates.

## Backend

FastAPI provides the versioned HTTP API. `/api/v1` is the first API namespace. Browser, web-clipper, and future mobile clients should use the same documented API contract instead of creating separate private backends.

The backend owns authentication, authorization, data validation, persistence rules, migration boundaries, notebook hierarchy rules, tag normalization, organizational filtering, export behavior, revision creation, Trash semantics, and attachment authorization.

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

The first reviewed migrations are `0001_native_notes_schema` and `0002_authentication`. CI performs a PostgreSQL upgrade/downgrade/upgrade round trip and runs `alembic check` after the final upgrade.

Shortcuts/favorites, note links, saved searches, reminders, and other later product concepts remain future schema work rather than foundation claims.

## Notebook Hierarchy

Notebooks are owner-scoped and may reference another owned notebook as their parent. The API validates the entire proposed parent chain before a re-parent operation and rejects self/descendant cycles.

Deleting a notebook preserves note content through `ON DELETE SET NULL`; notes return to the unfiled library rather than being deleted. Child notebooks are likewise promoted when their parent is removed. This keeps organization metadata subordinate to note durability.

## Tags and Cross-Notebook Organization

Tags are owner-scoped. Display names are Unicode-normalized and whitespace-normalized; a separate case-folded normalized name provides user-local uniqueness. `note_tags` carries the owner ID explicitly and assignment routes require both the note and tag to belong to the authenticated user.

Tag deletion removes assignment rows through referential cascade without deleting notes. Note listing can filter by one authorized tag ID. Richer boolean/multi-tag search remains later search work.

## Native Document Contract

The note `document` column stores an application-owned, versioned JSON document envelope. The Milestone 0 format is `goreecloud.blocks` version 1. The purpose is to preserve a GoreeCloud data contract instead of making the database representation an undocumented serialization of whichever rich-text library is selected later.

The current frontend bridge converts plain paragraphs to and from this envelope. A future rich-text editor may expand the block vocabulary, but schema/version transitions must remain explicit and exportable.

## Search

PostgreSQL full-text search remains the preferred search engine. The workspace API enforces owner scope before applying state, notebook, tag, or title filters. The current server-side `q` filter is intentionally basic and is not yet the full-text-search implementation. The frontend also provides an immediate search over the currently loaded note set.

A separate search engine must not be introduced until PostgreSQL search is demonstrated to be insufficient and the operational cost, indexing security, backup, restoration, and consistency implications are documented.

## Attachments

Attachment bytes will live outside ordinary relational rows behind a GoreeCloud-managed storage abstraction. PostgreSQL stores ownership, note relationship, metadata, checksum, size, media type, and storage identifiers.

Attachment download, preview, export, migration, and deletion must re-check note/attachment authorization server-side. The metadata schema exists; attachment byte storage and user-facing attachment workflows are not yet implemented.

## Authentication and Authorization

The browser authentication model is implemented as individual accounts with opaque database-backed sessions. GoreeCloud Notes does not expose an open registration endpoint; accounts are created through an administrative server-side CLI.

Password credentials are stored separately from account identity and use a salted, versioned `scrypt` password hash. Browser sessions use random opaque secrets. PostgreSQL stores only SHA-256 digests of the session and CSRF secrets, so the raw active browser secrets are not persisted.

The browser receives an HTTP-only session cookie plus a CSRF cookie. Cookies use `SameSite=Strict`; `Secure` is enabled automatically outside development. Authenticated state-changing requests must pass the CSRF cookie value in the `X-CSRF-Token` header and match the stored digest. Logout deletes the server-side session.

Authorization is server-side and owner-scoped. Notes, notebooks, and tags are fetched through helpers that require `owner_id == authenticated_user.id`. The API deliberately returns the same not-found response for nonexistent objects and objects owned by another user so identifiers are not useful as an ownership-enumeration signal. Organizational filters are authorization-checked before they alter a note query.

## Note Lifecycle and Revision History

Ordinary `DELETE /api/v1/notes/{id}` does not hard-delete a note. It changes native state to `trashed`, preserving recoverability. The UI also supports Archive/restore and pin/unpin through explicit native fields.

Title/document/document-schema edits create an immutable snapshot of the pre-change content in `note_revisions`. Revision history is owner-scoped and read through `/api/v1/notes/{id}/revisions`. Later retention, restore, coalescing/autosave, and permanent-delete policy must be designed before production use.

## CI Validation Architecture

Live integration checks are stored in versioned scripts:

- `scripts/ci_validate_auth.sh` validates account creation, login, current-session identity, CSRF rejection, authenticated logout, and session revocation;
- `scripts/ci_validate_workspace.sh` validates notebook hierarchy/cycle rules, normalized tag uniqueness, tag assignment/filtering, cross-user note/notebook/tag isolation, revision creation, pinning, notebook deletion without note loss, tag cleanup, Archive/restore, and recoverable Trash.

These scripts execute against the same Docker Compose/PostgreSQL stack used by the workflow rather than a reduced mock persistence layer.

## API Compatibility

The server API is versioned because the planned Firefox extension and future mobile applications must not require a backend redesign. Breaking changes require an intentional version/migration strategy.

## Deployment

The foundation Compose stack contains PostgreSQL and the API only. The frontend remains a Vite development process during this foundation phase. A production web-serving model, frontend image, Caddy route, persistent attachment path, backup source, and final Docker image digests require separate validation before deployment.

## Transitional Memos Boundary

`GoreeCloud/memos` remains a separate source system. Native development does not authorize modifying or deleting its database, attachments, or deployment. The transition requires a repeatable importer and validation of note counts, content, metadata, ownership, attachments, searchability, and exportability before Memos retirement.
