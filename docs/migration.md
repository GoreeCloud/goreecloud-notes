# GoreeCloud Notes Migration

## Source System

The current Memos-based GoreeCloud Notes environment is a transitional source system. Native development does not change its role as the authoritative source for any data that has not yet been migrated and validated.

## Non-Destructive Rule

The native migration path is read-only against Memos. Migration tooling must not delete, archive, rewrite, normalize in place, or otherwise mutate Memos source records merely to make import easier.

The migration chain deliberately separates source inspection, provider-neutral normalization, attachment-byte evidence, native target persistence, and post-import verification. Only the explicit target importer writes data, and it writes only to a selected native account after confirmation and empty-target checks. No migration command connects directly to Memos.

## Stage 1 — Read-Only Transitional Export Inspection

The first tool accepts an already-created GoreeCloud Notes full-library JSON export and performs no database connection, source API call, native persistence, or source mutation:

```bash
cd backend
python -m app.migration inspect-memos-export /path/to/goreecloud-notes-YYYY-MM-DD.json
```

Use `--json` for a machine-readable report. The report records the source export's SHA-256, byte size, export format/schema, note/state counts, unique tag count, attachment-metadata counts, relation counts, validation errors/warnings, and whether separate attachment-binary recovery is still required. The inspector returns a non-zero status when the metadata contract is invalid.

## Transitional GoreeCloud/Memos Export Contract

The currently supported source contract is the GoreeCloud fork's `goreecloud-notes` JSON export with `schemaVersion: 1`. The inspector verifies the provenance envelope (`GoreeCloud Notes` / `Memos`), explicit timezone-bearing export and note timestamps, unique note names and UIDs, valid normal/archived/trash state, Trash restore targets, tags, attachment metadata, and relation structure.

Schema v1 deliberately contains **attachment metadata but not attachment binary content**. Local attachment metadata is therefore reported as a separate binary-recovery requirement rather than being mistaken for a complete migration source. External-link attachments are counted separately. A metadata-valid report is not evidence that attachment bytes have been extracted or verified.

The inspector also warns when a relation points to a memo that is not among the exported top-level notes. This can be legitimate because comments are excluded from the full-library export, but the relationship must still be reconciled rather than silently discarded.

The test fixture under `backend/tests/fixtures/memos_export_v1.json` is synthetic. CI uses it only to prove the migration pipeline; it is not copied from production Notes data.

## Stage 2 — Provider-Neutral Migration Manifest

After an export passes metadata validation, the native tools emit a deterministic GoreeCloud-owned migration manifest without writing to either source or target:

```bash
cd backend
python -m app.migration build-memos-manifest /path/to/goreecloud-notes-YYYY-MM-DD.json > migration-manifest.json
```

The manifest uses `format: goreecloud-notes-migration` and `schemaVersion: 1`. It carries the validated source export SHA-256, byte size, source format/schema, and export timestamp forward so later importer evidence can be tied to one exact source artifact. It does not include a local source pathname, current wall-clock generation timestamp, target UUID, database identifier, or other environment-specific value that would make the same source artifact produce a different logical manifest.

Each normalized note record preserves the original Memos name, UID, source order, source state and restore target; title and Markdown; a SHA-256 of the exact Markdown bytes; normalized active/archived/trashed lifecycle state; pin state; visibility, color, tags, timestamps, and location; attachment metadata; and relations. Each record also carries a deterministic SHA-256 over its normalized representation for later source/target equivalence work.

Local attachment metadata is represented with `binary.status: required` and **no invented binary checksum or verified byte size**. External-link attachments use `binary.status: external`. A protected extraction step must supply independently verified local attachment bytes and checksums before the target importer may claim attachment completeness.

Relations retain their source type and target source memo identity. The manifest records whether the target is present among exported top-level notes, but does not silently delete unresolved relationships or invent target-native identifiers.

Manifest generation refuses metadata-invalid exports. It also rechecks the source export byte length and SHA-256 after validation and fails if the source file changed during the operation.

## Stage 3 — Attachment-Binary Evidence

Once attachment bytes have been obtained from an **approved protected source copy or separately approved authenticated extraction process**, a read-only verifier can produce evidence without importing the files:

```bash
cd backend
python -m app.migration verify-attachment-binaries \
  migration-manifest.json \
  attachment-map.json \
  /path/to/protected/extracted-attachment-root \
  > attachment-evidence.json
```

The operator-supplied mapping is versioned and deliberately simple:

