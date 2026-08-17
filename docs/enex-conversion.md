# Evernote ENML to GoreeCloud Blocks Conversion

## Purpose

This document defines Stage 4 of the GoreeCloud Notes Evernote migration path: deterministic conversion of exact-preservation ENML into reviewable `goreecloud.blocks` candidate documents **without writing native Notes application data**.

The conversion stage consumes the exact ENEX source, the Stage 3 `goreecloud-notes-enex-normalization` artifact, and—when resources exist—the same Stage 2 resource-evidence JSON used to create that normalization. It rebuilds normalization from the selected source/evidence and refuses conversion unless the supplied normalization matches exactly.

This is a migration review artifact, not an importer. It does not create users, notes, revisions, tags, attachments, database rows, files in the native attachment store, or production state.

## Evidence chain

The staged evidence chain is:

1. ENEX inspection proves the selected source is metadata-valid and records its exact fingerprint.
2. Resource extraction creates independently verified binary evidence without writing native data.
3. Normalization preserves exact original UTF-8 ENML and provider metadata without interpreting rich text.
4. Conversion produces deterministic native-document candidates while retaining explicit review/blocking evidence for semantics that `goreecloud.blocks` v1 cannot represent.

Conversion never replaces the exact ENML evidence. Stage 3 remains the evidence of original note content.

## Command

From `backend/`:

```bash
python -m app.migration.enex_conversion \
  /path/to/export.enex \
  --normalization /path/to/enex-normalization.json \
  --resource-evidence /path/to/enex-resource-evidence.json \
  > /path/to/enex-conversion.json
```

For a resource-free ENEX export, `--resource-evidence` is omitted.

Exit status `0` means every note produced a candidate document. Exit status `4` means a deterministic artifact was emitted but one or more notes were blocked by unsupported semantics. Unsafe, mismatched, tampered, malformed, or invalid inputs exit with status `2`.

## Input validation

Before converting any note, the converter:

- requires `goreecloud-notes-enex-normalization` schema version 1;
- verifies the normalization safety flags still prove exact ENML preservation and no prior native persistence;
- validates every per-note normalization record fingerprint;
- re-hashes every preserved ENML payload and checks its recorded byte size;
- validates every normalized resource reference and generated relative path;
- rebuilds Stage 3 normalization from the exact ENEX source and supplied resource evidence; and
- requires exact logical equality between the supplied and freshly rebuilt normalization artifact.

This prevents conversion from edited normalization JSON or evidence associated with another ENEX source.

## Reviewed mapping to `goreecloud.blocks` v1

The converter maps only semantics the current native document contract can represent safely.

### Block structure

- `div`, `p` → paragraph structure
- `h1`, `h2`, `h3` → native headings
- `h4`, `h5`, `h6` → native heading level 3 plus a review notice
- `ul`, `ol`, `li` → native list structure
- `blockquote` → native blockquote
- `pre` → native code block
- `hr` → native horizontal rule
- `br` → native hard break

### Inline marks

- `b`, `strong` → bold
- `i`, `em` → italic
- `s`, `strike`, `del` → strike
- `code` → code

Every candidate document is passed through the same backend `canonicalize_document()` contract used by native Notes. Conversion therefore cannot claim compatibility with a document shape the application itself would reject.

## Resource and attachment planning

Evernote `en-media` elements are resolved by their recorded resource hash against the normalized, verified resource inventory. MIME metadata must agree when `en-media` supplies a type.

The converter generates a deterministic future native attachment UUID from the exact source ENEX SHA-256, note index, resource index, and resource SHA-256. The UUID is planning evidence only; no attachment row or file is created at this stage.

Safe raster image resources supported by the existing native inline-image contract may become `attachmentImage` candidate blocks. Non-image resources remain planned attachments but their ENML placement becomes an explicit textual placeholder plus a review notice. Resources not referenced by ENML remain present in the planned attachment inventory and are marked for placement review rather than silently discarded.

## Review-required semantics

Some ENML semantics are intentionally preserved as explicit review evidence rather than silently discarded:

- generic anchor targets, because `goreecloud.blocks` v1 does not provide an arbitrary external-link mark;
- inline/layout styling attributes not represented by the native schema;
- source inline semantics such as underline/subscript/superscript that do not have a current native mark;
- Evernote checkbox (`en-todo`) semantics, represented temporarily as textual checkbox markers;
- encrypted Evernote (`en-crypt`) content, represented by an explicit encrypted-content placeholder while exact source ENML remains preserved;
- non-image `en-media` placement, represented by an attachment placeholder while binary evidence remains separately bound; and
- verified resources that are not referenced by ENML, retained as planned attachments pending placement review.

A note with any such notice is marked `converted-review-required`. It still has a structurally valid candidate document, but the artifact does not claim semantic equivalence until the notice is reviewed.

## Blocking semantics

The converter fails closed at the individual-note level when a construct cannot be represented safely. The current contract blocks ENML tables rather than flattening their cell relationships into ordinary text. Other unsupported block/inline structures, malformed ENML, missing/mismatched media evidence, and invalid media placement can also block a note.

A blocked note has `document: null`, a deterministic blocking issue record, and remains backed by its exact Stage 3 ENML evidence. Other notes in the same ENEX export may still produce review candidates so migration work can identify exactly which source notes need additional handling.

## Deterministic artifact

The `goreecloud-notes-enex-conversion` schema version 1 artifact records:

- the exact ENEX source fingerprint;
- the exact normalization JSON fingerprint and canonical normalization fingerprint;
- candidate `goreecloud.blocks` documents;
- normalized title, timestamps, and tags needed for later isolated import planning;
- planned attachment IDs and verified resource binary references;
- ENML resource reference counts;
- generic link targets preserved for review;
- review notices and blocking issues;
- per-note deterministic conversion record fingerprints; and
- explicit `nativeNotesCreated: false`, `nativeAttachmentsCreated: false`, `sourceMutationPerformed: false`, and `targetDatabaseMutationPerformed: false` evidence.

The artifact contains no generated timestamp or absolute source/evidence path. Repeating conversion with the same accepted source, evidence, and normalization produces the same logical artifact.

## Safety boundary

Stage 4 does **not** authorize or perform native account import, database writes, native attachment-store writes, production migration, Memos modification or retirement, DNS/Caddy/NetBird changes, permanent deletion, PR merge, or Stable release.

The next ENEX gates remain isolated empty-target native import, post-import equivalence and resource-integrity validation, protected-copy production-representative rehearsal, and final migration approval.
