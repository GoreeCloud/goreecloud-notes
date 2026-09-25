# GoreeCloud Notes — Project Specifications

**Repository:** `GoreeCloud/goreecloud-notes`  
**Project type:** First-party notes, knowledge-management, and personal-productivity application  
**Lifecycle:** Development  
**Repository visibility:** Public  
**Default branch:** `main`  
**Migration baseline:** `f371b84cd593fd764794013522c47ad3986b116e`  
**License:** AGPL-3.0-only  
**Canonical product address:** `https://notes.goreecloud.com` when production cutover is separately accepted  
**Canonical authority:** This file is the authoritative project specification once accepted on the default branch.

## Authority and migration boundary

This specification reconciles the active Google Drive **Project Specification — Notes** with accepted repository state.

Authoritative `main` intentionally does not claim the substantive native Notes application stack as implemented. Native backend, Knowledge Home, Browser capture, Android-readiness, platform-system, migration, and related work in open Draft pull requests remains candidate evidence only until accepted, merged, and read back from `main`.

Detailed accepted/open feature state is maintained by `IMPLEMENTED-FEATURES.md`, `PLANNED-FEATURES.md`, `CHANGELOGS.md`, and accepted repository evidence.

## Product role

GoreeCloud Notes is the full GoreeCloud notes and knowledge-management product. It owns durable notes, knowledge organization, rich editing, attachments, revision/history recovery, search, internal note relationships, templates, portability, controlled migration, and deeper long-form knowledge workflows.

## Notes and Memos boundary

GoreeCloud Notes and GoreeCloud Memos are separate products.

- **Notes** is the deeper knowledge-management application.
- **Memos** is the lightweight quick-capture product.

The historical Notes-branded Memos deployment is protected migration/history evidence for Notes, but that history does not make GoreeCloud Memos disposable or subordinate. Notes may support controlled Memos handoff/interoperability without absorbing Memos authority.

## Native-development requirement

Notes must be original GoreeCloud-owned software built from the ground up.

Historical Memos-based Notes code, complete third-party products, or maintained forks may be used only as migration/reference inputs where permitted. Narrow mature foundations may remain dependencies when independent replacement would materially increase security, standards, protocol, rendering, runtime, or interoperability risk.

## Core knowledge-management scope

The approved Notes scope includes:
- notebooks and nested notebooks/folders;
- All Notes and durable note collections;
- tags;
- favorites/shortcuts;
- pinned notes;
- Archive and recoverable Trash;
- attachments and inline images;
- rich editing with Markdown interoperability;
- checklists, headings, tables, code blocks, and links;
- global full-text search and filters;
- internal note links and backlinks;
- note history and revision recovery;
- templates;
- portable full-library export;
- controlled import/migration tooling; and
- responsive, accessible knowledge workflows.

A capability remains planned or candidate-only until accepted repository evidence establishes implementation.

## Knowledge Home and capture

Notes may provide a customizable native Knowledge Home with modules such as Recent Notes, Relevant Notes, Pinned Notes, Scratch Pad, Shortcuts, Tags, Recently Captured, and provider-owned Tasks/Calendar context where accepted integrations exist.

Relevant/Suggested Notes must use transparent deterministic rules or separately approved and accepted intelligence. The UI must not imply AI or personalization that is not implemented.

Scratch Pad is transient capture that may promote content into a durable Note. It must not become an undocumented parallel authoritative note store.

Browser capture must preserve source provenance, use bounded explicit intent data, prevent replay where appropriate, enforce Notes authorization, and avoid turning arbitrary browser content into trusted active data.

## Data, storage, and owner isolation

Every authoritative Notes object must be owner-scoped and authorization must be enforced server-side.

The native data model must support structured content, notebooks/tags, lifecycle state, revisions, attachments, links/backlinks, templates, migration provenance, search indexing, portability, and recovery.

PostgreSQL is the preferred relational authority unless a separately approved architecture change replaces it. Attachment storage must remain owner-scoped, integrity-verifiable, recoverable, and abstracted from application semantics.

Derived indexes, caches, recommendations, or projections are rebuildable state and must not silently become authoritative note content.

## Rich editing and draft protection

Editing must avoid silent overwrite, preserve revision history, protect unsaved drafts during navigation, make discard explicit, preserve portable content semantics, and remain accessible to keyboard, touch, and assistive technology.

Internal note links/backlinks must resolve through owner-authorized note identity rather than display-title guessing or unsafe generic routing.

## Attachments

Attachments must remain private and owner-scoped.

Requirements include bounded upload/storage behavior, path/key containment, symlink safety, size/integrity verification, safe inline rendering, read-only integrity auditing, controlled orphan handling, quota enforcement, backup/recovery, and Wardveil Security integration where applicable.

A security-clean result does not by itself authorize active-content execution.

## Migration and protected source preservation

