# GoreeCloud Notes

GoreeCloud Notes is a privacy-first, self-hosted note-taking, knowledge-management, and personal-productivity application developed as original GoreeCloud-owned software.

## Status

**Milestone 0 — Native Foundation is in active development. Production deployment is not approved.**

Draft PR #1 on `feature/native-foundation` contains the current native foundation. The application already has authenticated PostgreSQL-backed note persistence, owner isolation, nested notebook and tag organization, rich structured editing, conflict-safe explicit saves, immutable revision recovery, private attachments with safe raster previews and attachment-ID inline images, read-only attachment-store integrity auditing, indexed PostgreSQL full-text search, note lifecycle controls, a Glaze UI Account & Security workflow with privacy-preserving active-session review and selective other-session revocation, private administrative account suspension/reinstatement with fresh-session enforcement, verified full-library native export through both browser and administrative CLI paths, verified empty-target native portable re-import, a controlled disposable Memos-to-native persistence pipeline with preserved migration provenance, committed frontend/backend dependency-locking controls, and a fail-closed production runtime preflight for browser origins, trusted-proxy configuration, file-backed database secrets, persistent attachment storage, and dependency readiness. Those implemented capabilities remain development-stage until the remaining target-environment production, protected-source migration, backup/recovery, publication, and security gates are closed.

The native repository is independent from the transitional Memos-based GoreeCloud Notes implementation. `GoreeCloud/memos` remains preserved as a migration source, historical engineering record, and visual reference for the accepted Quick Notes experience until migration and replacement validation are complete.

## Product Direction

GoreeCloud Notes combines fast capture with an Evernote-class knowledge workspace. Product scope includes:

- Quick Notes and a low-friction capture workflow.
- Notebooks and nested notebooks.
- All Notes, tags, favorites, shortcuts, pinned notes, Archive, and recoverable Trash.
- Rich structured editing with a GoreeCloud-owned document contract and Markdown interoperability.
- Private attachments, safe previews, and attachment-ID inline images.
- Full-text search and filters.
- Internal note links and backlinks.
- Revision history and recovery.
- Portable full-library export and controlled import/migration tooling.
- Firefox-first browser clipping in a later milestone.
- Future offline and mobile clients after the server API and synchronization model mature.

## Native Architecture

```text
Browser / future clients
        |
        | versioned HTTPS API
        v
React + TypeScript + Vite
        |
        v
FastAPI / Python
        |
        +---- PostgreSQL + indexed full-text search
        |
        +---- GoreeCloud-managed attachment storage
```

Current technology direction:

- Frontend: React + TypeScript + Vite.
- Rich editor: open-source Tiptap/ProseMirror with an application-owned conversion boundary.
- Design language: GoreeCloud Glaze UI.
- Backend: Python + FastAPI.
- Database: PostgreSQL with SQLAlchemy and Alembic.
- Search: PostgreSQL generated `tsvector` + GIN index initially.
- API: versioned HTTP API designed for web, browser-extension, and future mobile clients.
- Deployment: Docker and Docker Compose for development validation; production placement is not approved.
- License: GNU Affero General Public License v3.0 only (`AGPL-3.0-only`).

## Repository Structure

```text
goreecloud-notes/
├── frontend/                 # React/TypeScript/Vite web application
├── backend/                  # FastAPI application, lockfile, migrations, and tests
├── docker/                   # Container/deployment support
├── docs/                     # Architecture, attachment, recovery, development, migration, and production-readiness records
├── tests/                    # Cross-component and future end-to-end tests
├── scripts/                  # Versioned live integration validation
├── .github/workflows/        # Continuous integration and source-level production preflight
├── .env.example              # Sanitized development configuration template
├── compose.yml               # Development Compose stack
├── CONTRIBUTING.md
├── LICENSE
└── README.md
```

## Development Safety Boundaries

- Do not commit passwords, tokens, private keys, production session values, or other reusable credentials.
- Do not use production personal/family notes as a convenient development dataset.
- Do not modify or delete the transitional Memos database or attachments merely because native development has started.
- Do not publish backend ports directly to the public internet.
- Do not treat a development container, migration, green CI run, static production preflight, or draft pull request as production approval.
- Preserve data portability, migration traceability, backup requirements, and rollback capability throughout development.
- Do not allow arbitrary external URLs to bypass the owner-scoped attachment and inline-image model.
- Do not hard-delete recoverable note/revision/attachment dependencies before retention and recovery policy is approved.

## Current Milestone 0 Foundation

Implemented foundation work includes:

