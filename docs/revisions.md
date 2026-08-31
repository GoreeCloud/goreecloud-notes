# GoreeCloud Notes Revision Recovery

## Purpose

GoreeCloud Notes keeps immutable historical content snapshots so an authorized note owner can recover earlier note content without rewriting history or silently discarding the current version.

This document defines the Milestone 0 recovery behavior and the conservative retention boundary that applies until production backup, retention, and permanent-deletion requirements are approved.

## Revision Scope

A revision stores the historical content-bearing fields that can be safely restored as one coherent editor state:

- title
- structured `goreecloud.blocks` document
- document schema version
- content version represented by the snapshot
- revision number and creation time
- optional server-generated change summary

A revision does **not** restore notebook placement, tags, lifecycle state, pinning, color, attachments, ownership, authentication state, or other metadata. Those fields have independent lifecycle and authorization rules and must not be changed as a side effect of content recovery.

## Immutable History

Revision rows are immutable application history. A restore operation never edits or deletes the selected historical revision.

When a historical revision differs from the current note content, GoreeCloud Notes:

1. verifies that the authenticated user owns the note and selected revision;
2. requires CSRF protection for the write;
3. requires the caller's exact current `content_version`;
4. returns HTTP `409` if the note changed after the caller read it;
5. creates a new immutable snapshot of the current content **without applying the ordinary time-coalescing rule**;
6. copies the selected historical title/document/document-schema fields into the current note;
7. increments the note's `content_version`; and
8. leaves the selected historical revision and all prior revisions intact.

The forced pre-restore snapshot is intentional. Revision coalescing is useful for ordinary rapid editor saves, but it must never remove the ability to undo a deliberate historical restore.

If the selected revision already matches the current title, document, and document schema, the restore is a no-op and does not create a redundant content version.

## Authorization and Privacy

Revision history is private and owner scoped.

- Reading a revision list requires an authenticated session and ownership of the note.
- Restoring a revision requires ownership of both the note and the revision plus a valid CSRF token.
- A revision ID from another user or another note is treated as unavailable rather than revealing cross-user object existence.
- Revision restore uses the same optimistic-concurrency principle as normal content saves.

## Current Retention Policy

During native Milestone 0, existing note revisions are retained indefinitely within the application database unless a separately approved migration or recovery operation requires otherwise.

No user-facing or API operation for permanently deleting individual revisions is approved in Milestone 0.

No user-facing or API operation for permanently deleting a trashed native note is approved in Milestone 0. Ordinary note deletion remains recoverable Trash only.

This conservative policy exists because permanent deletion must be designed together with:

- production backup and restore behavior;
- attachment-byte deletion semantics;
- retention periods and any grace period;
- audit/recovery expectations;
- migration rollback requirements;
- multi-device synchronization behavior;
- legal or family-record preservation requirements where applicable; and
- explicit confirmation and authorization UX.

A future permanent-delete design must not be inferred from database foreign-key cascade behavior. Database cascades are integrity mechanisms, not product authorization.

## Production Gate

Before permanent deletion can be enabled, GoreeCloud Notes must have a reviewed policy and validated implementation covering at minimum:

- what is eligible for permanent deletion;
- who may authorize it;
- whether a waiting or recovery period applies;
- how revisions and attachment bytes are handled;
- how backups interact with deletion and retention;
- what can and cannot be recovered afterward;
- conflict behavior across active clients;
- test coverage for owner isolation and accidental deletion prevention; and
- documented restore/recovery evidence.

Until those gates are complete, preserving recoverability takes precedence over storage reclamation.
