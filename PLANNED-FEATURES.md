# GoreeCloud Notes — Planned Features

**Record type:** Repository planned/open feature inventory  
**Repository:** `GoreeCloud/goreecloud-notes`  
**Lifecycle:** Development  
**Migration state:** Candidate on `migration/repository-feature-records-20260922`; authoritative only after accepted merge to `main`.  
**Evidence baseline:** authoritative `main` at `3b7fe544c01e0336c28daee050bfcc2a5d480ab8`; later Draft PRs remain candidate-only.  
**Governing standard:** Standard — Repository Feature Tracking and Changelog Governance v1.0.

## Purpose and migration sources

This file carries forward open, partial, blocked, acceptance-gated, and future obligations from:
- the legacy root `FEATURE-ROADMAP.md`;
- the Drive roadmap `GoreeCloud/Feature Roadmap/GoreeCloud Notes/FEATURE-ROADMAP.docx` (file ID `1lQVN24S-54yY6qfPXvWkDhYf62dZQA5B`);
- authoritative `main` repository state.

Open Draft PRs remain candidate evidence only. Their code, tests, and documentation are not accepted implementation until merged and verified on authoritative `main`.

## Legacy roadmap disposition

| Legacy ID | Repository-native disposition |
| --- | --- |
| FR-001 | Superseded as a roadmap-control row by the maintenance rules in the repository-native feature/changelog records; continuous reconciliation remains required. |
| FR-002 | Continues under GoreeCloud Tasks Management when work remains actionable; this is governance rather than product implementation. |
| FR-003 | Evidence-backed lifecycle control remains; repository/Drive roadmap synchronization is superseded by repository-native authority. |
| FR-010 | Ongoing product boundary. Preserve Notes as the full knowledge-management product and Memos as the separate lightweight quick-capture product. |
| FR-011 | Open for authoritative-main acceptance. Draft native backend work covers structured notes, revisions, lifecycle, search, attachments, notebooks/tags, links/backlinks, templates, portability, and migration tooling, but current `main` does not yet accept that implementation. |
| FR-012 | Open. Knowledge Home work exists only in the Draft PR stack and remains candidate-only until accepted on `main`. |
| FR-013 | Open. Complete controlled migration from historical Notes-branded Memos with preserved meaning/provenance, protected-source rehearsal, equivalence checks, rollback, and production cutover approval. |
| FR-014 | Open. Migrate the accepted Notes web/PWA application to the then-current Stable GLAZE UI baseline and complete fresh source, rendered, accessibility, responsive, representative-browser/device, performance, rollback, and applicable human-visual acceptance. |
| FR-015 | Blocked/open production gate. Complete publication, monitoring, security headers, trusted-proxy policy, storage placement, recovery, signing/provenance, rollback, production approval, and Stable qualification. |
| FR-020 | Planned Android prerequisite. Define a versioned, owner-scoped, minimized mobile client API while preserving server authorization as authoritative. |
| FR-021 | Planned Android prerequisite. Define and validate native GoreeCloud Identity session binding without browser-cookie reuse, embedded reusable credentials, or client-selected owner authority. |
| FR-022 | Planned Android prerequisite. Define revision/change tokens, incremental sync, conflict resolution, tombstones/deletion semantics, retry/idempotency, and offline reconciliation. |
| FR-023 | Planned Android prerequisite. Define authenticated attachment transfer, integrity, bounded/resumable transfer where required, offline metadata, and safe retry without making caches authoritative. |
| FR-024 | Planned Android prerequisite. Define local-data minimization/protection, cache invalidation, logout/revocation, diagnostics, and recovery under Privacy Shield, Wardveil Security, Everkeep, Identity, and Sync authority. |
| FR-025 | Blocked on FR-020 through FR-024. Establish a dedicated first-party Android/Kotlin/Compose client only after prerequisite contracts are source-ready and reviewed. Draft readiness governance does not itself satisfy this gate. |
| FR-026 | Blocked. Android presentation must start from the then-current Stable GLAZE UI version and remain fail-closed for application acceptance pending rendered/accessibility/form-factor/device/human evidence. |
| FR-027 | Planned after Android foundation. Add capture/share entry points, widgets, reminders/notifications, offline editing, background synchronization, and device integrations only after their independent authority/privacy/recovery/lifecycle contracts are accepted. |
| FR-028 | Final Android release gate. Complete representative physical-device, TalkBack/keyboard/switch accessibility, performance/battery/network-failure, signing/provenance, rollback, release approval, and Stable qualification. |

## Additional open candidate work preserved from repository history

The open Draft stack also contains candidate-only Browser capture contracts, one-time intent/replay controls, platform-system conformance declarations, Knowledge Home ranking/navigation work, and native application foundations. These remain open Development candidates until accepted on authoritative `main`; they must not be silently converted to implemented state by this migration.

## Repository-governance obligations

- Do not recreate `FEATURE-ROADMAP.md` after verified migration retirement.
- Do not create, synchronize, mirror, or retain a Notes roadmap or changelog in Google Drive after the applicable migration source is successfully retired.
- Keep `IMPLEMENTED-FEATURES.md`, this file, and `CHANGELOGS.md` synchronized with accepted `main` lifecycle truth.
- Preserve Draft/candidate evidence without promoting it to implemented state.
- Keep Android fail-closed until the defined API, Identity, synchronization, attachment, local-data, privacy/security/recovery, GLAZE UI, device, and release gates are actually satisfied.

## Maintenance rule

A capability remains here until its defined implementation and acceptance scope is complete. When accepted on authoritative `main`, update `IMPLEMENTED-FEATURES.md`, reconcile the corresponding obligation here, and record the meaningful event in `CHANGELOGS.md`.