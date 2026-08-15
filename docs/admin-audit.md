# Administrative Audit Boundary

GoreeCloud Notes records privileged local account mutations in PostgreSQL so administrative actions can be attributed and reviewed without creating a public administrator API or storing reusable secrets in ordinary logs.

This is a **source-level accountability control**. It does not by itself authorize anyone to administer production, select a production audit-retention period, prove the identity of the human at the keyboard, configure monitoring, or approve production deployment.

## Scope

The append-only audit boundary currently covers these local CLI mutations:

- `create-user` — `account.create`
- `reset-password` — `credential.reset`
- `disable-user` — `account.disable`
- `enable-user` — `account.enable`

Read-only commands such as `account-status`, `admin-audit`, `audit-attachments`, and export verification do not create administrative mutation events.

There is no browser or public HTTP endpoint for arbitrary account administration.

## Production Attribution Requirement

In production, each covered mutation requires both:

```text
--operator <non-secret operator identifier>
--reason <non-secret operational reason>
```

The values must be supplied together. Production fails closed if both are absent. Development and test environments may omit both values so disposable fixtures and isolated validation can remain simple; supplying only one value is rejected in every environment.

Example:

```bash
python -m app.cli disable-user \
  --username <username> \
  --confirm-disable \
  --operator <approved-operator-id> \
  --reason 'Approved temporary suspension under the account-lifecycle runbook.'
```

The operator identifier is an **asserted operational identity**, not a password, token, certificate, or cryptographic proof of the person executing the command. Production host access, shell identity, sudo policy, operator authorization, and the mapping between an approved administrator and the identifier remain deployment/runbook controls.

## Data Minimization

Each event stores only the information needed for accountability:

- server-generated event UUID;
- target account UUID snapshot;
- target username snapshot;
- action identifier;
- asserted operator identifier;
- non-secret reason;
- small action-specific JSON details such as whether state changed or how many sessions were revoked;
- server-generated timestamp.

The target account UUID is deliberately stored as an immutable snapshot rather than a foreign key. A future separately approved account-deletion workflow must not rewrite historical audit identity through `ON DELETE` behavior.

Administrative audit events must **not** contain:

- passwords or password hashes;
- session or CSRF tokens or their digests;
- recovery codes or API keys;
- note titles or note content;
- attachment filesystem paths or attachment contents;
- authentication cookies;
- client IP-address history or browser fingerprints;
- unrelated private account data.

The `--reason` value is ordinary audit metadata. Operators must never paste a credential, recovery secret, private note content, or other sensitive value into it.

## Transaction Boundary

A covered mutation and its audit event are written inside the same SQLAlchemy transaction.

If audit attribution validation fails, the privileged operation does not begin. If the audit insert fails before commit, the account mutation is rolled back with it. This prevents a production account change from succeeding while its required source-side audit record is missing.

## Append-Only Database Enforcement

Migration `0007_admin_audit_events` creates the `admin_audit_events` table and installs a PostgreSQL trigger that rejects ordinary `UPDATE` and `DELETE` statements against committed audit rows.

This provides a database-level immutability guard in addition to the fact that the application exposes no mutation API for audit records.

The trigger does not claim tamper-proof storage against a database superuser, physical storage administrator, backup administrator, or someone capable of replacing the application/database itself. Production access control, independent backups, monitoring, and administrative separation remain necessary.

The Alembic downgrade intentionally removes the trigger before dropping the table so disposable migration round-trip validation can still return to `base` cleanly.

## Read-Only Review

Recent events can be reviewed locally with:

```bash
python -m app.cli admin-audit --json
python -m app.cli admin-audit --username <username> --limit 50 --json
```

The query is bounded to at most 200 records per invocation and returns only non-secret event fields. It does not expose target user UUIDs in normal CLI output.

## Validation Contract

Continuous Integration must prove that:

- all four covered account mutations can append an event;
- the event action, target username, operator, and reason are preserved;
- generated audit output does not contain the test passwords or common credential/session field names;
- ordinary SQL `UPDATE` against a committed event is rejected;
- ordinary SQL `DELETE` against a committed event is rejected;
- failed tampering attempts leave the committed event count unchanged;
- migration `upgrade head -> check -> downgrade base -> upgrade head -> check` remains valid with the audit trigger present;
- all existing authentication, authorization, portability, migration, backup/restore, attachment, search, and Glaze UI gates remain green.

## Backup and Recovery

Administrative audit events are PostgreSQL application data. The existing database backup/restore validation therefore carries them with the relational database once events exist in the protected dataset.

Production still requires a selected backup repository, retention policy, independent recovery evidence, and a production-representative restore. Source-level inclusion in a database dump is not a substitute for those operational controls.

## Remaining Production Decisions

Before production approval, GoreeCloud must still define and validate:

- which host accounts and administrators may execute privileged Notes CLI commands;
- required shell/sudo or equivalent authorization boundaries;
- the canonical production operator-identifier format;
- what approvals or incident/change records are required for each action class;
- audit retention and archival requirements;
- who may read audit history;
- monitoring and alerting expectations for privileged account changes;
- how audit history is reviewed during security incidents and routine administration;
- how audit records are protected in backup, restore, migration, and disaster-recovery workflows;
- how any future permanent user-deletion feature interacts with preserved audit identity;
- final administrator acceptance of the runbook.

Until those target-environment controls are approved, the presence of the append-only source audit mechanism does **not** make GoreeCloud Notes production-ready.
