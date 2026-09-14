# GoreeCloud Notes — Feature Roadmap

**Status:** Active roadmap control  
**Authoritative project record:** `GoreeCloud/Projects/Project Specification — Notes`  
**Canonical repository:** `GoreeCloud/goreecloud-notes`  
**Drive counterpart:** `GoreeCloud/Feature Roadmap/GoreeCloud Notes/FEATURE-ROADMAP.docx`

This file records current GoreeCloud Notes feature obligations and verified Development state. It does not replace the authoritative project specification, implementation evidence, release gates, or GoreeCloud Tasks Management. A feature is not complete or Stable merely because it appears here.

The repository and Drive roadmap copies must remain materially synchronized. Status changes require authoritative implementation/validation evidence. Historical Notes-branded Memos work remains migration/reference evidence and must not be treated as current native Notes implementation.

## Status vocabulary

- **Validated Development foundation** — source/CI evidence exists for the exact recorded Development revision, but production/Stable acceptance is not established.
- **Active** — implementation work is currently actionable or in progress.
- **Planned** — required/recommended work remains outstanding.
- **Blocked on prerequisite** — work is intentionally held until a safety/authority prerequisite exists.
- **Ongoing control** — governance obligation that remains continuously active.

## Roadmap

| ID | Feature / obligation | Priority | Current state |
| --- | --- | --- | --- |
| FR-001 | Reconcile every current planned or recommended Notes feature against the authoritative project record and verified repository evidence. | High | Ongoing control |
| FR-002 | Move actionable Notes obligations into GoreeCloud Tasks Management when required, preserving priority, dependency, and lifecycle disposition. | High | Ongoing control |
| FR-003 | Do not mark Notes features implemented, complete, cancelled, superseded, production accepted, or Stable without authoritative evidence and synchronized repository/Drive roadmap updates. | High | Ongoing control |
| FR-010 | Preserve GoreeCloud Notes as the full knowledge-management product while GoreeCloud Memos remains the separate lightweight quick-capture product. | High | Ongoing control |
| FR-011 | Owner-isolated native Notes backend with structured notes, revisions, lifecycle state, search, attachments, notebooks/tags, links/backlinks, templates, portability, and migration tooling. | High | Validated Development foundation; production gates remain open |
| FR-012 | Knowledge Home with owner-scoped Recent/Pinned/Relevant modules, Scratch Pad promotion, and safe navigation into authoritative note workspaces. | Medium | Active in Draft PR stack through PR #12 |
| FR-013 | Controlled migration from historical Notes-branded Memos, preserving note/attachment meaning and provenance without mutating protected source data. | High | Active; protected-source rehearsal and production cutover remain open |
| FR-014 | Current Stable GLAZE UI migration for the Notes web/PWA application with fresh source, rendered, accessibility, responsive, representative-device/browser, performance, rollback, and applicable human-visual acceptance. | High | Planned migration; active Notes stack still records historical V1.0 target and must not be represented as current-Stable accepted |
| FR-015 | Production publication, monitoring, security headers, trusted-proxy policy, data/storage placement, recovery evidence, signing/provenance, rollback, and Stable qualification. | High | Blocked on production acceptance gates |
| FR-020 | Define a versioned owner-scoped mobile client API that exposes only the minimum Notes data/actions required by native clients and preserves backend authorization as authoritative. | High | Planned / Android prerequisite |
| FR-021 | Define and validate GoreeCloud Identity native-session binding for Notes mobile clients without browser-cookie reuse, embedded reusable credentials, or client-selected owner authority. | High | Planned / Android prerequisite |
| FR-022 | Define revision/change tokens, incremental synchronization, conflict detection/resolution, deletion/tombstone semantics, retry/idempotency, and offline reconciliation before any native client claims offline work. | High | Planned / Android prerequisite |
| FR-023 | Define attachment transfer contracts for authenticated download/upload, integrity, bounded/resumable transfer where required, offline metadata, and safe retry without turning attachment caches into independent authority. | High | Planned / Android prerequisite |
| FR-024 | Define native-client local-data minimization, encryption/storage, cache invalidation, logout/revocation, diagnostics, and backup/recovery boundaries under Privacy Shield, Wardveil Security, Everkeep, Identity, and Sync authority. | High | Planned / Android prerequisite |
| FR-025 | Establish a dedicated first-party Android/Kotlin/Compose client only after the mobile API, Identity binding, synchronization/reconciliation, attachment, and local-data authority prerequisites are source-ready and reviewed. | High | Blocked on FR-020 through FR-024 |
| FR-026 | Android client presentation must start on the then-current Stable GLAZE UI version and remain fail-closed for application acceptance until rendered/accessibility/form-factor/device/human evidence exists. | High | Blocked on FR-025 and current Stable Glaze authority at implementation time |
| FR-027 | Android capture/share entry points, widgets, notifications/reminders, offline editing, background synchronization, and device integrations must be added only after their independent authority, privacy, recovery, and lifecycle contracts are accepted. | Medium | Planned after Android foundation |
| FR-028 | Representative Android physical-device validation, TalkBack/keyboard/switch/accessibility acceptance, performance/battery/network-failure testing, signing/provenance, rollback, release approval, and Stable qualification. | High | Planned; final Android release gates |

## Android implementation gate

The authoritative Notes specification places native Android/iOS work in **Milestone 5 — Mobility and Offline Work**, after the server API and synchronization contract are mature enough to support clients safely. The repository therefore must not create or represent a production-capable Android client merely to satisfy product presence.

`platform/mobile-client-readiness.json` is the source-controlled fail-closed prerequisite declaration for this boundary. Until every required prerequisite is accepted with evidence, Android application status remains `blocked-prerequisites` and no Android production/Stable claim is permitted.

## Current acceptance boundary

The current Notes implementation remains Development work. Passing source/CI checks does not establish production publication, current-Stable GLAZE UI application acceptance, Android readiness, native Identity, offline synchronization, Privacy Shield/Wardveil/Everkeep/Sync runtime acceptance, Release Candidate, production, or Stable status.
