# Notes Drive Project Specification History — Sections 18–24

**Source:** Google Drive `Project Specification — Notes.docx`  
**Source file ID:** `1-RUxapBX-fQjf7XkU7IKR4gX0vsXR0ZL`  
**Migration treatment:** Source-grounded normalized history. The original Drive source remains protected while this migration is pending.  
**Authority:** Historical/source-era and candidate evidence only. Current authority is `PROJECT-SPECIFICATIONS.md`, repository-native feature/change records, and accepted `main`.

## 18. Native product scope

The source defines GoreeCloud Notes as the larger full notes and knowledge-management product with notebooks/nested notebooks, All Notes, tags, favorites/shortcuts, pinning, Archive, recoverable Trash, attachments/inline images, rich editing with Markdown interoperability, checklists, headings, tables, code blocks, links, global search/filters, internal links/backlinks, revision recovery, templates, full-library export, and controlled import/migration tooling.

Quick Notes may exist inside Notes for convenience, but lightweight quick capture remains the primary role of the separate GoreeCloud Memos product.

Later opportunities include reminders, Tasks/Notify integration, OCR, saved searches, offline synchronization, mobile clients, and optional local AI search/summarization. The source treats these as planned opportunities rather than current production claims.

## 19. Preferred native architecture

The source's preferred native direction uses a React/TypeScript/Vite web/PWA client, Glaze UI, a structured open-source rich-text editor, FastAPI/Python backend, PostgreSQL as primary relational/search foundation, GoreeCloud-managed attachment storage behind an abstraction, and versioned HTTP APIs for browser, mobile, and GoreeCloud integrations.

A Firefox-first WebExtensions companion is planned for article, selection, URL, bookmark, and quick-note capture. Chromium compatibility may follow when it does not weaken privacy or maintenance. The server API is expected to support future mobile clients without a backend redesign.

Specific versions and dependencies remain subject to repository inspection and acceptance.

## 20. Migration and data preservation

The historical Memos-based Notes environment is a protected migration source. Native development alone does not authorize deletion or overwrite.

The source requires inventory/protection of the historical database, attachments, configuration, users, note content, labels/tags, colors/state, pin/archive/Trash state, timestamps, and export metadata.

A repeatable native import path must validate counts, content, metadata, attachments, ownership, searchability, and exportability before the historical Notes-branded Memos deployment can be retired or changed. Retiring that historical deployment must not retire the separate GoreeCloud Memos product.

The `notes.goreecloud.com` identity is reserved for native Notes and may move only through controlled cutover with rollback/recovery protection.

The source also records a staged ENEX migration design:
1. read-only bounded source inspection;
2. controlled resource extraction to a new destination;
3. provider-neutral normalization preserving exact ENML/source metadata;
4. deterministic conversion of supported content into reviewable native block candidates;
5. isolated empty-target native import; and
6. post-import equivalence/resource-integrity validation.

Source fingerprinting, symbolic-link refusal, size/count bounds, hash verification, unsupported-semantics preservation, and fail-closed handling are central to this flow. Protected-copy rehearsal and production approval remain separate gates.

Historical fixed Glaze-version language in this section is retained as source-era evidence only; current design-system requirements are controlled by the canonical project specification and live accepted Glaze authority.

## 21. Native development roadmap

The source records a large Draft Milestone 0 implementation program in PR #1, including:
- native repository and AGPL licensing;
- locked frontend/backend dependency controls;
- React/TypeScript/Vite and FastAPI foundations;
- PostgreSQL/SQLAlchemy persistence and Alembic migrations;
- private authentication and owner isolation;
- password rotation/recovery and login-abuse controls;
- structured rich editing and conflict-safe revisions;
- indexed search;
- private attachments/inline images;
- read-only attachment integrity auditing;
- organization management;
- native full-library export/import;
- migration provenance;
- synthetic Memos import/equivalence checks;
- destructive disposable database-plus-attachment recovery validation;
- privileged administrative audit records;
- private API response hardening;
- accessibility/resilience controls;
- rich-editor lazy loading and frontend performance budgeting; and
- repeated CI and synthetic production-preflight checkpoints.

