# Native Portable Re-Import

## Purpose

GoreeCloud Notes native portability is not complete merely because user knowledge can leave the application in a verified archive. The application must also provide a controlled way to reconstruct that knowledge from its own portable format without depending on the original PostgreSQL database, original attachment filesystem, original account UUID, original container, or original deployment host.

Milestone 0 therefore includes an administrator-operated **native portable re-import** path for the verified `goreecloud-notes-native-export` schema-v1 ZIP.

This feature is intentionally a reconstruction/restore boundary, not a general merge or synchronization feature.

## Administrative Command

The target account must already exist and must be empty:

```bash
python -m app.cli import-library \
  --username <existing-empty-target-account> \
  --input /path/to/goreecloud-notes-library.zip \
  --confirm-empty-target
```

Machine-readable result output is available with:

```bash
python -m app.cli import-library \
  --username <existing-empty-target-account> \
  --input /path/to/goreecloud-notes-library.zip \
  --confirm-empty-target \
  --json
```

The explicit `--confirm-empty-target` flag is mandatory. Omitting it fails closed. The importer also checks the target account itself and refuses the operation when that account already owns any native Notes data.

## What the Importer Restores

For the selected empty target account, the importer reconstructs the portable user-knowledge collections present in the verified native bundle:

- notebooks and notebook hierarchy;
- notes and structured GoreeCloud documents;
- note lifecycle state, pinning, and six-digit hexadecimal colors;
- content versions;
- tags, normalized tag identity, tag colors, and note/tag relationships;
- immutable note revisions;
- attachment metadata;
- the actual attachment bytes;
- user-owned created/updated timestamps represented by the portable format; and
- migration import checkpoints plus exact normalized migration source records when the exported account contains transitional migration provenance.

The generated PostgreSQL search vector is not imported. It is derived again by PostgreSQL from the restored native note data, and the live round-trip gate proves imported content remains searchable.

## Credentials and Target Identity Are Deliberately Separate

A portable library is user knowledge, not an account-credential backup.

The importer does **not** restore or overwrite:

- password hashes;
- browser sessions;
- CSRF material;
- login-abuse/rate-limit state;
- the target account credential;
- database credentials;
- deployment secrets; or
- internal attachment storage paths from another installation.

The administrator creates the empty target account separately. That target account and its independently created credential remain authoritative after import.

The bundle's source account ID and username remain evidence in the import result. They do not become authentication authority for the target account.

## Native Object Identity

The initial native re-import preserves portable native object UUIDs for:

- notebooks;
- notes;
- tags;
- attachments;
- revisions;
- migration import checkpoints; and
- migration provenance records.

Preserving these UUIDs avoids rewriting durable document references such as attachment-ID inline-image nodes and keeps a native export/re-import/re-export cycle structurally equivalent.

The importer therefore **refuses global UUID collisions** instead of silently remapping identifiers. This is another reason the current feature is an empty-target restore/import path rather than a merge feature.

## Read-Only Verification Before Mutation

Before target mutation, `load_native_import_plan` performs the existing independent ZIP verification and additional native-schema validation.

The import refuses unsafe or inconsistent input including:

- a symbolic-link source ZIP rather than a regular file;
- unsupported export format or schema version;
- an invalid source/application boundary;
- collection counts that disagree with the library summary or bundle verifier;
- invalid, duplicate, or unresolved UUID relationships;
- notebook parent references outside the bundle;
- notebook hierarchy cycles;
- note references to notebooks outside the bundle;
- unsupported note lifecycle state;
- unsupported native document schema;
- documents or revision documents that fail the current GoreeCloud document contract;
- duplicate or non-canonical tag identities;
- invalid note/tag relationships;
- unsafe attachment filenames or archive paths;
- attachment archive paths that do not match `attachments/<attachment UUID>/<filename>`;
- invalid attachment size or SHA-256 metadata;
- invalid revision ordering/content-version relationships;
- inline attachment nodes that point outside their note's attachments;
- inline attachment nodes using a media type the native renderer does not permit inline;
- invalid migration provenance hashes or relationships; and
- migration import/provenance counts that disagree with the preserved source records.

The input bundle SHA-256 and size are checked again after attachment staging. A bundle that changes between initial verification and the mutation boundary is refused.

## Attachment Reconstruction

Portable attachment paths are not reused as native filesystem paths.

For the selected target account, the importer generates fresh private storage keys using the target owner ID, restored note ID, and restored attachment ID. Attachment bytes are streamed out of the verified ZIP into temporary files under the configured private attachment root.

