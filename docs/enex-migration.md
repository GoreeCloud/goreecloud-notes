# Evernote ENEX Migration

GoreeCloud Notes includes three source-contained Evernote ENEX migration checkpoints:

1. **read-only ENEX inspection**, which validates and inventories an operator-supplied `.enex` file without mutation;
2. **controlled ENEX resource extraction**, which writes embedded resource bytes only into a newly created local evidence directory, verifies every written object with SHA-256, and never writes native GoreeCloud Notes application data; and
3. **provider-neutral ENEX note normalization**, which preserves the original UTF-8 ENML CDATA payload exactly, binds resource references to validated extraction evidence, normalizes source metadata into a deterministic review artifact, and still performs no ENML conversion or native import.

These checkpoints deliberately stop before reviewed ENML-to-`goreecloud.blocks` conversion, native import, or production migration.

## Stage 1 — Read-only ENEX inspection

The inspector:

- reads one explicitly selected local ENEX file;
- refuses symbolic-link inputs;
- enforces a bounded input-size limit;
- rejects XML entity declarations before parsing;
- computes a SHA-256 fingerprint of the exact source file;
- validates the ENEX root and Evernote UTC timestamps;
- inventories notes, deleted notes, tags, embedded resources, decoded resource bytes, and MIME types;
- validates base64 resource payloads and Evernote resource hashes when present; and
- records that source and target mutation were both **not** performed.

It does **not** connect to Evernote, modify the ENEX source, extract resources, create or modify a GoreeCloud Notes account, import notes, claim ENML-to-native rich-text equivalence, or authorize production migration.

From the `backend/` directory:

```bash
python -m app.migration inspect-enex-export /path/to/export.enex
```

Machine-readable output:

```bash
python -m app.migration inspect-enex-export /path/to/export.enex --json
```

The default maximum ENEX input size is 256 MiB. A smaller or larger positive limit can be selected explicitly:

```bash
python -m app.migration inspect-enex-export /path/to/export.enex --max-bytes 134217728 --json
```

A metadata-invalid ENEX report exits with status `3`. An unreadable, unsafe, oversized, or malformed XML input exits with status `2`.

## Stage 2 — Controlled embedded-resource extraction

After inspection is metadata-valid, embedded resource bytes can be extracted into a **new destination path that does not already exist**:

```bash
python -m app.migration extract-enex-resources \
  /path/to/export.enex \
  /path/to/new-enex-resource-evidence
```

The command writes a deterministic JSON evidence document to standard output and also stores the same document as:

```text
/path/to/new-enex-resource-evidence/enex-resource-evidence.json
```

Resource objects are stored under generated paths such as:

```text
resources/
└── note-000000/
    └── resource-000000-<full-sha256>.bin
```

Provider-supplied filenames are preserved only as metadata in the evidence document. They are **not** used as filesystem paths. This prevents an ENEX filename from controlling output traversal or overwriting another file.

### Extraction safety contract

The extractor:

- reruns the metadata-valid ENEX inspection gate before extraction;
- requires the exact inspected source byte length and SHA-256 to remain unchanged;
- refuses a pre-existing destination, including an empty directory, so it never adopts or overwrites operator files;
- refuses a symbolic-link destination and refuses symbolic links in the destination-parent chain;
- creates the extraction root with private directory permissions;
- uses only GoreeCloud-generated relative resource paths;
- bounds ENEX input size, decoded per-resource size, total decoded output size, and resource count;
- prevalidates the complete extraction plan before creating the destination;
- writes each resource with exclusive-create semantics;
- verifies the written file's SHA-256 and size from disk;
- records duplicate resource content without collapsing or overwriting the one-to-one ENEX resource mapping;
- re-hashes the source again before finalizing evidence;
- writes the evidence file with exclusive-create semantics and verifies its persisted bytes;
- removes the newly created extraction root when a caught extraction failure occurs before successful completion;
- never writes to the GoreeCloud Notes database; and
- never modifies the ENEX source.

Default extraction limits are:

- ENEX input: 256 MiB;
- one decoded resource: 128 MiB;
- total decoded resources: 256 MiB;
- resource count: 10,000.

They can be lowered or raised explicitly with positive values:

```bash
python -m app.migration extract-enex-resources \
  /path/to/export.enex \
  /path/to/new-enex-resource-evidence \
  --max-bytes 268435456 \
  --max-resource-bytes 134217728 \
  --max-total-resource-bytes 268435456 \
  --max-resources 10000
```

Unsafe input, metadata-invalid input, changed source bytes, invalid limits, unsafe output paths, extraction-limit violations, or write/integrity failures exit with status `2`.

### Evidence schema

The deterministic `goreecloud-notes-enex-resource-evidence` schema version 1 document records:

