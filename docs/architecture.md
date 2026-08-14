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

The web frontend uses React, TypeScript, and Vite. The first shell establishes the intended three-pane desktop model:

1. navigation and product context;
2. note list / Quick Notes capture;
3. focused editor workspace.

The shell is not yet a functional note editor. Structured rich-text editing will be added only after the note data contract and editor dependency are reviewed together.

## Backend

FastAPI provides the versioned HTTP API. `/api/v1` is the first API namespace. Browser, web-clipper, and future mobile clients should use the same documented API contract instead of creating separate private backends.

The backend owns authentication, authorization, data validation, persistence rules, migration boundaries, export behavior, and attachment authorization.

## Database

PostgreSQL is the native relational store. SQLAlchemy is the initial ORM/data-access layer and Alembic is the migration boundary.

The planned native schema will represent concepts directly instead of reproducing the transitional Memos model. Expected entities include users, sessions, notes, notebooks, notebook hierarchy, tags, note-tag relationships, attachments, revisions, shortcuts/favorites, note links, and future saved searches/reminders where approved.

No production schema is claimed by the foundation branch yet.

## Search

PostgreSQL full-text search is the preferred initial search engine. Search must always start from the current user's authorized data scope before applying text queries or filters.

A separate search engine must not be introduced until PostgreSQL search is demonstrated to be insufficient and the operational cost, indexing security, backup, restoration, and consistency implications are documented.

## Attachments

Attachment bytes will live outside ordinary relational rows behind a GoreeCloud-managed storage abstraction. PostgreSQL will store ownership, note relationship, metadata, checksum, size, media type, and storage identifiers.

Attachment download, preview, export, migration, and deletion must re-check note/attachment authorization server-side.

## Authentication and Authorization

The intended browser model is individual accounts with opaque server-side sessions. Browser cookies will be HTTP-only and secure in the production HTTPS environment. CSRF protection will be required for state-changing browser requests.

Authorization must be expressed in reusable backend query and mutation helpers so user-data access cannot depend on frontend filtering.

## API Compatibility

The server API is versioned because the planned Firefox extension and future mobile applications must not require a backend redesign. Breaking changes require an intentional version/migration strategy.

## Deployment

The foundation Compose stack contains PostgreSQL and the API only. The frontend remains a Vite development process during this first foundation step. A production web-serving model, frontend image, Caddy route, persistent attachment path, backup source, and final Docker image digests require separate validation before deployment.

## Transitional Memos Boundary

`GoreeCloud/memos` remains a separate source system. Native development does not authorize modifying or deleting its database, attachments, or deployment. The transition requires a repeatable importer and validation of note counts, content, metadata, ownership, attachments, searchability, and exportability before Memos retirement.
