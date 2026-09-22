# GoreeCloud Notes — Implemented Features

**Record type:** Repository implemented-feature inventory  
**Repository:** `GoreeCloud/goreecloud-notes`  
**Lifecycle:** Development  
**Migration state:** Candidate on `migration/repository-feature-records-20260922`; authoritative only after accepted merge to `main`.  
**Evidence baseline:** authoritative `main` at `3b7fe544c01e0336c28daee050bfcc2a5d480ab8`.  
**Governing standard:** Standard — Repository Feature Tracking and Changelog Governance v1.0.

## Interpretation

This record describes only capabilities established on authoritative `main`. Open Draft pull requests—including the native Notes foundation and its stacked platform, Browser-capture, Knowledge Home, and Android-readiness work—remain candidate-only and are not promoted into implemented state here.

GoreeCloud Notes remains Development. Source or CI evidence on Draft branches does not establish production publication, migration cutover, current-Stable GLAZE UI application acceptance, native Android readiness, production platform-system integration, Release Candidate status, production acceptance, or Stable qualification.

## Implemented on authoritative `main`

### Repository and product identity
- The repository is established as the native GoreeCloud Notes codebase for original GoreeCloud-owned development.
- GoreeCloud Notes is defined as a note-taking, knowledge-management, and personal-productivity application.
- The transitional Memos-based Notes implementation is explicitly preserved separately as migration source/historical reference until the native replacement is validated.

### Licensing
- The repository declares GNU Affero General Public License version 3 only (`AGPL-3.0-only`) and contains the corresponding repository license record.

### Governance baseline
- Root `FEATURE-ROADMAP.md` is the legacy repository-side roadmap control currently being migrated by this branch.
- Accepted `main` documents that active application development occurs through reviewed feature branches and pull requests rather than direct feature implementation on `main`.

## Explicitly not accepted on current `main`

Authoritative `main` does **not** establish acceptance of the substantive native Notes application stack currently represented in open Draft PRs, including:
- owner-isolated native Notes backend/runtime capability;
- structured-note, revision, lifecycle, search, attachment, notebook/tag, link/backlink, template, portability, or migration implementation from Draft branches;
- Knowledge Home, Scratch Pad promotion, Relevant Notes, or direct note navigation;
- Browser-to-Notes capture contracts or replay controls;
- current-Stable GLAZE UI application migration or rendered/accessibility/device acceptance;
- native Android client APIs, Identity binding, synchronization/offline reconciliation, attachment transfer, local-data protection, Android application source, or mobile release acceptance;
- accepted Manager, Privacy Shield, Wardveil Security, Everkeep, Mesh, Identity, or Sync runtime integration;
- production publication, production-data migration, signing/provenance, Release Candidate, production, or Stable qualification.

## Maintenance rule

When a capability is accepted on authoritative `main`, update this file, reconcile its open obligation in `PLANNED-FEATURES.md`, and record the meaningful change in `CHANGELOGS.md` through the governed repository workflow.