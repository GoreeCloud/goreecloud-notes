# Notes Drive Project Specification History — Sections 9–17

**Source:** Google Drive `Project Specification — Notes.docx`  
**Source file ID:** `1-RUxapBX-fQjf7XkU7IKR4gX0vsXR0ZL`  
**Migration treatment:** Source-grounded normalized history. The original Drive source remains protected while this migration is pending.  
**Authority:** Historical/source-era evidence only. Current authority is `PROJECT-SPECIFICATIONS.md`, repository-native feature/change records, and accepted `main`.

## 9. Historical Memos data-model strategy — superseded for native development

The historical Memos-based Notes implementation reused Memos concepts directly: memo content for notes, first-H1 title behavior, pinned/archive state, tags and tag metadata for labels/colors, Markdown task lists for checklists, attachments for files/images, and creator ownership for per-user separation.

The source explicitly releases the native Notes application from those persistence constraints. Native Notes may model titles, notebooks, tags, colors, Trash state, revisions, links, attachments, and other concepts directly when that yields a clearer, more maintainable, testable, portable, and recoverable design.

## 10. Privacy and security

The source establishes Notes as a private GoreeCloud family service with these historical operating requirements:
- do not expose the backend application port directly to the public Internet;
- use approved private-network/DNS/Caddy HTTPS publication paths;
- disable open registration after approved accounts exist;
- use individual accounts rather than shared credentials;
- keep optional upstream AI providers disabled unless separately approved;
- do not require telemetry, hosted control planes, or proprietary authentication for core operation; and
- separate reusable secrets from source code, ordinary documentation, and ordinary configuration.

Later platform-specific security/privacy requirements are governed by current repository and GoreeCloud authority rather than these historical deployment details alone.

## 11. Deployment and storage

The source selected Docker/Compose for deployment and PostgreSQL as the preferred native relational database because the target product requires structured notebooks, relationships, revisions, richer search, migration tooling, and future multi-client synchronization.

Persistent application data and attachments are intended to live in GoreeCloud-managed storage.

The historical Notes-branded Memos RC was to remain on its existing SQLite source store until migration completed. Beginning native development did not authorize source-data deletion or mutation. The separate Memos product retained its own production-storage decision.

The historical long-term placement target was the Family Services VM; current deployment authority must be verified separately before treating that as present production state.

## 12. Backup and recovery

Stable production was conditioned on protecting and successfully restoring the database, attachments, configuration, secrets, and full application reconstruction path.

The historical recovery model called for:
- GitHub source recovery;
- reproducible container/image rebuilding;
- database restore;
- attachment restore;
- configuration restore;
- secret recovery from approved sensitive-information storage;
- reconstruction of Caddy, DNS, and private-network publication; and
- a tested end-to-end restoration procedure.

Kopia was identified as the intended persistent-data protection mechanism after production storage paths were finalized. Current backup/recovery implementation must still be established from accepted evidence.

## 13. Repository and release model — native transition

The source records `GoreeCloud/goreecloud-notes` as the native Notes repository and `GoreeCloud/memos` as the separate maintained Memos repository and migration source.

The preferred historical branch model was:
- `main` for stable/accepted GoreeCloud code;
- `feature/*` for isolated feature development;
- `fix/*` for bug fixes;
- `security/*` for security work; and
- temporary `upstream-sync/*` branches when needed.

The Notes-branded Memos RC3 prerelease remains historical migration/reference evidence and is not automatically a Stable Memos release. Notes and Memos have independent product-development and release governance.

## 14. Development milestones — historical plan and gate tracking

The source records these Memos-era milestones:
- **Milestone 0 — Fork Foundation:** completed establishment of the GoreeCloud Memos fork, upstream provenance, initial branch, and build/test/sync documentation.
- **Milestone 1 — GoreeCloud Identity and Private UX:** completed in the RC line with branding, private-default behavior, reduced public/social prominence, attribution, and tests.
- **Milestone 2 — Keep-Style Notes Workspace:** implemented in RC2 and desktop-polished in RC3, including composer/workspace/pinning/title/card-action work. Mobile/PWA source readiness existed, but real-device acceptance remained open.
- **Milestone 3 — GoreeCloud Note State:** implemented colors, Trash/restore/permanent-delete flows, portable exports, and associated testing in the RC line.
- **Milestone 4 — Deployment and Recovery:** only partial; private publication, monitoring, backup, restore testing, and production approval remained gated.

These milestones are historical Memos-based Notes evidence, not the current native Notes acceptance model.

## 15. Historical Phase 2 opportunities — reclassified in native roadmap

The source listed reminders/ntfy, selected family sharing, better offline/PWA behavior, optional local AI, Google Keep import, and improved version-history/recovery as later opportunities.

These were reclassified under the native Notes roadmap rather than retained as a Memos-fork Phase 2 commitment.

## 16. Historical fork exit criteria — satisfied and superseded

The source records the criteria used to decide whether the Memos fork should remain the long-term Notes foundation: repeated upstream conflicts, invasive feature changes, disproportionate maintenance burden, excessive feature removal/patching, insufficient portability/recovery, or a materially simpler purpose-built native architecture.

The document states that these criteria were satisfied for the intended Evernote-class Notes scope, leading to the native Notes decision.

That decision preserves the separate Memos product and requires the Notes transition to preserve user notes, attachments, labels/tags, colors/state where applicable, timestamps, exportability, migration traceability, and recoverability.

## 17. Immediate next action — native transition

The source says the Memos RC3 environment and repository must remain protected until migration, recovery, and cutover requirements are proven.

It then records extensive **Draft PR #1 candidate evidence**, including native dependency controls, Alembic schema evolution, migration provenance, privileged-administration audit design, private authentication/owner isolation, Account & Security UI, portable full-library export/import, attachment integrity auditing, controlled Memos migration tooling, destructive disposable round-trip validation, attachment quota work, API-response hardening, reduced-effects/high-contrast safeguards, lazy rich-editor loading, frontend performance budgeting, and production-shaped CI/preflight evidence.

The source also describes strict portability boundaries: export bundles include accepted native content, organization, revisions, attachment metadata/bytes, and migration provenance while excluding credentials, sessions, rate-limit state, derived search indexes, deployment secrets, and deployment-specific storage paths. Empty-target re-import verifies archive integrity/relationships, rejects unsafe collisions/populated targets, regenerates owner-scoped storage keys, re-hashes staged bytes, and rechecks source fingerprints.

The Memos migration path is described as staged and fail-closed: read-only source inspection, provider-neutral normalization/manifest generation, attachment-byte verification, explicit empty-target import, post-import verification, and provenance-preserving export/re-import/re-export.

Exact-head CI and synthetic/runtime-preflight results cited in this source are candidate evidence for Draft PR #1 only. The source itself keeps production storage sizing, malware/scanning/quarantine, protected-source rehearsal, real production backup/recovery objectives, publication headers, monitoring, large-library/concurrency behavior, real-device/browser acceptance, hostname cutover, protected-source mutation, PR merge, and Stable release gated.

## Interpretation

Sections 9–17 document the transition from a Memos-derived implementation model to the protected, native Notes migration program. Candidate implementation details are preserved as history but do not become accepted `main` capabilities unless repository-native accepted evidence says so.
