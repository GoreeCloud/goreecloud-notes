# GoreeCloud Notes Migration

## Source System

The current Memos-based GoreeCloud Notes environment is a transitional source system. Native development does not change its role as the authoritative source for any data that has not yet been migrated and validated.

## Non-Destructive Rule

The native migration path must be read-only against the source by default. Migration tooling must not delete, archive, rewrite, normalize in place, or otherwise mutate Memos source records merely to make import easier.

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
3. Extract source records into a versioned provider-neutral migration representation.
4. Validate required fields, ownership, identifiers, timestamps, note state, and attachment references before persistence.
5. Import into a clean native target.
6. Compare source/target counts and selected content checksums/metadata.
7. Validate native search and export behavior.
8. Validate attachment retrieval and checksums.
9. Perform user-facing acceptance testing.
10. Create current backups of both source and target before any production cutover.
11. Move `notes.goreecloud.com` only through a controlled, reversible publication change.
12. Retain the source environment until rollback is no longer required and retirement is explicitly approved.

## Evernote Import

Evernote ENEX import is a separate Milestone 3 capability. It should normalize into the same provider-neutral import boundary rather than creating a second privileged persistence path.

## Validation Evidence

A migration is not considered successful because the importer exits without an error. Evidence must include source/target record counts, ownership checks, selected note-content comparison, state/metadata comparison, attachment validation, searchability, exportability, and documented exceptions.
