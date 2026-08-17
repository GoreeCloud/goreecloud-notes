# GoreeCloud Notes

GoreeCloud Notes is a privacy-first, self-hosted note-taking, knowledge-management, and personal-productivity application developed as original GoreeCloud-owned software.

## Status

**Milestone 0 — Native Foundation is in active development. Production deployment is not approved.**

The current development line is draft PR #1 on `feature/native-foundation`. The native application already provides a substantial source-validated foundation, but GoreeCloud production cutover remains gated by protected-source migration rehearsal, target storage and recovery evidence, final private-publication controls, monitoring, operator procedures, and real-device acceptance.

The existing Memos-based Notes environment remains protected as a migration source until those gates are closed. `GoreeCloud/memos` is a separate GoreeCloud quick-capture product and is not replaced or retired by native Notes development.

## Product Direction

GoreeCloud Notes combines fast capture with an Evernote-class knowledge workspace. The native product direction includes:

- Quick Notes and low-friction capture.
- Notebooks and nested notebooks.
- Tags, pinning, favorites/shortcuts where approved, Archive, and recoverable Trash.
- Rich structured editing with Markdown interoperability.
- Private attachments and inline images.
- Full-text search and filtering.
- Revision history and recovery.
- Portable full-library export and controlled import/migration tooling.
- Internal note links, backlinks, templates, and richer knowledge organization in later milestones.
- Firefox-first browser capture in a later milestone.
- Offline synchronization and mobile clients only after the server and synchronization contracts are mature.

## Native Architecture