While staging each attachment, the importer recomputes SHA-256 and byte size. Both must match the portable metadata. Only completely staged and revalidated bytes are eligible for the final target transaction.

The final attachment path is checked to remain beneath the configured attachment root. Existing generated destinations cause refusal instead of replacement.

## Commit Boundary and Merge Refusal

Expensive ZIP verification and attachment staging happen before database write locks are acquired.

At the short final write boundary, the importer locks the native application-data tables in PostgreSQL with `SHARE ROW EXCLUSIVE` mode, then rechecks:

1. the selected target account is still empty; and
2. no portable native UUID collides with an existing database object.

Only after those checks pass does it insert rows in deterministic dependency order:

1. parent-before-child notebooks;
2. tags;
3. notes;
4. migration import checkpoints;
5. note/tag relationships;
6. revisions;
7. attachment metadata; and
8. migration provenance records.

Staged attachment files are then atomically moved into their generated native paths and the database transaction commits.

A caught failure rolls the database transaction back, removes remaining temporary files, and removes any final attachment files already moved during the failed attempt.

A process or host power loss at the narrow final file-move/database-commit boundary can leave unreferenced attachment bytes. The design does not commit metadata that points at bytes that were never successfully staged. Production recovery policy and garbage-collection policy remain separate release gates.

## Migration Provenance Through Re-Import

Native re-import also preserves the exact migration provenance embedded by the native exporter.

The disposable Memos validation chain proves this across the complete path:

```text
synthetic Memos export
  → deterministic migration manifest
  → attachment evidence
  → native Memos import
  → native portable export
  → destructive deletion of the disposable native target
  → separately recreated empty target account
  → native portable re-import
  → Memos post-import verifier
  → second native portable export
```

After that round trip, the existing Memos verifier still validates:

- database provenance ownership and hashes;
- native note projection;
- tag assignments;
- attachment byte integrity;
- exact normalized source records; and
- the deliberate fact that complete native semantic equivalence is **not** claimed by the current literal-Markdown migration profile.

The second native export is compared with the first for the portable user-knowledge collections. Exact source Markdown, relations, named source color, location metadata, Trash restore target, migration fingerprints, migration record hashes, note/tag relationships, and attachment bytes remain unchanged.

## Disposable Native Round-Trip Validation

A separate pure-native gate tests a richer native library without transitional migration data. It creates:

- nested notebooks;
- a colored tag;
- note/tag assignment;
- rich structured note content;
- a safe inline raster image;
- pinning and note color;
- an immutable pre-edit revision;
- an archived note;
- a separately trashed note; and
- searchable note text.

The gate then:

1. exports and independently verifies the source ZIP;
2. proves import without `--confirm-empty-target` is refused;
3. deletes the disposable source account rows and source attachment directory while preserving only the ZIP;
4. creates a new empty account with the same username but a different account UUID and separately created credential;
5. imports the ZIP;
6. authenticates through the separately created target credential;
7. verifies restored organization, note IDs/content/state/pinning/color, tag assignment, revision, attachment metadata, exact attachment bytes, and searchability;
8. proves another user receives opaque `404` responses for the restored note and attachment;
9. proves a second import into the now-populated target is refused; and
10. re-exports the target and compares every portable user-knowledge collection and attachment bytes with the source export.

This is destructive **only inside the disposable CI environment**. It does not touch production data or the protected transitional Memos service.

## Current Boundaries

Native portable re-import does not currently provide:

- browser ZIP upload/import;
- import into a populated target library;
- conflict resolution or UUID remapping;
- selective note restore from a full-library archive;
- synchronization between two native installations;
- scheduled restore automation;
- encrypted-archive password handling;
- background-job/progress UI for very large imports;
- approved production concurrency or library-size limits;
- ENEX import; or
- protected-source/production migration approval.

Those capabilities must be evaluated separately. A general merge feature must not be inferred from the existence of this controlled empty-target reconstruction path.

## Relationship to Backup and Recovery

Native portable re-import complements rather than replaces the PostgreSQL-plus-attachment recovery process.

Operational backup/restore preserves an installation as a working service. Native portable export/re-import preserves application-level user knowledge across database, filesystem, deployment, and future implementation boundaries.

A stable production release still requires production backup repository, retention, off-host/off-site protection, selected RPO/RTO, and production-representative restoration evidence in addition to this portable reconstruction capability.
