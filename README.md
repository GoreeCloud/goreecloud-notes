# GoreeCloud Notes

GoreeCloud Notes is a privacy-first, self-hosted note-taking, knowledge-management, and personal-productivity application developed as original GoreeCloud-owned software.

## Status

**Milestone 0 — Native Foundation is in active development. Production deployment is not approved.**

The active development line is draft PR #1 on `feature/native-foundation`. Source-level validation is substantial, but production cutover remains gated by protected-source migration rehearsal, target storage and recovery evidence, final private-publication controls, monitoring, operator procedures, and real-device acceptance.

GoreeCloud Memos remains a separate lightweight quick-capture product and is not replaced or retired by native Notes development.

## Product direction

GoreeCloud Notes is designed as a private Evernote-class knowledge workspace with:

- low-friction note capture;
- notebooks and nested notebooks;
- tags, pinning, Archive, and recoverable Trash;
- structured rich editing with Markdown interoperability;
- private attachments and inline images;
- full-text search and filtering;
- immutable revisions and conflict-safe recovery;
- portable full-library export and controlled migration/import tooling;
- owner-scoped internal links/backlinks and private templates;
- Firefox-first browser capture in a later milestone; and
- offline/mobile clients only after server and synchronization contracts mature.

## Architecture

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

Current foundation:

- **Frontend:** React, TypeScript, Vite, Tiptap/ProseMirror, canonical Glaze UI 1.0.
- **Document contract:** application-owned `goreecloud.blocks` v1.
- **Backend:** Python + FastAPI.
- **Database:** PostgreSQL with SQLAlchemy and Alembic through `0008_note_links`.
- **Search:** PostgreSQL generated `tsvector` plus GIN indexing.
- **Deployment validation:** Docker and Docker Compose; production placement is not approved.
- **License:** GNU Affero General Public License v3.0 only (`AGPL-3.0-only`).

## Current source-validated foundation

The native branch includes:

- private authentication, opaque sessions, CSRF protection, bounded login-abuse controls, password recovery/rotation, session review, and account suspension/reinstatement;
- append-only privileged-account audit records with production operator/reason requirements;
- owner-scoped notes, notebooks, nested notebooks, tags, pinning, Archive, recoverable Trash, and organization management;
- structured rich editing, optimistic concurrency, immutable revisions, and conflict-safe restore;
- a Glaze unsaved-draft navigation guard that protects note/view changes, new-note actions, sign-out, Archive/Trash/Restore context changes, and browser unload while preserving explicit Save and the existing optimistic-concurrency path;
- owner-scoped internal note links/backlinks with the portable note document as source of truth and a derived same-owner PostgreSQL lookup index;
- built-in private note templates;
- indexed owner-isolated PostgreSQL full-text search;
- private attachment storage, safe raster previews, attachment-ID inline images, owner quotas, reference-aware deletion protection, and non-destructive attachment integrity auditing;
- authenticated browser and administrator CLI full-library native export;
- explicit empty-target native re-import with staged attachment hashing and relationship validation;
- destructive disposable native export/re-import/re-export equivalence coverage;
- controlled Memos inspection, migration manifest/evidence, isolated empty-target import, post-import verification, and provenance preservation;
- Evernote ENEX read-only inspection, controlled resource extraction, exact-preservation provider-neutral normalization, and deterministic **zero-write ENML → `goreecloud.blocks` conversion review**;
- locked frontend/backend dependencies and fail-closed production configuration;
- separate liveness (`/health`) and dependency readiness (`/ready`);
- centralized private API response hardening;
- destructive disposable PostgreSQL-plus-attachment backup/restore validation; and
- dedicated Continuous Integration and Production Runtime Preflight workflows.

The draft-navigation guard presents a local Glaze Overlay with **Cancel**, **Discard & continue**, and **Save & continue**. Save & continue activates the existing Save action rather than implementing a second persistence path; failed saves and optimistic-concurrency conflicts keep navigation blocked. Only the explicitly destructive discard path may intentionally leave a local draft unsaved. See `docs/unsaved-navigation.md`.

## Evernote migration boundary

The ENEX migration path is deliberately staged:

1. read-only source inspection;
2. controlled resource extraction and binary evidence;
3. exact original UTF-8 ENML preservation in a deterministic provider-neutral normalization artifact;
4. deterministic zero-write conversion into `goreecloud.blocks` candidate documents with explicit review/blocking evidence.

Stage 4 does **not** import data. It preserves unsupported semantics as review evidence instead of silently discarding them. Tables currently block a candidate note because the native v1 document contract has no table node. Generic link targets, styling, Evernote checkboxes/encryption, non-image media placement, and resources not referenced by ENML are explicitly marked for review. Verified safe raster media may receive deterministic future attachment IDs for candidate `attachmentImage` blocks, but no native attachment is created.