```text
Browser / future clients
        |
        | versioned HTTPS API
        v
React + TypeScript + Vite + Glaze UI
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
- Design system: canonical GoreeCloud Glaze UI 1.0.0 with a locally vendored, revision-pinned web foundation.
- Rich editor: Tiptap/ProseMirror behind an application-owned `goreecloud.blocks` document contract.
- Backend: Python + FastAPI.
- Database: PostgreSQL with SQLAlchemy and Alembic migrations through `0007_admin_audit_events`.
- Search: PostgreSQL generated `tsvector` plus GIN index initially.
- API: versioned private HTTP APIs designed for browser, extension, and future mobile clients.
- Deployment: Docker and Docker Compose for development/integration validation; production placement is not approved.
- License: GNU Affero General Public License v3.0 only (`AGPL-3.0-only`).

## Glaze UI 1.0

GoreeCloud Notes targets Glaze UI 1.0.0 and keeps the reusable design-system foundation local to the application. The exact canonical revision and license are recorded under `frontend/src/glaze/`; Notes-specific composition remains separate in `frontend/src/glaze-foundation.css`.

The frontend currently includes:

- Canvas, Solid, Raised, Glaze, and Overlay surface mapping.
- Semantic Glaze color, depth, radius, spacing, target, and motion tokens.
- System, Light, and Dark appearance choices stored locally in the browser.
- Cross-tab appearance synchronization without sending the preference to the server.
- Compact, Medium, Expanded, and Wide adaptive-range contracts.
- Visible keyboard focus and practical touch/coarse-pointer targets.
- Reduced-motion, reduced-transparency, increased-contrast, forced-colors, and no-backdrop-filter fallbacks.
- A unified Glaze utility overlay for appearance and Account & Security access.
- A production-build conformance test that verifies the exact canonical Glaze snapshots, load order, local-only UI dependency boundary, responsive ranges, accessibility fallbacks, and appearance contract.

Source conformance does not replace manual Compact/Expanded Light/Dark visual acceptance on supported target browsers and devices before a stable release.

See `docs/glaze-ui-conformance.md`.

## Current Foundation

The current native branch includes:

- Private authentication with salted `scrypt` credentials, opaque database sessions, CSRF protection, bounded login-abuse controls, password rotation/recovery, active-session review, and global revocation after credential changes.
- Local administrative account creation, reset, suspension, and reinstatement with append-only privileged-account audit records and production operator/reason requirements.
- Owner-scoped notes, nested notebooks, tags, pinning, Archive/restore, recoverable Trash, and richer organization management.
- Structured rich editing, optimistic concurrency, immutable revisions, and conflict-safe restore.
- Indexed PostgreSQL full-text search with owner isolation.
- Private attachment storage, safe raster previews, attachment-ID inline images, aggregate owner quotas, reference-aware deletion protection, and a separate non-destructive attachment-store integrity audit.
- Verified full-library native ZIP export through administrative CLI and authenticated browser delivery.
- Verified administrator-operated native re-import into an explicitly confirmed empty existing account, including staged attachment hashing and relationship validation.
- Destructive disposable native export/re-import/re-export equivalence coverage.
- Controlled Memos migration inspection, deterministic manifest generation, attachment-byte evidence, explicit empty-target import, post-import verification, and migration-provenance preservation through native portability.
- A read-only Evernote ENEX inspection checkpoint that validates source structure, timestamps, embedded-resource integrity, source SHA-256, and mutation-free inventory without yet claiming ENML conversion or import readiness.
- Reproducible frontend/backend dependency locks.
- Fail-closed production configuration rules for browser origins, secure cookies, trusted proxies, database secrets, attachment storage, and per-owner attachment quota.
- Separate process liveness (`/health`) and dependency readiness (`/ready`).
- Centralized privacy-first private API response hardening.
- Destructive disposable PostgreSQL-plus-attachment backup/restore validation.
- Dedicated Continuous Integration and Production Runtime Preflight workflows.

## Repository Structure

```text
goreecloud-notes/
├── frontend/                 # React/TypeScript/Vite web application
│   └── src/glaze/            # Revision-pinned canonical Glaze UI web snapshot + license
├── backend/                  # FastAPI application, migrations, lockfile, and tests
├── docker/                   # Container/deployment support
├── docs/                     # Architecture, security, migration, recovery, and readiness records
├── scripts/                  # Versioned live integration validation
├── tests/                    # Cross-component and future end-to-end tests
├── .github/workflows/        # CI and source-level production preflight
├── .env.example              # Sanitized development configuration template
├── compose.yml               # Development Compose stack
├── CONTRIBUTING.md
├── LICENSE
└── README.md
```

## Safety Boundaries

- Do not commit passwords, tokens, private keys, production session values, or reusable credentials.
- Do not use production personal/family notes as a development dataset.
- Do not modify or delete the protected Memos migration source merely because native development advances.
- Do not publish backend ports directly to the public internet.
- Do not treat a green CI run, static preflight, container build, or draft pull request as production approval.
- Preserve migration traceability, data portability, backup protection, rollback capability, and owner isolation throughout development.
- Do not allow arbitrary external URLs to bypass the private attachment model.
- Do not enable permanent native deletion until retention and recovery policy is separately approved.

## Stable-Release Gates Still Open

Source maturity is not the same as target-environment readiness. Major remaining gates include:

- Final Family Services VM placement and persistent storage paths.
- Protected-copy Memos attachment extraction and production-representative migration rehearsal.
- Production Kopia repository, encryption, retention, off-host/off-site protection, selected RPO, measured RTO, and isolated restore evidence.
- Final frontend/static serving, Caddy, trusted-proxy, browser CSP/HSTS, DNS/NetBird reconstruction, and private-publication contract.
- Production monitoring, alert routing, integrity-audit scheduling, and publication-layer abuse controls.
- Final attachment capacity/quota, malware scanning/quarantine, large-object behavior, and storage architecture.
- Production operator/host authorization, canonical operator identity, audit retention/read access/monitoring, and account lifecycle runbooks.
- Real-device/network Glaze UI performance and accessibility acceptance.
- ENEX resource extraction, provider-neutral normalization, reviewed ENML conversion, isolated import, post-import equivalence, and protected-copy rehearsal.
- Populated-library merge/conflict semantics, selective restore, synchronization, scheduled/encrypted export UX, and large-library/background-job policy if later approved.

## Documentation

Start with the following records for current implementation boundaries:

- `docs/architecture.md`
- `docs/account-security.md`
- `docs/admin-audit.md`
- `docs/attachments.md`
- `docs/attachment-integrity.md`
- `docs/revisions.md`
- `docs/migration.md`
- `docs/enex-migration.md`
- `docs/portable-export.md`
- `docs/native-import.md`
- `docs/backup-restore.md`
- `docs/production-readiness.md`
- `docs/glaze-ui-conformance.md`

## Branch Model

- `main` — reviewed stable repository state.
- `feature/*` — isolated feature development.
- `fix/*` — bug fixes.
- `security/*` — security changes.

A permanent `develop` branch is not required unless project complexity later demonstrates a real need.

## License

GoreeCloud Notes is licensed under the GNU Affero General Public License v3.0 only (`AGPL-3.0-only`). See `LICENSE`.

The vendored Glaze UI foundation retains the canonical MIT license under `frontend/src/glaze/LICENSE`.