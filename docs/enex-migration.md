# Evernote ENEX Migration

GoreeCloud Notes now has four source-contained Evernote migration checkpoints. Each stage is independently bounded so evidence can be reviewed before any later stage is allowed to create native data.

1. **Read-only ENEX inspection** validates and inventories an operator-selected `.enex` source.
2. **Controlled resource extraction** writes only verified embedded-resource evidence into a new local evidence directory.
3. **Provider-neutral normalization** preserves exact original UTF-8 ENML and source metadata without converting rich text.
4. **Zero-write ENML conversion review** converts supported ENML into deterministic `goreecloud.blocks` candidates, while recording review-required and blocking semantics instead of silently dropping them.

These stages do **not** provide native ENEX import or production migration approval.

## Stage 1 — Read-only inspection

Run from `backend/`:

```bash
python -m app.migration inspect-enex-export /path/to/export.enex --json
```

The inspector refuses symbolic-link inputs, bounds input size, rejects XML entity declarations before parsing, fingerprints the exact source, validates ENEX metadata/timestamps, and inventories notes, deleted notes, tags, resources, decoded resource bytes, and MIME types. It never connects to Evernote and never mutates the source or target database.

A metadata-invalid report exits `3`; unsafe, unreadable, oversized, or malformed input exits `2`.

## Stage 2 — Controlled resource extraction

After Stage 1 is metadata-valid:

```bash
python -m app.migration extract-enex-resources \
  /path/to/export.enex \
  /path/to/new-enex-resource-evidence
```

The destination must not already exist. The extractor prevalidates the complete plan, creates a private evidence directory, uses only GoreeCloud-generated relative resource paths, bounds per-resource/total bytes and count, writes with exclusive-create semantics, verifies persisted SHA-256/size, records duplicate content without collapsing source relationships, rechecks the ENEX source fingerprint, and writes `enex-resource-evidence.json`.

Provider filenames are metadata only and never become output paths. The evidence contains no absolute extraction path or generated timestamp. No GoreeCloud Notes database data is written.

Default limits are 256 MiB ENEX input, 128 MiB per decoded resource, 256 MiB total decoded resources, and 10,000 resources.

## Stage 3 — Exact-preservation normalization

For a source with resources:

```bash
python -m app.migration.enex_normalization \
  /path/to/export.enex \
  --resource-evidence /path/to/new-enex-resource-evidence/enex-resource-evidence.json \
  > /path/to/enex-normalization.json
```

For resource-free ENEX, omit `--resource-evidence`.

Normalization requires UTF-8 ENEX with exactly one CDATA `<content>` payload per note. It captures the original bytes inside each CDATA section, decodes strictly as UTF-8, and records the ENML byte size and SHA-256. It refuses sources that cannot satisfy this exact-preservation contract rather than reconstructing ENML through the XML parser.

When resources exist, Stage 3 requires Stage 2 evidence and independently revalidates source fingerprint, extraction status, indexes, MIME/file/hash metadata, decoded SHA-256/size, duplicate references, and generated path safety. Resource hashes are recalculated from the embedded ENEX bytes.

The deterministic `goreecloud-notes-enex-normalization` schema-v1 artifact preserves title, timestamps, tags in source order, note/resource metadata, exact ENML, verified resource references, and deterministic per-note record fingerprints. It records `exactEnmlPreserved: true`, `enmlConversionPerformed: false`, `nativeDocumentCreated: false`, and no source/target mutation.

## Stage 4 — Zero-write ENML conversion review

Run against the exact Stage 3 artifact and, when applicable, the same Stage 2 evidence:

```bash
python -m app.migration.enex_conversion \
  /path/to/export.enex \
  --normalization /path/to/enex-normalization.json \
  --resource-evidence /path/to/enex-resource-evidence.json \
  > /path/to/enex-conversion.json
```

Stage 4 revalidates the supplied normalization, rebuilds it from the exact ENEX/evidence set, and requires exact logical equality before conversion. It verifies note record fingerprints, exact ENML fingerprints, resource evidence state, and generated relative paths.

Supported ENML is mapped only into the existing `goreecloud.blocks` v1 contract:

- paragraphs/divisions, headings, bullet/ordered lists, blockquotes, code blocks, horizontal rules, and hard breaks;
- bold, italic, strike, and code marks;
- verified safe raster `en-media` as deterministic future `attachmentImage` candidates.

Every candidate is passed through the native backend `canonicalize_document()` validator.

### Review-required semantics

Stage 4 explicitly records semantics that cannot yet claim native equivalence, including generic link targets, layout/style attributes, unsupported inline presentation semantics, Evernote checkboxes, encrypted `en-crypt` content, non-image media placement, and verified resources not referenced from ENML. Candidate notes with these conditions are marked `converted-review-required`.

### Blocking semantics

The converter fails closed per note when safe representation is unavailable. ENML tables are currently blocked rather than flattened because `goreecloud.blocks` v1 has no table model. Malformed ENML, unsupported structures, missing/mismatched media evidence, or invalid media placement can also block a note. A blocked note retains its exact Stage 3 ENML evidence and emits `document: null` plus a deterministic blocking issue.

The `goreecloud-notes-enex-conversion` schema-v1 artifact includes candidate documents, planned deterministic attachment UUIDs, verified binary references, link review evidence, review notices, blocking issues, and per-note record fingerprints. It explicitly records `nativeNotesCreated: false`, `nativeAttachmentsCreated: false`, `sourceMutationPerformed: false`, and `targetDatabaseMutationPerformed: false`.

Exit `0` means all notes produced candidates; exit `4` means an artifact was emitted with at least one blocked note; invalid/tampered/mismatched input exits `2`.

Detailed Stage 4 semantics are documented in `docs/enex-conversion.md`.

## Current migration boundary

Inspection, extraction evidence, exact-preservation normalization, and zero-write ENML conversion review are source-level migration tooling only. They do not authorize native account import or production migration.

Remaining ENEX-specific gates are:

1. isolated empty-target native import using reviewed conversion/evidence;
2. post-import equivalence and resource-integrity validation;
3. production-representative rehearsal against a protected source copy; and
4. final migration approval.

Until those stages are implemented and validated together, GoreeCloud Notes must not claim production ENEX migration readiness.