The source is explicit that PR #1 remains Draft/unmerged and that these exact-head checks are candidate evidence only.

Milestone 0 remains open for protected-copy/live Memos migration rehearsal, production-grade backup/recovery and selected recovery objectives, publication/proxy/rate-limit/monitoring acceptance, remaining attachment scanning/quarantine/quota/storage decisions, scheduled integrity auditing, operator/host authorization and audit operations, production concurrency/background-job behavior, later import semantics, and ENEX target-import/production rehearsal.

Later roadmap milestones cover:
- core Notes/organization workflows;
- Evernote-class knowledge-workspace refinement;
- Memos/ENEX migration and browser capture;
- OCR/previews/richer knowledge capabilities; and
- mobility/offline synchronization and client work.

No source-era milestone claim in this history overrides the narrow accepted `main` boundary.

## 22. Product decision

The source formally separates:
- **GoreeCloud Notes:** original full notes and knowledge-management product, intended for `notes.goreecloud.com`;
- **GoreeCloud Memos:** separate maintained lightweight quick-note product, intended for `memos.goreecloud.com`.

The historical Notes-branded Memos implementation remains migration/history evidence, not proof that Memos itself is transitional or disposable.

Future Notes decisions are governed by Notes knowledge-management requirements; future Memos decisions are governed by the separate Memos specification. Controlled interoperability is allowed without merging the products.

The source also records a native-build mandate and platform-system evaluation requirement. Historical exact Glaze/platform-version pins are preserved as historical context; current requirements must be verified from present authority.

## 23. Approved product-experience direction — Knowledge Home

The source approves the direction, not automatic implementation acceptance.

It uses Evernote references only as workflow/information-architecture inspiration and explicitly rejects copying Evernote branding, assets, source code, proprietary implementation, or a pixel-identical UI.

Approved direction includes:
- a customizable Knowledge Home with Recent, Relevant/Suggested, Pinned, Scratch Pad, Shortcuts, Tags, Recently Captured, Tasks context, and Calendar context;
- user-controlled module visibility/order/size;
- transparent deterministic or separately accepted intelligence for recommendations;
- purpose-built Wide/Medium/Compact compositions rather than simple scaling;
- one coherent Notes creation/capture entry point;
- Scratch Pad promotion into durable Notes;
- controlled Memos handoff without replacing Memos;
- provenance-preserving Recently Captured;
- continued rich editing, templates, attachments, internal links/backlinks, revision recovery, search, notebooks/tags, and portability; and
- future richer media/OCR/table/reminder capabilities only after their contracts/evidence exist.

The source requires provider authority to remain explicit: Tasks owns tasks, Calendar owns calendar state, Everkeep owns recovery truth, Privacy Shield privacy state, Wardveil security/trust state, Identity authentication/authorization, and Mesh coordination where implemented. The Notes UI must not fabricate subsystem state.

It also records a Draft PR #10 Knowledge Home checkpoint with exact-head CI/preflight evidence. That evidence remains candidate-only; Suggested/Relevant Notes, Recently Captured provenance, Tasks/Calendar modules, Scratch Pad durable promotion, direct item navigation, rendered/device acceptance, production, and Stable gates were still open at the recorded checkpoint.

## 24. Development continuation — Scratch Pad promotion and Relevant Notes

The source records later Draft checkpoints:
- PR #10 advanced to a green exact head and added explicit Scratch Pad promotion through the existing owner-scoped Note creation path. Transient content clears only after durable creation succeeds.
- PR #11, stacked on PR #10, added Relevant Notes as deterministic local ranking over already-authorized Notes data, using explicit native note properties and stable ordering.

The source explicitly says this ranking added no model, embedding service, behavioral profile, click/dwell history, telemetry, remote recommendation call, cross-application data source, or persisted recommendation score.

Both remain Development/Draft evidence. CI and synthetic runtime preflight do not establish production deployment, complete rendered/accessibility acceptance, Stable qualification, Mesh/Tasks/Calendar authority, or permission to mutate protected migration sources.

## Interpretation

Sections 18–24 establish the native Notes scope and migration/product-experience direction while preserving a strict boundary between approved direction, Draft implementation evidence, and accepted authoritative `main`.