- Repository and branch governance with AGPL-3.0-only licensing.
- React/TypeScript/Vite frontend with committed `package-lock.json`, exact direct dependency declarations, and strict `npm ci` validation.
- FastAPI `/api/v1` backend and PostgreSQL persistence.
- Committed `backend/requirements.lock` constraining the complete reviewed Python runtime/test dependency graph, an exact Setuptools build-backend pin, CI exact-version verification plus `pip check`, and API-image installation through the same constraints file.
- SQLAlchemy models and reviewed Alembic migration round trips through migration-provenance revision `0006`.
- Private administrative account creation, salted `scrypt` credentials, opaque database-backed sessions, and CSRF protection.
- Authenticated Glaze UI Account & Security page with password rotation, the same 12-to-1,024-character password boundary as the backend, global session revocation after credential changes, owner-scoped active-session review, CSRF-protected sign-out of other active browser sessions while preserving the current session, and a separate-tab launcher that protects unsaved Notes drafts while explicit Save remains active. Session review exposes only server-generated session identity plus creation/expiration/current-session state; it does not require browser fingerprinting, device-name storage, user-agent history, or IP-history collection.
- Private administrative account lifecycle commands for non-sensitive status review, confirmation-gated suspension, and reinstatement. Disabling preserves credentials and user data while revoking every browser session; re-enabling also revokes any stale sessions so a pre-suspension cookie cannot become valid again and a fresh sign-in is required. Disabled-account login remains the same generic invalid-credential response used by the normal authentication boundary.
- Explicit owner-scoped authorization and two-user isolation validation.
- Nested notebooks, normalized tags, richer organization management, pinning, Archive/restore, and recoverable Trash.
- Application-owned `goreecloud.blocks` structured document format with server-side canonicalization and strict compatibility checks.
- Tiptap rich editing with optimistic concurrency and explicit conflict recovery.
- Immutable revision snapshots and conflict-safe revision restore.
- Private attachment byte storage, integrity checks, safe raster previews, and attachment-ID inline raster images.
- Reference-aware attachment deletion protection so current or recoverable historical content does not lose required bytes.
- Read-only administrative attachment-store integrity audit that verifies owner/note relationships, generated storage keys, path containment, symlink boundaries, regular-file presence, byte size, SHA-256 integrity, duplicate storage keys, and unexpected owner-scoped orphan files without automatically repairing or deleting evidence.
- Indexed PostgreSQL full-text search with scoped browser integration.
- Verified native full-library ZIP export that preserves notebooks, notes, tags, relationships, revisions, attachment metadata, attachment bytes, and imported source provenance while excluding credentials, sessions, login-rate state, search indexes, and internal storage paths.
- Authenticated CSRF-protected browser full-library download using the same verified exporter as the administrative CLI, with no-store/no-cache delivery, archive SHA-256 response evidence, and removal of temporary server-side export files after delivery.
- Verified administrator-operated native portable re-import into an explicitly confirmed empty existing account. The importer independently verifies the ZIP and native relationships, preserves native object UUIDs and user-owned timestamps, refuses UUID collisions and populated-target merges, stages and re-hashes attachment bytes into generated target-owned storage paths, reconstructs searchable PostgreSQL state, and leaves account credentials/session state outside the portable-data boundary.
- Destructive disposable native export → source-account/data removal → separately created empty target → native re-import → API/search/attachment validation → re-export equivalence testing.
- Non-destructive transitional Memos export inspection, deterministic provider-neutral manifest generation, and attachment-binary evidence verification.
- Explicit empty-target native Memos persistence import using only validated manifest/evidence inputs, generated native attachment storage, persistent source provenance, post-import read-only verification, duplicate-import refusal, and cross-user opacity.
- Native portable export of imported accounts preserves exact migration import checkpoints and normalized source records so deferred source semantics remain portable instead of becoming database-only history.
- Provenance-bearing destructive round-trip validation proving Memos source Markdown, relations, named source color, location metadata, Trash restore target, migration fingerprints/record hashes, note-tag relationships, and attachment bytes survive native export → destructive native-source removal → native re-import → Memos post-import verification → second native export.
- Production mode rejects unsafe development carryover: non-HTTPS/localhost/loopback or wildcard credentialed origins, an unresolved trusted-proxy boundary, relative attachment storage, and inline/relative database-secret configuration.
- `python -m app.production_check` provides a non-destructive static production preflight for secure cookies, HTTPS origins, trusted proxy configuration, file-backed database-secret readiness, and attachment-root readiness while explicitly reporting that live dependency validation and production approval were not performed.
- `/health` remains dependency-free liveness, while `/ready` requires both a live PostgreSQL query and usable attachment storage. Dockerfile/Compose health checks use `/ready` so persistence failure is not reported as a healthy application merely because the API process is running.
- A dedicated **Production Runtime Preflight** GitHub Actions workflow proves both a passing explicit synthetic production configuration and fail-closed rejection of unsafe production defaults without claiming target-environment acceptance.
- Backend unit tests plus live Compose validation for authentication, browser sessions, administrative account suspension/reinstatement, workspace, organization, search, revisions, attachments, attachment-store integrity auditing, CLI/browser portability, native portable re-import, Memos migration/provenance, destructive disposable database-plus-attachment recovery, and dependency readiness.

The current synthetic migration gate deliberately does not claim complete native semantic equivalence. Exact source Markdown, relations, location metadata, Trash restore targets, and named Memos colors remain preserved in migration provenance when the current native projection does not have an approved equivalent. External-link attachments remain unsupported by the native Memos importer and therefore fail closed.

Milestone 0 remains open for final production operator authorization/runbook acceptance, PDF/document/SVG preview policy, malware scanning, resumable/large-object and final production storage design, attachment quotas and scheduled integrity-audit/alerting policy, protected-copy Memos attachment extraction and a production-representative migration rehearsal, production Kopia/retention/off-site recovery evidence, selected RPO/RTO, and target-environment production publication/monitoring/Caddy/trusted-proxy validation. Scheduled/encrypted export UX and production large-library/background-job/concurrency policy remain open. Native portable re-import is currently administrator-operated and empty-target only; browser upload/import, populated-library merge/conflict resolution, selective restore, and synchronization are not implemented.

See `docs/architecture.md`, `docs/account-security.md`, `docs/attachments.md`, `docs/attachment-integrity.md`, `docs/revisions.md`, `docs/migration.md`, `docs/portable-export.md`, `docs/native-import.md`, `docs/backup-restore.md`, and `docs/production-readiness.md` for the current technical boundaries.

## Branch Model

- `main` — reviewed stable repository state.
- `feature/*` — isolated feature development.
- `fix/*` — bug fixes.
- `security/*` — security changes.

A permanent `develop` branch is not required unless project complexity later demonstrates a real need.

## License

GoreeCloud Notes is licensed under the GNU Affero General Public License v3.0 only (`AGPL-3.0-only`). See `LICENSE`.
