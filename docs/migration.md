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
5. Recover local attachment binary content from an approved protected source copy or authenticated extraction path and produce verifiable byte/checksum evidence; do not assume the JSON export contains those bytes.
6. Reconcile unresolved relations and any documented migration exceptions without rewriting the source.
7. Validate required fields, ownership mapping, identifiers, timestamps, lifecycle state, and attachment references before persistence.
8. Import the provider-neutral manifest into a clean disposable native target only after the importer has its own authorization and rollback tests.
9. Compare source/manifest/target counts and selected content hashes/metadata.
10. Validate native search and export behavior.
11. Validate attachment retrieval and checksums.
12. Perform user-facing acceptance testing.
13. Create current backups of both source and target before any production cutover.
14. Move `notes.goreecloud.com` only through a controlled, reversible publication change.
15. Retain the source environment until rollback is no longer required and retirement is explicitly approved.

## Evernote Import

Evernote ENEX import is a separate Milestone 3 capability. It should normalize into the same provider-neutral import boundary rather than creating a second privileged persistence path.

## Validation Evidence

A migration is not considered successful because an inspector, manifest generator, or future importer exits without an error. Evidence must include source/manifest/target record counts, ownership checks, selected note-content comparison, lifecycle/metadata comparison, attachment validation, searchability, exportability, and documented exceptions.

A green export-inspection report plus deterministic manifest is still only migration-readiness evidence. It does not prove binary attachment availability, target persistence equivalence, production backup readiness, authorize cutover, or permit retirement of the transitional Memos environment.