The historical Notes-branded Memos environment is a protected migration source until migration, equivalence, rollback, and recovery requirements are proven.

Migration must preserve or account for note content, attachments, labels/tags, colors/state where applicable, pinned/archive/Trash state, timestamps, ownership, source provenance, unsupported source semantics, note counts, searchability, and exportability.

Protected migration sources must not be deleted, overwritten, or mutated merely because native Development work exists.

## Import, export, and round-trip integrity

Notes requires a native portable full-library format and controlled import.

Export should preserve accepted native content, organization, revisions, attachments, metadata, and migration provenance while excluding credentials, sessions, rate-limit state, deployment secrets, and derived indexes.

Import must validate before mutation, enforce target-state rules, verify attachment bytes and relationships, refuse unsafe collisions, and preserve identity/ownership semantics.

Round-trip validation should establish usable equivalence across export → clean target → import → re-export.

## External migration

ENEX and other external imports must be inspect-first and staged: source inspection, bounded resource extraction, provider-neutral normalization, conversion into reviewable native candidates, controlled target import, and post-import equivalence/integrity validation.

Unsupported semantics must be preserved as evidence or blocked rather than silently flattened.

## Cross-application authority

Tasks, Calendar, Memos, Notify, Identity, Mesh, Privacy Shield, Wardveil Security, Everkeep, Manager, and other GoreeCloud systems retain authority for their own domains.

Notes may present or coordinate provider-owned context only through accepted interfaces and must not manufacture provider state.

## Glaze UI and accessibility

Notes must use the latest accepted Stable Glaze UI contract applicable at candidate acceptance time. Historical Drive references to fixed Glaze versions are migration history, not a permanent version pin.

Application-specific acceptance must cover responsive form factors, keyboard/touch operation, visible focus, screen-reader semantics, RTL, 200% text adaptation, Reduced Motion, Reduced Transparency, Increased/Forced Contrast, local assets, material/depth semantics, performance, representative browser/device rendering, and Human Visual Excellence review where required.

## Android and offline roadmap

A native Android client is separately gated. Before acceptance it requires versioned owner-scoped mobile APIs, native Identity binding, synchronization/change tokens, conflict/tombstone semantics, retry/idempotency, offline reconciliation, authenticated attachment transfer, local-data protection, logout/revocation/cache invalidation, privacy/security/recovery controls, Glaze UI accessibility, representative physical-device evidence, signing/provenance, rollback, and release approval.

## Backup, recovery, and resilience

Production Notes requires database and attachment backup, clean-target restore, integrity validation, rollback, off-device recovery where applicable, defined recovery objectives, export portability, and alerting for integrity failures.

Export alone is not a substitute for operational backup/recovery. Everkeep acceptance remains separately required where applicable.

## Privacy and security

Notes handles private personal knowledge and must minimize disclosure by default.

Requirements include no advertising or behavioral tracking, protected owner data, data-minimized logs, safe error disclosure, secure headers and trusted-proxy behavior, secret/key protection, dependency/supply-chain controls, integrity-protected privileged audit trails where applicable, Privacy Shield acceptance, and Wardveil acceptance for applicable security boundaries.

## Production and cutover gates

The native application must not replace the historical Notes-branded Memos deployment or take over `notes.goreecloud.com` until the exact candidate satisfies migration, recovery, security/privacy, accessibility, performance, representative runtime, monitoring, publication, rollback, signing/provenance, and release gates.

Cutover must include an explicit recovery/rollback path and must not retire GoreeCloud Memos as a separate product.

## Current accepted implementation boundary

At migration baseline `main`, accepted Notes state is intentionally narrow:
- repository/product identity;
- AGPL-3.0-only licensing;
- repository-native feature/changelog governance; and
- the protected relationship to the historical Memos-based migration source.

The substantive native application stack remains Draft/candidate work and is not accepted on `main`.

## Open obligations

`PLANNED-FEATURES.md` is the authoritative detailed open/partial/blocked inventory. This project specification defines project-level requirements and authority boundaries; it does not convert Draft work into implementation.

## Maintenance

Update this specification when product scope, Notes/Memos separation, data/storage architecture, migration policy, supported clients, security/privacy authority, Glaze requirements, integrations, deployment/cutover, licensing, or acceptance gates materially change.

## Related repository documentation

- [README.md](README.md)
- [PROJECT-RECORD.md](PROJECT-RECORD.md)
- [IMPLEMENTED-FEATURES.md](IMPLEMENTED-FEATURES.md)
- [PLANNED-FEATURES.md](PLANNED-FEATURES.md)
- [CHANGELOGS.md](CHANGELOGS.md)
- [docs/project-record-history/](docs/project-record-history/) — normalized migration history from the former Drive project specification.
- [LICENSE](LICENSE)
- [BRANDING.md](BRANDING.md)