```json
{
  "format": "goreecloud-notes-attachment-map",
  "schemaVersion": 1,
  "attachments": [
    {
      "sourceName": "attachments/123",
      "relativePath": "123/photo.jpg"
    }
  ]
}
```

The verifier accepts only source attachment names whose manifest binary state is `required`. Relative paths must be clean POSIX-style paths. Absolute paths, `.`/`..`, duplicate source names, duplicate mapped paths, symbolic-link roots, symbolic-link path components, and non-regular files are rejected. The evidence output contains only relative paths, never the absolute protected extraction root.

Before trusting attachment metadata, the verifier validates the migration-manifest format/schema and mutation boundary and recomputes every normalized note `recordSha256`. It hashes each supplied file using SHA-256 and requires the actual byte count to equal the size declared by the schema-v1 source metadata. Size mismatch is a hard failure rather than an automatic correction.

The resulting `goreecloud-notes-attachment-evidence` schemaVersion 1 document records the exact migration-manifest file SHA-256/size, the source-export SHA-256, each verified local attachment's source identity, relative evidence path, declared and verified sizes, and SHA-256. It explicitly records `sourceMutationPerformed=false` and `targetMutationPerformed=false`.

A missing mapping or missing file is represented as incomplete evidence and the CLI returns status 4. Invalid/tampered manifests, unsafe paths, duplicate mappings, size mismatches, or other validation failures return status 2.

This verifier does **not** know or guess how a production Memos attachment ID maps to a live filesystem path. Production extraction remains a separate operation that must be designed from the actual protected source deployment/storage implementation. CI creates only synthetic attachment bytes and a synthetic mapping.

## Stage 4 — Explicit Empty-Target Native Persistence

The native importer consumes only the provider-neutral manifest, complete attachment evidence, and explicit evidence root. It never receives privileged direct access to Memos:

```bash
cd backend
python -m app.migration import-memos-manifest \
  migration-manifest.json \
  attachment-evidence.json \
  /path/to/protected/extracted-attachment-root \
  --username <existing-empty-native-account> \
  --confirm-empty-target
```

The command has an intentionally narrow mutation boundary:

- `--confirm-empty-target` is mandatory;
- the selected native account must already exist;
- the account must contain no notebooks, notes, tags, note/tag relationships, attachments, revisions, or prior migration provenance;
- the importer refuses a second import or an implicit merge into a non-empty account;
- source and evidence JSON are validated and attachment bytes are re-hashed before target mutation begins;
- the database write is one transaction;
- private attachment bytes are staged under generated temporary paths, re-hashed while copied, moved atomically to generated native storage keys before commit, and removed on caught rollback failures;
- source data is never mutated; and
- persistent migration provenance is written alongside the native projection.

Alembic revision `0006_migration_provenance` adds owner-scoped `migration_imports` and `migration_note_records`. The import checkpoint preserves provider and exact source-export/manifest/evidence fingerprints plus the conversion profile and source/imported counts. Each migration note record ties one native note to its source Memos name/UID/order, deterministic `recordSha256`, and the **entire normalized source record in JSONB**.

The exact source record remains authoritative migration evidence for source concepts not yet represented natively. This prevents a migration from silently losing information merely because the current application model has not yet approved an equivalent feature.

### Current Native Projection

The initial conversion profile is `literal-markdown-lines-v1`. It deliberately preserves every Markdown character visibly rather than pretending to provide rich-text semantic equivalence. Each source Markdown line becomes a native paragraph whose text is the literal source line, and empty source lines become empty paragraphs. The exact original Markdown and its SHA-256 remain preserved in migration provenance.

The importer currently maps without guessing:

- active/normal source lifecycle → native `normal`;
- archived source lifecycle → native `archived`;
- trashed source lifecycle → native `trashed`;
- source pin state → native pin state;
- private source visibility → approved private native account data;
- normalized source tags → owner-scoped native tags and assignments;
- source creation/update timestamps → native note timestamps;
- verified local attachments → generated private native attachment records and copied bytes; and
- six-digit hexadecimal source note colors → native note colors.

The importer deliberately **does not claim native semantic equivalence** for:

- Markdown rich-format semantics;
- Memos relations/internal-link semantics;
- location metadata;
- Trash restore-target semantics;
- non-hex named source colors such as `blue`; or
- external-link attachments.

These values remain in the exact preserved source record. External-link attachments currently cause target import to fail because no approved native persistence representation exists. A Memos named color such as `blue` remains in provenance while native `color` stays unset rather than guessing a hex value.

