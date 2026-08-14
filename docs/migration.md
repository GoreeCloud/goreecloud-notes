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
4. Recover local attachment binary content from an approved protected source copy or authenticated extraction path and produce verifiable byte/checksum evidence; do not assume the JSON export contains those bytes.
5. Extract source records into a versioned provider-neutral migration representation.
6. Validate required fields, ownership, identifiers, timestamps, note state, and attachment references before persistence.
7. Import into a clean native target.
8. Compare source/target counts and selected content checksums/metadata.
9. Validate native search and export behavior.
10. Validate attachment retrieval and checksums.
11. Perform user-facing acceptance testing.
12. Create current backups of both source and target before any production cutover.
13. Move `notes.goreecloud.com` only through a controlled, reversible publication change.
14. Retain the source environment until rollback is no longer required and retirement is explicitly approved.

## Evernote Import

Evernote ENEX import is a separate Milestone 3 capability. It should normalize into the same provider-neutral import boundary rather than creating a second privileged persistence path.

## Validation Evidence

A migration is not considered successful because the importer exits without an error. Evidence must include source/target record counts, ownership checks, selected note-content comparison, state/metadata comparison, attachment validation, searchability, exportability, and documented exceptions.

A green export-inspection report is only the first migration-readiness checkpoint. It validates the JSON metadata envelope and produces a deterministic source fingerprint; it does not import records, prove binary attachment availability, prove target equivalence, authorize cutover, or permit retirement of the transitional Memos environment.
