# GoreeCloud Notes — Project Record

**Repository:** `GoreeCloud/goreecloud-notes`  
**Lifecycle:** Development  
**Record purpose:** Significant product decisions, native-transition history, protected-source migration context, candidate evidence, governance transitions, and project-specification migration provenance  
**Migration baseline:** `f371b84cd593fd764794013522c47ad3986b116e`  
**Canonical authority:** This file is the repository-local project record once accepted on the default branch.

## Product separation decision

GoreeCloud Notes is the full knowledge-management product. GoreeCloud Memos is the separate lightweight quick-capture product.

The historical Notes-branded Memos deployment remains protected migration/history evidence for Notes until controlled migration and cutover requirements are accepted. Its historical role does not make Memos a temporary or disposable product.

## Native transition

The project moved toward an original GoreeCloud-owned native Notes architecture rather than constraining the full Notes roadmap to the maintained Memos architecture.

The native replacement remains Development. Authoritative `main` intentionally keeps substantive native implementation outside accepted state while the implementation exists in open Draft pull-request stacks.

## Repository-native feature/change authority

Authoritative `main` already contains:
- `IMPLEMENTED-FEATURES.md`;
- `PLANNED-FEATURES.md`; and
- `CHANGELOGS.md`.

The mapped legacy Notes Drive feature roadmap has already been retired after the separate feature/changelog migration. This project-specification migration does not recreate Drive roadmap/changelog authority.

## Current accepted main boundary

At migration baseline `f371b84cd593fd764794013522c47ad3986b116e`, accepted `main` establishes:
- the native GoreeCloud Notes repository and product identity;
- AGPL-3.0-only licensing;
- repository-native feature/change governance; and
- the protected historical relationship to the Memos-based Notes migration source.

It does not accept the substantive native Notes application stack represented by open Draft pull requests.

## Candidate-stack boundary

Open Draft work includes the native Notes foundation, platform-system conformance, Browser capture contracts and replay controls, Knowledge Home, relevant-note ranking/navigation, and Android-readiness planning.

Candidate CI or source evidence remains exact-revision evidence for those branches only. It does not establish default-branch implementation, production publication, Stable qualification, migration cutover, or permission to mutate protected migration sources.

## Project-specification migration

The former Drive **Project Specification — Notes** contains 24 numbered sections plus extensive checkpoint detail. Because a single oversized verbatim GitHub write was rejected by the connector safety layer, the migration is segmented rather than flattened into one oversized root record.

The canonical normative requirements are consolidated in `PROJECT-SPECIFICATIONS.md`. Historical/source-era material is retained in bounded files under `docs/project-record-history/`, grouped by the original section ranges:
- Sections 1–8: product role, purpose, early Memos-era baseline, and GoreeCloud-specific historical changes;
- Sections 9–17: historical data-model strategy, privacy/security, deployment/storage, recovery, repository/release history, milestones, and native-transition decision;
- Sections 18–24: native product scope, architecture, migration/data preservation, native roadmap, product decision, Knowledge Home direction, and September 2026 Development continuation.

**Drive source:** Project Specification — Notes.docx  
**Drive file ID:** `1-RUxapBX-fQjf7XkU7IKR4gX0vsXR0ZL`  
**Drive deletion status:** Blocked until all segmented history is present, the migration PR is accepted, authoritative `main` readback succeeds, and no discrepancy remains.

## Historical interpretation rule

The history segments preserve source-era statements, exact-revision evidence, superseded architecture/version claims, and Draft checkpoints. They do not override current repository truth.

Where a historical segment says a feature is implemented on a Draft branch, that remains candidate evidence unless `IMPLEMENTED-FEATURES.md` and accepted `main` establish otherwise.

## Ongoing maintenance

Update this record for significant product-scope, Notes/Memos-boundary, architecture, governance, repository, migration/cutover, security/privacy, recovery, client-platform, lifecycle, split/merge/rename, deprecation, or retirement events.

Routine accepted feature/fix chronology remains in `CHANGELOGS.md`.