- source provider/format;
- exact source ENEX SHA-256 and byte size;
- extraction completion state;
- decoded resource count and byte total;
- configured extraction limits;
- explicit `sourceMutationPerformed: false`;
- explicit `targetDatabaseMutationPerformed: false`;
- explicit `outputOverwritePerformed: false`;
- note/resource source indexes;
- normalized MIME type;
- original Evernote filename metadata when present;
- recorded Evernote MD5 metadata when present;
- GoreeCloud-generated relative output path;
- SHA-256 and exact byte size of each extracted resource; and
- `duplicateOf` when identical resource bytes were already observed earlier in the same ENEX source.

The evidence intentionally contains no destination-absolute path and no generation timestamp, so the same source bytes and extraction limits produce the same logical evidence regardless of where the operator stores the extraction directory.

## Stage 3 — Provider-neutral note normalization with exact ENML preservation

Normalization is intentionally a **zero-write review stage**. It does not use the native database, create native notes, or interpret ENML into the GoreeCloud rich-document model.

For an ENEX export that contains resources, first create Stage 2 evidence and pass the exact evidence JSON to the normalizer:

```bash
python -m app.migration.enex_normalization \
  /path/to/export.enex \
  --resource-evidence /path/to/new-enex-resource-evidence/enex-resource-evidence.json \
  > /path/to/enex-normalization.json
```

For an ENEX export with no embedded resources, `--resource-evidence` is not required:

```bash
python -m app.migration.enex_normalization \
  /path/to/resource-free-export.enex \
  > /path/to/enex-normalization.json
```

The command exits with status `0` after emitting a deterministic artifact. Unsafe input, metadata-invalid input, source/evidence mismatch, unsupported exact-preservation input, tampered evidence, or invalid limits exit with status `2`.

### Exact ENML boundary

The normalizer treats original ENML as evidence, not as already converted rich text.

To prevent silent parser normalization from changing the original content, this stage requires UTF-8 ENEX input with exactly one CDATA `<content>` payload per note. It captures the bytes **inside the original CDATA section directly from the ENEX source**, decodes those bytes as UTF-8 without replacement, stores the resulting ENML string, and records the original byte length and SHA-256.

This means line endings and all ENML characters inside the CDATA payload are preserved exactly. If a source represents note content in another XML form, the normalizer refuses it rather than pretending exact preservation occurred.

The artifact explicitly records:

- `exactEnmlPreserved: true`;
- `enmlConversionPerformed: false`;
- `nativeDocumentCreated: false`;
- `sourceMutationPerformed: false`; and
- `targetMutationPerformed: false`.

### Resource-evidence binding

When the ENEX source contains resources, normalization requires the Stage 2 evidence document and independently validates it against the exact source ENEX.

The validator checks:

- the resource-evidence format and schema version;
- exact source ENEX SHA-256 and byte size;
- metadata-valid inspection state;
- completed extraction state;
- non-mutation and non-overwrite evidence flags;
- expected resource count and total bytes;
- one-to-one note/resource indexes;
- normalized MIME type;
- original Evernote filename and MD5 metadata;
- generated resource path safety;
- decoded resource SHA-256 and byte size; and
- duplicate-content references.

The normalizer recalculates each resource SHA-256 from the ENEX embedded bytes rather than trusting the evidence JSON. A copied, edited, mismatched, or path-tampered evidence document is therefore refused.

The normalization artifact records the SHA-256 and byte size of the exact evidence JSON it accepted, allowing later conversion/import tooling to require the same evidence set.

### Normalization artifact

The deterministic `goreecloud-notes-enex-normalization` schema version 1 artifact records:

- exact ENEX source fingerprint and export metadata;
- source inspection warnings;
- note/deleted-note/tag/resource inventory;
- exact original ENML plus per-note ENML SHA-256 and byte size;
- source title;
- normalized UTC created/updated/deleted timestamps;
- every tag in source order, including its original value and trimmed comparison name;
- note-attributes metadata without interpreting it into native behavior;
- resource references bound to Stage 2 evidence;
- resource-attributes, recognition, and alternate-data metadata snapshots when present;
- deterministic per-note record SHA-256 values; and
- explicit proof that ENML conversion and native persistence did not occur.

The artifact contains no source absolute path and no generated timestamp, so repeated normalization of the same accepted source and resource evidence produces the same logical output.

## Current ENEX migration state

ENEX **inspection, resource extraction evidence, and provider-neutral note normalization with exact original ENML preservation** are source-implemented checkpoints. They are not ENEX native-import support.

The remaining ENEX-specific stages stay separately gated:

1. reviewed ENML-to-`goreecloud.blocks` conversion semantics;
2. isolated empty-target native import;
3. post-import equivalence and resource-integrity validation;
4. production-representative migration rehearsal against a protected source copy; and
5. final migration approval.

Until those stages are implemented and validated together, GoreeCloud Notes must not claim production ENEX migration readiness.
