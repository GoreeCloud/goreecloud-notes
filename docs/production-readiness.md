# Production Runtime Readiness Boundary

GoreeCloud Notes is not approved for production by source configuration alone. This document defines the source-level production runtime preflight and administrative suspension boundary added during Milestone 0 and separates those source controls from target-environment publication, monitoring, backup, migration, operator authorization, and final administrator acceptance.

## Purpose

Development defaults are intentionally convenient for an isolated workstation or disposable CI environment. They are not valid production values. A production process must fail closed rather than silently starting with localhost browser origins, an unresolved reverse-proxy trust boundary, relative attachment storage, or an inline database password.

The production runtime boundary therefore has two layers:

1. `Settings` rejects known unsafe production configuration before the application starts.
2. `python -m app.production_check` verifies non-secret target filesystem prerequisites without connecting to PostgreSQL or mutating application data.

A separate account-lifecycle boundary allows an authorized local operator to suspend or reinstate an account without deleting its data. None of these source-level controls grants production approval.

## Production Configuration Requirements

When `GOREECLOUD_NOTES_ENVIRONMENT=production`, the application requires:

- one or more explicit credentialed CORS origins;
- HTTPS for every production browser origin;
- no localhost or loopback browser origin;
- no wildcard credentialed CORS origin;
- one or more explicitly verified trusted reverse-proxy CIDRs so forwarded-source handling does not silently collapse every browser behind the proxy into one login-rate source;
- an absolute attachment-storage root;
- a file-backed PostgreSQL password path rather than an inline database password;
- an absolute database-secret file path.

The application does not guess production Caddy, Docker, VM, VLAN, NetBird, or other private-network CIDRs. Those values must come from the validated target topology.

The normal development configuration remains separate and continues to permit loopback browser origins and an empty trusted-proxy list.

## Production Preflight Command

With the intended production environment variables and mounted secret/storage paths present, run:

```bash
python -m app.production_check
```

Machine-readable output is available with:

```bash
python -m app.production_check --json
```

Schema-v1 output reports only non-sensitive check names and boolean state. It does not print the database secret, database URL, attachment path, proxy addresses, or application data.

The static preflight checks:

- production environment selection;
- secure-cookie behavior;
- HTTPS credentialed origins;
- presence of an explicit trusted-proxy boundary;
- database secret-file existence, regular-file status, non-empty size, readability, non-symlink status, and absence of world permissions;
- attachment-root existence, directory status, non-symlink status, and process read/write/traverse access.

A passing report explicitly records:

- `nonDestructive: true`;
- `liveDependencyValidationPerformed: false`;
- `productionApprovalGranted: false`.

This prevents a successful static check from being misrepresented as a deployment acceptance result.

## Liveness and Readiness

The API retains two separate operational probes:

- `GET /health` is dependency-free process liveness. It confirms that the API process can answer without checking PostgreSQL or attachment storage.
- `GET /ready` is dependency readiness. It succeeds only when PostgreSQL accepts a real query and the configured attachment root exists as a non-symlink directory usable by the API process.

Readiness responses remain intentionally non-sensitive. A failed dependency returns HTTP `503` without exposing database hosts, credentials, filesystem paths, SQL errors, or storage exception details.

The development Dockerfile and Compose service health checks now use `/ready` rather than `/health`. An API process whose required persistence layers are unavailable is therefore not advertised as a healthy service merely because the Python process is running.

Process-level monitoring may still query `/health` separately so operators can distinguish an API-process failure from a dependency-readiness failure.

## Administrative Suspension Boundary

The private account model already separates the account identity from its credential and session records. The source-level lifecycle commands use that separation to provide reversible suspension instead of destructive account deletion.

Operators can review non-sensitive account state with:

```bash
python -m app.cli account-status --username <username>
python -m app.cli account-status --username <username> --json
```

Suspension requires explicit acknowledgement:

```bash
python -m app.cli disable-user \
  --username <username> \
  --confirm-disable
```

A confirmed disable changes only the account's active state and revokes every stored browser session in the same transaction. Credentials and user-owned Notes data remain preserved. Existing browser cookies stop authenticating after the transaction commits, and subsequent login attempts receive the same generic invalid-credential response as other authentication failures.

Reinstatement is explicit:

```bash
python -m app.cli enable-user --username <username>
```

Re-enabling preserves the existing password but also revokes any stored sessions. This prevents a still-unexpired cookie issued before suspension from becoming valid again after reinstatement. A fresh login is required.

This is a source capability, not an authorization policy. Production still needs a documented answer for who may execute these commands, through which privileged host/account, how the action is audited, and how suspension/reinstatement is approved. Permanent account deletion and retention-driven destruction remain outside this boundary.

## CI Evidence

`.github/workflows/production-readiness.yml` provides a dedicated **Production Runtime Preflight** source gate. It uses only synthetic temporary paths and a synthetic secret. The workflow:

1. installs the locked backend dependency graph;
2. creates an isolated synthetic attachment directory and file-backed database secret;
3. runs the production preflight with explicit HTTPS origin and trusted-proxy values;
4. requires every static check to pass while `productionApprovalGranted` remains false;
5. reruns the command with unsafe production defaults and requires a non-zero result plus machine-readable failure evidence.

The main Continuous Integration workflow separately exercises `/ready` against the disposable Compose/PostgreSQL/attachment-volume stack and validates the administrative account lifecycle against a disposable account. The authentication gate proves that disable requires confirmation, revokes the active session, blocks login without disclosing account state, preserves the credential for later reinstatement, prevents stale-cookie resurrection, and permits a fresh login after re-enable.

These checks validate source behavior without converting CI into production-environment or operator-authorization evidence.

## Production Gates Still Open

The implemented source boundary closes the unsafe-default/basic runtime-readiness gap and provides reversible administrative account suspension. Production still requires separate evidence for:

- final Family Services VM placement and persistent storage paths;
- final Caddy route and exact trusted-proxy CIDRs;
- DNS and NetBird/private-publication reconstruction;
- publication-layer abuse controls and monitoring;
- target-environment attachment ownership, permissions, capacity, quota, scanning/quarantine, and large-object policy;
- production Kopia repository, encryption, retention, off-host/off-site protection, monitoring, and notification routing;
- selected RPO and measured RTO;
- isolated production-representative restore;
- protected-copy Memos attachment extraction and production-representative migration rehearsal;
- final operator authorization, auditing, and runbooks for account creation, recovery, suspension, and reinstatement;
- production image/release policy and rollback validation;
- final administrator acceptance.

The transitional `GoreeCloud/memos` service and `notes.goreecloud.com` publication remain protected and unchanged until those gates are validated together. A green Production Runtime Preflight or lifecycle test must not be used as justification to retire Memos, migrate production data, change DNS/Caddy/NetBird, or enable permanent deletion.
