# GoreeCloud Notes Android Client Readiness

## Purpose

GoreeCloud Notes is expected to gain a first-party Android client, but the authoritative Notes specification places native mobile work in **Milestone 5 — Mobility and Offline Work**. Android development must therefore follow the server API and synchronization foundations required to preserve Notes authority, privacy, recovery, and conflict semantics.

This document defines the current Development boundary. It does not authorize an Android application, package name, production credential, deployment, release, or Stable claim.

## Why the client is intentionally blocked today

A visually complete Android shell without a mature mobile data contract would create the wrong architecture. Notes must not rely on browser-cookie reuse, embedded service credentials, direct database access, duplicated client-side ownership rules, or an offline database that silently becomes a competing source of truth.

The server remains authoritative for account ownership, note authorization, lifecycle state, revisions, attachments, and accepted mutation results. Native clients may cache and stage work only under explicitly defined synchronization and reconciliation contracts.

## Required prerequisites

The source-controlled status is recorded in `platform/mobile-client-readiness.json` and is tested by the backend CI suite.

### Mobile API contract

Notes needs versioned, owner-scoped native API contracts for the minimum list/detail/mutation operations required by mobile. Contracts must define exact request/response fields, pagination/change boundaries, error behavior, authorization recalculation, revision preconditions, and data minimization. Unknown fields and unsupported authority must fail closed at consumer boundaries.

### Native GoreeCloud Identity binding

Android must use an accepted GoreeCloud Identity native-session exchange scoped to the Notes application and current principal. Browser cookies, reusable embedded service credentials, client-selected owners, and direct reuse of web-session state are not acceptable native authentication architecture.

### Incremental synchronization and conflicts

Offline work requires explicit change/revision tokens, tombstone/deletion semantics, idempotent retry behavior, conflict detection, conflict presentation/resolution, ordering rules, and safe recovery after partial failure. Synchronization success must not be presented as backup or recoverability.

### Attachment transfer

Native attachment behavior needs authenticated bounded upload/download contracts, resource identity, integrity verification, retry/resume semantics where required, cache invalidation, offline metadata behavior, and failure recovery. Local attachment copies remain caches unless separate authoritative evidence says otherwise.

### Local data protection

The Android client must define what data may be retained locally, how it is minimized and protected, what is removed on logout/revocation, what can participate in device backup, how diagnostics avoid note content, and how clean-target restore behaves. Local persistence must not manufacture server, Privacy Shield, Wardveil, Everkeep, or Sync authority.

### Platform systems

Android-specific acceptance remains required for Privacy Shield, Wardveil Security, Everkeep, GoreeCloud Identity, and GoreeCloud Sync. Applicable Manager and Mesh integration must also be evaluated before release. Each authority remains independently evidenced; one system's success may not be substituted for another.

### GLAZE UI

When Android implementation begins, it must start from the then-current **Stable** GLAZE UI baseline rather than inheriting the web application's historical Glaze version. Application acceptance remains independent and requires Android-rendered, accessibility, form-factor, physical-device, performance, rollback, and applicable human/manual evidence.

### Representative Android acceptance

Before Release Candidate or Stable qualification, Notes Android requires representative physical-device validation, TalkBack/accessibility testing, text scaling/reflow, reduced motion/transparency/contrast behavior, keyboard/switch behavior where applicable, network-loss/retry behavior, battery/background constraints, protected signing/provenance, upgrade/rollback, recovery, and release approval.

## Sequencing

1. Accept the mobile API surface and native Identity binding.
2. Accept incremental sync/conflict semantics and attachment transfer.
3. Accept local-data/privacy/security/recovery boundaries.
4. Establish the first-party Kotlin/Compose Android foundation on the current Stable GLAZE UI baseline.
5. Add bounded read behavior before mutation/offline authority.
6. Add mutation and offline reconciliation incrementally with exact-head validation.
7. Add optional capture/share/widget/notification/background features only after their independent permissions and authority contracts are accepted.
8. Complete representative-device, accessibility, performance, signing, recovery, rollback, release, and Stable gates.

## Current truth

Android status is **blocked-prerequisites**. No native Android implementation is represented as started, production capable, or Stable eligible by this repository checkpoint.
