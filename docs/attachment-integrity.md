# Attachment Storage Integrity Audit

## Purpose

GoreeCloud Notes stores attachment metadata in PostgreSQL and attachment bytes in GoreeCloud-managed private filesystem storage. A stable release must not assume those two persistence layers remain consistent merely because an upload originally succeeded.

The administrative integrity audit provides a **read-only verification boundary** for one account's attachment store.

```bash
python -m app.cli audit-attachments --username <account>
```

Machine-readable output is available with:

```bash
python -m app.cli audit-attachments --username <account> --json
```

## What the Audit Verifies

For every attachment row owned by the selected account, the audit verifies:

- the attachment row still belongs to the selected account;
- the referenced note is owned by the same account;
- the persisted storage key matches the generated `owner/note/attachment` layout;
- no two attachment rows reuse the same storage key;
- the storage path remains beneath the configured attachment root;
- the storage path does not traverse a symbolic-link component;
- the expected file exists and is a regular file;
- the on-disk byte size matches PostgreSQL metadata; and
- the on-disk SHA-256 value matches PostgreSQL metadata.

The audit also walks only the selected owner's storage directory and reports:

- unexpected symbolic links; and
- orphan files that exist beneath the owner directory without a corresponding attachment row.

## Non-Destructive Boundary

The audit never repairs, deletes, moves, renames, quarantines, or rewrites attachment data.

This is deliberate. A mismatched file may represent corruption, a failed operation, an incomplete restore, an operational mistake, or evidence needed for recovery. Automatic cleanup would destroy evidence and could make recovery harder.

If the audit reports a problem, the administrator must preserve the affected data, investigate the cause, verify available backups or exports, and select an explicit recovery action.

## Exit Codes

The CLI uses the following exit behavior:

- `0` — the selected account's audited attachment store is clean;
- `2` — the command could not run because of invalid input or another administrative command error; and
- `3` — the audit completed but found one or more integrity problems.

Exit code `3` is intended for monitoring and automation. It distinguishes detected integrity findings from a command invocation failure.

## JSON Contract

The current machine-readable report uses:

- format: `goreecloud-notes-attachment-audit`
- schema version: `1`
- selected owner/account identity;
- a `clean` boolean;
- summary counts for attachment records, verified attachments, metadata bytes, observed bytes, orphan files, and issues; and
- explicit issue codes with attachment/storage-key context where applicable.

The schema is an administrative diagnostic contract, not a portable user-data format. Stable automation should check both `format` and `schemaVersion` before interpreting fields.

## CI Validation

The disposable Compose gate creates an isolated account and attachment, then proves all of the following against the real PostgreSQL and attachment-volume stack:

1. a healthy attachment store audits cleanly;
2. direct byte corruption is detected and returns exit code `3`;
3. restoring the original bytes returns the audit to a clean state;
4. removing the expected file is reported as missing bytes;
5. restoring the file returns the audit to a clean state;
6. an unexpected owner-scoped file is reported as an orphan and is not auto-deleted; and
7. after the disposable fault injections are removed, the final audit is clean before later export, migration, and recovery gates continue.

Backend unit tests separately validate clean stores, byte corruption, missing bytes, orphan detection, invalid note ownership, storage-key escape, and duplicate storage keys.

## Stable-Release Role

This audit strengthens attachment recoverability and operational observability, but it does not by itself approve production attachment storage.

The following remain separate production gates:

- malware scanning and quarantine policy;
- PDF/office/SVG preview and active-content policy;
- per-user or deployment storage quotas;
- resumable and very-large-object upload behavior;
- final production filesystem/object-storage architecture;
- scheduled integrity-audit cadence and alert routing;
- production backup repository, retention, off-host/off-site protection, and restore validation; and
- production monitoring and incident-response procedures for detected integrity failures.

No audit result authorizes permanent deletion of attachment bytes required by current note content or retained revision history.
