# Backup and Restore Readiness

GoreeCloud Notes is not approved for production until PostgreSQL state and private attachment bytes can be captured, independently verified, restored together, and reconciled with current security state. This document records the Milestone 0 disposable recovery model and the production gates that remain open.

## Recovery Units

A usable GoreeCloud Notes recovery point must cover at least:

1. the PostgreSQL database, including users, password credential hashes, notebooks, notes, tags, relationships, revisions, attachment metadata, schema/version state, and other native relational records;
2. private attachment bytes stored outside PostgreSQL;
3. source code or an independently reproducible application image;
4. deployment configuration;
5. separately protected reusable secrets;
6. private publication configuration and monitoring once those are approved for production.

Database state and attachment bytes form one logical application recovery point. Restoring one without the other can produce broken note documents or orphaned attachment metadata and is not considered a valid application restore.

## Database Capture

The Milestone 0 validation uses PostgreSQL's native `pg_dump` custom format with ownership and privilege restoration disabled for portability into a controlled replacement database.

A production procedure must select an application-consistent capture method and schedule rather than assuming that independent database and attachment copies taken at unrelated times form a valid recovery point. The final production method must also define retention, encryption, Kopia protection, off-host/off-site independence, monitoring, and recovery-point objectives.

## Attachment Capture

The disposable validation archives the server-controlled attachment root separately from PostgreSQL. Only server-generated files beneath that root are included. The recovery archive is SHA-256 verified together with the database dump before destructive testing begins.

The validation extracts only relative regular-file archive members and rejects absolute paths, path traversal, or unsupported member types. Production backup tooling may use a different transport, but it must preserve the same storage-boundary and integrity guarantees.

## Security-State Reconciliation After Restore

A historical database restore can reintroduce browser sessions and short-lived login-rate state that were valid when the backup was taken but should not automatically become current authorization after a disaster recovery event.

Therefore the Milestone 0 restore procedure invalidates restored `auth_sessions` and `login_rate_buckets` **before the API is started**. Password credential hashes remain recoverable so users can establish new sessions through ordinary authentication after restoration.

This is a conservative initial rule. Any future persistent API tokens, sharing credentials, recovery grants, browser-extension credentials, or mobile sync credentials must receive their own explicit restore-reconciliation policy before production use.

## Disposable Destructive Validation

`scripts/ci_validate_backup_restore.sh` runs only against the disposable CI Compose project. It:

1. creates a synthetic private user, note, raster attachment, and attachment-ID inline image;
2. creates a PostgreSQL custom-format dump;
3. creates a separate attachment archive;
4. records and verifies SHA-256 checksums for both artifacts;
5. destroys the disposable PostgreSQL and attachment volumes;
6. creates a clean replacement PostgreSQL volume;
7. restores the database dump;
8. invalidates restored sessions and rate-limit state before application startup;
9. restores attachment bytes into a clean attachment volume without starting the API against incomplete storage;
10. starts GoreeCloud Notes only after both data layers exist;
11. runs `alembic check` against the recovered database;
12. proves the pre-backup browser session is invalid;
13. proves the preserved credential can create a fresh session;
14. verifies the expected note/document/attachment relationship;
15. verifies restored attachment bytes exactly match the original SHA-256/source bytes;
16. verifies no historical rate-limit state survived and only the intentionally fresh post-restore browser session exists;
17. creates a new database recovery point from the restored application state.

The test is destructive by design but operates only on synthetic CI state. It must never be pointed at the production Compose project or production data.

## Production Gates Still Open

A green disposable recovery test does **not** approve production backup or restoration. Production still requires:

- final database and attachment storage locations;
- a coordinated application-consistent backup procedure;
- Kopia repository/snapshot configuration and retention;
- an independent/off-host or off-site recovery copy appropriate to GoreeCloud policy;
- backup-health monitoring and notification delivery;
- final secret-recovery procedure and access controls;
- target-environment ownership, permissions, and storage-capacity evidence;
- selected RPO and measured RTO;
- restore into an isolated production-representative environment;
- authentication and authorization reconciliation for every credential type that exists at that time;
- migration/version compatibility checks across supported releases;
- rollback procedure;
- documented administrator acceptance evidence.

The transitional `GoreeCloud/memos` environment is not modified or retired by this validation. Native backup readiness and Memos migration/rollback remain separate gates until the controlled cutover is approved.
