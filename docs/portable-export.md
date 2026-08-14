# Native Portable Export

## Purpose

GoreeCloud Notes must preserve user knowledge independently from the database engine, attachment filesystem layout, deployment host, container, or future application implementation.

Milestone 0 therefore includes an administrator-operated full-library export that produces one verified ZIP bundle for a selected GoreeCloud Notes account. If that account contains data imported from a transitional source, the bundle also preserves the exact owner-scoped migration provenance needed to understand what the source contained and which semantics remain intentionally deferred in the native projection.

This is a portability and recovery feature. It is not a database backup replacement, and it does not authorize production deployment by itself.

## Command

Run the export from the API application environment so it can read the configured PostgreSQL database and private attachment root:

```bash
python -m app.cli export-library \
  --username <username> \
  --output /path/to/goreecloud-notes-library.zip
```

The command refuses to replace an existing output file unless overwrite is explicitly approved:

```bash
python -m app.cli export-library \
  --username <username> \
  --output /path/to/goreecloud-notes-library.zip \
  --overwrite
```

Verify a bundle without connecting to PostgreSQL:

```bash
python -m app.cli verify-library-export \
  --input /path/to/goreecloud-notes-library.zip
```

Verification checks the ZIP structure, library JSON SHA-256 and size, every attachment SHA-256 and size, declared member paths, duplicate members, undeclared members, and agreement between the bundle manifest and library attachment metadata.

## Bundle Format

The initial native export uses:

- Library format: `goreecloud-notes-native-export`
- Library schema version: `1`
- Bundle format: `goreecloud-notes-native-export-bundle`
- Bundle schema version: `1`

The ZIP contains:

```text
bundle.json
library.json
attachments/
└── <attachment UUID>/
    └── <original sanitized filename>
```

`library.json` contains the selected account's portable application data:

- account identity required for migration traceability;
- notebooks and hierarchy;
- notes, lifecycle state, pinning, color, structured document, document schema, and content version;
- tags and normalized tag identity;
- note/tag relationships;
- attachment metadata and portable archive paths;
- immutable note revisions and change summaries;
- created/updated timestamps where the native model stores them;
- owner-scoped migration import checkpoints and exact normalized source note records when the account contains migrated data; and
- collection counts, including migration provenance counts when applicable.

`bundle.json` provides integrity evidence for `library.json` and every attachment member.

## Migration Provenance Preservation

A successful migration must not become less explainable after the user later exports the native library. For that reason, the native exporter includes additive `migrationImports` and `migrationNoteRecords` collections when an account contains imported data.

Before migration provenance is added to a portable bundle, the exporter verifies that:

1. every migration import and migration note record belongs to the selected account;
2. every migration note record points to a note included in the same native export;
3. every migration note record points to an exported migration import checkpoint;
4. the embedded source `recordSha256`, persisted provenance hash, and freshly recomputed canonical source-record SHA-256 all agree; and
5. each import checkpoint's source/imported note counts agree with its preserved provenance records.

The preserved source record carries the normalized provider-neutral migration record, including source identity, exact source Markdown and its digest, lifecycle and Trash restore target, named source color, tags, timestamps, location metadata, attachment metadata, and source relations. These records are kept because some transitional semantics are deliberately not guessed into the current native model.

The exporter rebuilds and re-verifies the ZIP rather than appending a second `library.json`, because duplicate ZIP member names are rejected by the verifier. Attachment bytes are streamed unchanged into the rebuilt bundle and native note/attachment counts must remain identical to the already verified base export.

This makes migration provenance part of portable user-owned knowledge rather than a database-only implementation detail.

## Deliberately Excluded Data

The portable library export does **not** include:

- password hashes or credential records;
- raw or hashed browser-session secrets;
- CSRF secrets;
- login-abuse/rate-limit state;
- derived PostgreSQL search vectors or search indexes;
- database connection credentials;
- deployment secrets;
- internal attachment `storage_key` filesystem paths; or
- production infrastructure configuration.

Those records are either security-sensitive, deployment-specific, or reconstructable derived state rather than portable user knowledge.

## Attachment Integrity

Attachment bytes are a required part of a complete native library export.

Before the ZIP is finalized, the exporter:

1. resolves every persisted attachment key beneath the configured private attachment root;
2. rejects paths that escape that root;
3. requires every attachment to exist as a regular file;
4. recomputes byte size and SHA-256;
5. requires both values to match PostgreSQL metadata;
6. writes the attachment under an attachment-UUID-scoped archive path;
7. writes SHA-256 and size evidence into the bundle manifest; and
8. verifies the completed temporary ZIP before atomically replacing the requested destination.

If required bytes are missing or disagree with metadata, the full-library export fails instead of silently creating an incomplete archive.

## Atomic Output and Replacement

The exporter writes to temporary files in the destination directory, verifies the native base export, rebuilds it with validated migration provenance where applicable, verifies the final temporary bundle, and only then atomically replaces the final output path.

Existing export files are protected by default. Replacement requires the explicit `--overwrite` flag.

## Relationship Validation

Before writing an export, the exporter validates owner scope and relationship integrity for:

- notebook parents;
- note-to-notebook references;
- note/tag relationships;
- note-to-attachment references;
- note-to-revision relationships; and
- migration-import/provenance-to-native-note relationships.

A cross-owner or unresolved relationship fails the export rather than being silently omitted.

## Current Boundary

This feature establishes native full-library portability, attachment-byte integrity, and preservation of migration provenance across subsequent native exports. It does not yet provide:

- a browser download control;
- automatic scheduled exports;
- encrypted export archives;
- a native re-import command;
- an ENEX exporter or importer;
- production Kopia repository policy;
- off-host/off-site retention; or
- production recovery approval.

The portable export complements PostgreSQL-plus-attachment backup and restore. The backup system protects operational recovery; the portable export protects application/data independence, source traceability, and future migration.