## Stage 5 — Read-Only Post-Import Verification

After commit, a separate verifier re-checks the target without changing it:

```bash
python -m app.migration verify-memos-import \
  --username <account> \
  --import-id <migration-import-uuid>
```

The verifier checks:

- import checkpoint and provenance ownership;
- exact source-record `recordSha256` integrity;
- source/imported note counts;
- native note title/document/schema/content-version/lifecycle/pin/color projection;
- tag normalization and note/tag assignments;
- attachment provenance links to the exact manifest/evidence fingerprints;
- current native attachment metadata; and
- byte-for-byte attachment SHA-256 and size under the private native attachment root.

The verification report explicitly states `nativeSemanticEquivalenceComplete=false` while listing the still-deferred semantics. Verification itself records `sourceMutationPerformed=false` and `targetVerificationMutationPerformed=false`.

## Stage 6 — Preserve Migration Provenance in Native Portable Export

Migration provenance is user-owned knowledge and must not become a database-only dead end. When an imported native account is later exported with `python -m app.cli export-library`, the verified native full-library ZIP includes owner-scoped `migrationImports` and `migrationNoteRecords` in `library.json`.

Before export, GoreeCloud Notes revalidates ownership, import/note relationships, import counts, and the canonical SHA-256 of every exact normalized source record. The native export preserves the import checkpoint fingerprints and exact source record—including deferred named colors, locations, restore targets, relations, and exact source Markdown—alongside the current native note representation and attachment bytes.

The portable exporter then rebuilds and independently verifies the ZIP so provenance survives future migrations without weakening attachment-byte integrity or exporting credentials/session state. See `docs/portable-export.md`.

## Data to Preserve

Before production cutover, inventory and preserve at least:

- users and ownership relationships;
- note content and titles;
- creation and modification timestamps;
- labels/tags and available color metadata;
- per-note color metadata;
- pinned state;
- Archive state;
- Trash/restore state implemented by the GoreeCloud fork;
- attachments and attachment relationships;
- source relations and location metadata where available;
- exact migration source identities/fingerprints; and
- available export identifiers/metadata needed for traceability.

## Migration Stages

1. Protect and inventory the source database and attachment storage.
2. Create an isolated/protected source copy for migration work.
3. Validate and fingerprint a GoreeCloud/Memos schema-v1 JSON export with the native read-only inspector.
4. Generate and preserve the deterministic provider-neutral migration manifest tied to that exact source fingerprint.
5. Recover local attachment binary content from an approved protected source copy or authenticated extraction path, create an explicit source-ID-to-relative-path mapping, and use the read-only verifier to produce SHA-256/size evidence.
6. Require complete local attachment evidence or document explicit approved exceptions before target persistence claims attachment completeness.
7. Reconcile unresolved relations and documented migration exceptions without rewriting the source.
8. Import the provider-neutral manifest plus verified attachment evidence into a clean disposable native target only with explicit confirmation and rollback protection.
9. Run the independent post-import verifier and compare source/manifest/evidence/provenance/native counts and hashes.
10. Validate imported data through the authenticated owner-scoped application API, including note lifecycle, tags, attachment retrieval, and cross-user opacity.
11. Export the imported native account and prove migration provenance plus native attachment bytes survive the portable-export boundary.
12. Validate native search and user-facing workflows.
13. Perform protected-copy migration rehearsals using production-representative source evidence without mutating the live source.
14. Create current backups of both source and target before any production cutover.
15. Move `notes.goreecloud.com` only through a controlled, reversible publication change.
16. Retain the source environment until rollback is no longer required and retirement is explicitly approved.

## Evernote Import

Evernote ENEX import is a separate Milestone 3 capability. It should normalize into the same provider-neutral import boundary rather than creating a second privileged persistence path.

## Validation Evidence

A migration is not considered successful because an inspector, manifest generator, evidence verifier, importer, or verifier exits without an error. Evidence must include source/manifest/evidence/target record counts, ownership checks, exact provenance hashes, selected note-content comparison, lifecycle/metadata comparison, attachment validation, cross-user authorization, searchability, portable exportability, and documented exceptions.

The current automated gate uses only synthetic Memos export data and synthetic attachment bytes in a disposable native target. It proves the software pipeline and safety boundaries; it does **not** prove production attachment extraction, protected-copy production migration equivalence, production backup readiness, authorize cutover, or permit retirement of the transitional Memos environment.