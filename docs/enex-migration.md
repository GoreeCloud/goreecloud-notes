# Evernote ENEX Migration Inspection

GoreeCloud Notes includes a **read-only ENEX inspection checkpoint** for future Evernote migration work.

This checkpoint inventories and validates an operator-supplied `.enex` file before any resource extraction, normalization, native account import, or production migration is attempted.

## Safety boundary

The ENEX inspector:

- reads one explicitly selected local ENEX file;
- refuses symbolic-link inputs;
- enforces a bounded input-size limit;
- rejects XML entity declarations before parsing;
- computes a SHA-256 fingerprint of the exact source file;
- validates the ENEX root and Evernote UTC timestamps;
- inventories notes, deleted notes, tags, embedded resources, resource bytes, and MIME types;
- validates base64 resource payloads and Evernote resource hashes when present;
- records that source and target mutation were both **not** performed.

It does **not**:

- connect to Evernote;
- modify the ENEX source;
- extract attachment/resource files;
- build a native GoreeCloud migration manifest;
- create or modify a GoreeCloud Notes account;
- import notes;
- claim ENML-to-native rich-text equivalence;
- authorize production migration.

## Usage

From the `backend/` directory:

```bash
python -m app.migration inspect-enex-export /path/to/export.enex
```

Machine-readable output:

```bash
python -m app.migration inspect-enex-export /path/to/export.enex --json
```

The default maximum input size is 256 MiB. A smaller or larger positive limit can be selected explicitly:

```bash
python -m app.migration inspect-enex-export /path/to/export.enex --max-bytes 134217728 --json
```

A metadata-invalid ENEX report exits with status `3`. An unreadable, unsafe, oversized, or malformed XML input exits with status `2`.

## Current ENEX migration state

This checkpoint is intentionally earlier than the existing controlled Memos migration pipeline.

The next ENEX-specific implementation stages remain separate review gates:

1. controlled extraction of embedded ENEX resources with SHA-256 evidence;
2. provider-neutral normalization of note metadata and exact ENML source preservation;
3. reviewed ENML-to-`goreecloud.blocks` conversion semantics;
4. isolated empty-target import;
5. post-import equivalence and resource-integrity validation;
6. production-representative migration rehearsal against a protected source copy;
7. final migration approval.

Until those stages are implemented and validated, ENEX support should be described as **inspection readiness**, not import support.