Remaining ENEX gates are isolated empty-target native import, post-import equivalence/resource-integrity validation, protected-copy production-representative rehearsal, and final migration approval. See `docs/enex-migration.md` and `docs/enex-conversion.md`.

## Glaze UI 1.0

The frontend vendors the canonical Glaze UI web foundation locally with provenance and license text. Notes maps product styling onto shared semantic tokens and preserves:

- System, Light, and Dark appearance;
- Compact, Medium, Expanded, and Wide adaptive ranges;
- visible keyboard focus and practical pointer targets;
- reduced-motion and reduced-transparency fallbacks;
- increased-contrast and forced-colors behavior;
- Overlay semantics and solid fallbacks for draft-protection dialogs; and
- CI-enforced local-only Glaze conformance.

Source conformance does not replace real-device Compact/Expanded Light/Dark performance, accessibility, and draft-navigation acceptance before Stable release.

## Validation model

Every pull-request head runs locked backend/frontend validation plus the full Compose integration chain. Stable-source evidence is accepted only for the **exact head** under review.

The integration chain covers database migration round trips, readiness, authentication/CSRF, administrative audit immutability, login/trusted-proxy behavior, notes/revisions/lifecycle, internal links/backlinks, notebook/tag organization, PostgreSQL search/isolation, attachment authorization/quota/integrity, CLI/browser export, destructive native re-import, Memos import/equivalence/provenance, destructive database-plus-attachment recovery, diagnostics, and clean teardown. The frontend production build separately fails closed if the unsaved-navigation interaction contract or its Glaze accessibility/resilience requirements regress.

Production Runtime Preflight uses synthetic production configuration only. A green CI or preflight run is not deployment approval.

## Repository structure

```text
goreecloud-notes/
├── frontend/                 # React/TypeScript/Vite + local Glaze UI
├── backend/                  # FastAPI, migrations, migration tools, tests
├── docker/                   # Container/deployment support
├── docs/                     # Architecture, security, migration, recovery
├── scripts/                  # Versioned integration validation
├── tests/                    # Cross-component/future end-to-end tests
├── .github/workflows/        # CI and production-runtime preflight
├── compose.yml
├── CONTRIBUTING.md
├── LICENSE
└── README.md
```

## Safety boundaries

- Never commit passwords, tokens, private keys, production sessions, or reusable credentials.
- Never use production personal/family notes as a development dataset.
- Do not modify or delete protected migration sources merely because native development advances.
- Do not publish backend ports directly to the public internet.
- Do not treat green source validation as production approval.
- Preserve migration traceability, portability, backup protection, rollback capability, and owner isolation.
- Do not enable permanent native deletion until retention/recovery policy is separately approved.

## Stable-release gates still open

Major remaining gates include:

- final Family Services VM placement and persistent storage paths;
- protected-copy Memos migration rehearsal;
- production Kopia encryption/retention/off-host/off-site recovery with selected RPO and measured RTO;
- final frontend/static serving, Caddy, trusted proxies, CSP/HSTS, DNS/NetBird reconstruction, and private-publication controls;
- production monitoring, alert routing, integrity-audit scheduling, and abuse controls;
- final attachment capacity/quota, malware-scanning/quarantine, large-object behavior, permissions, and storage architecture;
- operator/host authorization, audit retention/access/monitoring, and account lifecycle runbooks;
- production image/release/rollback policy and administrator acceptance;
- real-device/network Glaze performance, accessibility, and draft-navigation acceptance; and
- remaining ENEX native-import, equivalence, protected-copy rehearsal, and final migration approval.

## Documentation

Start with:

- `docs/architecture.md`
- `docs/account-security.md`
- `docs/admin-audit.md`
- `docs/attachments.md`
- `docs/attachment-integrity.md`
- `docs/revisions.md`
- `docs/unsaved-navigation.md`
- `docs/migration.md`
- `docs/enex-migration.md`
- `docs/enex-conversion.md`
- `docs/portable-export.md`
- `docs/native-import.md`
- `docs/backup-restore.md`
- `docs/production-readiness.md`
- `docs/glaze-ui-conformance.md`

## Branch model

- `main` — reviewed stable repository state.
- `feature/*` — isolated feature development.
- `fix/*` — bug fixes.
- `security/*` — security changes.

A permanent `develop` branch is not required unless project complexity later demonstrates a concrete need.

## License

GoreeCloud Notes is licensed under `AGPL-3.0-only`. The vendored Glaze UI foundation retains its canonical MIT license under `frontend/src/glaze/LICENSE`.