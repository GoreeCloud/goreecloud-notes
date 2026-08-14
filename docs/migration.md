# GoreeCloud Notes Migration

## Source System

The current Memos-based GoreeCloud Notes environment is a transitional source system. Native development does not change its role as the authoritative source for any data that has not yet been migrated and validated.

## Non-Destructive Rule

The native migration path must be read-only against the source by default. Migration tooling must not delete, archive, rewrite, normalize in place, or otherwise mutate Memos source records merely to make import easier.

The first native migration tool is therefore an **inventory and validation tool, not an importer**. It accepts an already-created GoreeCloud Notes full-library JSON export and performs no database connection, source API call, native persistence, or source mutation:

```bash
cd backend
python -m app.migration inspect-memos-export /path/to/goreecloud-notes-YYYY-MM-DD.json
```

Use `--json` for a machine-readable report. The report records the source export's SHA-256, byte size, export format/schema, note/state counts, unique tag count, attachment-metadata counts, relation counts, validation errors/warnings, and whether separate attachment-binary recovery is still required. The inspector returns a non-zero status when the metadata contract is invalid.

## Transitional GoreeCloud/Memos Export Contract

The currently supported source contract is the GoreeCloud fork's `goreecloud-notes` JSON export with `schemaVersion: 1`. The inspector verifies the provenance envelope (`GoreeCloud Notes` / `Memos`), explicit timezone-bearing export and note timestamps, unique note names and UIDs, valid normal/archived/trash state, Trash restore targets, tags, attachment metadata, and relation structure.

Schema v1 deliberately contains **attachment metadata but not attachment binary content**. Local attachment metadata is therefore reported as a separate binary-recovery requirement rather than being mistaken for a complete migration source. External-link attachments are counted separately. A metadata-valid report is not evidence that attachment bytes have been extracted or verified.

The inspector also warns when a relation points to a memo that is not among the exported top-level notes. This can be legitimate because comments are excluded from the full-library export, but the relationship must still be reconciled rather than silently discarded.

The test fixture under `backend/tests/fixtures/memos_export_v1.json` is synthetic. CI uses it only to prove that the read-only inspector and schema contract continue to work; it is not copied from production Notes data.

## Provider-Neutral Migration Manifest

After an export passes metadata validation, the native tools can emit a deterministic GoreeCloud-owned migration manifest without writing to either source or target:

```bash
cd backend
python -m app.migration build-memos-manifest /path/to/goreecloud-notes-YYYY-MM-DD.json > migration-manifest.json
```

The manifest uses `format: goreecloud-notes-migration` and `schemaVersion: 1`. It carries the validated source export SHA-256, byte size, source format/schema, and export timestamp forward so later importer evidence can be tied to one exact source artifact. It does not include a local source pathname, current wall-clock generation timestamp, target UUID, database identifier, or other environment-specific value that would make the same source artifact produce a different logical manifest.

Each normalized note record preserves the original Memos name, UID, source order, source state and restore target; title and Markdown; a SHA-256 of the exact Markdown bytes; normalized active/archived/trashed lifecycle state; pin state; visibility, color, tags, timestamps, and location; attachment metadata; and relations. Each record also carries a deterministic SHA-256 over its normalized representation for later source/target equivalence work.

Local attachment metadata is represented with `binary.status: required` and **no invented binary checksum or verified byte size**. External-link attachments use `binary.status: external`. A later protected extraction step must supply independently verified local attachment bytes and checksums before any importer may claim attachment completeness.

Relations retain their source type and target source memo identity. The manifest records whether the target is present among exported top-level notes, but does not silently delete unresolved relationships or invent target-native identifiers.

Manifest generation refuses metadata-invalid exports. It also rechecks the source export byte length and SHA-256 after validation and fails if the source file changed during the operation. The command writes only JSON to standard output; any destination file is chosen by the operator or shell redirection.

This manifest is a provider-neutral **migration boundary**, not a native database dump and not an authorization to import. The later persistence importer should accept this versioned boundary rather than receiving privileged direct access to Memos-specific objects.

## Attachment-Binary Evidence

The provider-neutral manifest intentionally leaves local binary hashes unresolved. Once attachment bytes have been obtained from an **approved protected source copy or separately approved authenticated extraction process**, a second read-only verifier can produce evidence without importing the files:

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

The resulting `goreecloud-notes-attachment-evidence` schemaVersion 1 document records the exact migration-manifest file SHA-256/size, the source-export SHA-256, each verified local attachment's source identity, relative evidence path, declared and verified sizes, and SHA-256. It explicitly records sourceMutationPerformed=false and targetMutationPerformed=false.

A missing mapping or missing file is represented as incomplete evidence and the CLI returns status 4. This makes partial recovery reviewable without being mistaken for complete attachment readiness. Invalid/tampered manifests, unsafe paths, duplicate mappings, size mismatches, or other validation failures return status 2.

This verifier does **not** know or guess how a production Memos attachment ID maps to a live filesystem path. Production extraction remains a separate operation that must be designed from the actual protected source deployment/storage implementation. CI creates only synthetic attachment bytes and a synthetic mapping.

## Data to Preserve

Before cutover, inventory and preserve at least:

- users and ownership relationships;
- note content and titles;
- creation and modification timestamps;
- labels/tags and available color metadata;
- per-note color metadata;
- pinned state;
- Archive state;
- Trash/restore state implemented by the GoreeCloud fork;
- attachments and attachment relationships;
- available export identifiers/metadata needed for traceability.

## Migration Stages

1. Protect and inventory the source database and attachment storage.
2. Create an isolated copy for importer development.
3. Validate and fingerprint a GoreeCloud/Memos schema-v1 JSON export with the native read-only inspector.
4. Generate and preserve the deterministic provider-neutral migration manifest tied to that exact source fingerprint.
5. Recover local attachment binary content from an approved protected source copy or authenticated extraction path, create an explicit source-ID-to-relative-path mapping, and use the read-only verifier to produce SHA-256/size evidence.
6. Require complete local attachment evidence or document explicit approved exceptions before target persistence claims attachment completeness.
7. Reconcile unresolved relations and any documented migration exceptions without rewriting the source.
8. Validate required fields, ownership mapping, identifiers, timestamps, lifecycle state, and attachment references before persistence.
9. Import the provider-neutral manifest plus verified attachment evidence into a clean disposable native target only after the importer has its own authorization and rollback tests.
10. Compare source/manifest/evidence/target counts and selected content hashes/metadata.
11. Validate native search and export behavior.
12. Validate imported attachment retrieval against the evidence SHA-256/size records.
13. Perform user-facing acceptance testing.
14. Create current backups of both source and target before any production cutover.
15. Move `notes.goreecloud.com` only through a controlled, reversible publication change.
16. Retain the source environment until rollback is no longer required and retirement is explicitly approved.

## Evernote Import

Evernote ENEX import is a separate Milestone 3 capability. It should normalize into the same provider-neutral import boundary rather than creating a second privileged persistence path.

## Validation Evidence

A migration is not considered successful because an inspector, manifest generator, evidence verifier, or future importer exits without an error. Evidence must include source/manifest/evidence/target record counts, ownership checks, selected note-content comparison, lifecycle/metadata comparison, attachment validation, searchability, exportability, and documented exceptions.

A green export-inspection report, deterministic manifest, and synthetic attachment-evidence gate are still only migration-readiness evidence. They do not prove production attachment extraction, target persistence equivalence, production backup readiness, authorize cutover, or permit retirement of the transitional Memos environment.
