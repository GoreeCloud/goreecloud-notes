# Production Runtime Readiness Boundary

GoreeCloud Notes is not approved for production by source configuration alone. This document defines the source-level production runtime preflight added during Milestone 0 and separates that preflight from target-environment publication, monitoring, backup, migration, and administrator acceptance.

## Purpose

Development defaults are intentionally convenient for an isolated workstation or disposable CI environment. They are not valid production values. A production process must fail closed rather than silently starting with localhost browser origins, an unresolved reverse-proxy trust boundary, relative attachment storage, or an inline database password.

The production runtime boundary therefore has two layers:

1. `Settings` rejects known unsafe production configuration before the application starts.
2. `python -m app.production_check` verifies non-secret target filesystem prerequisites without connecting to PostgreSQL or mutating application data.

Neither layer grants production approval.

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

## CI Evidence

`.github/workflows/production-readiness.yml` provides a dedicated **Production Runtime Preflight** source gate. It uses only synthetic temporary paths and a synthetic secret. The workflow:

1. installs the locked backend dependency graph;
2. creates an isolated synthetic attachment directory and file-backed database secret;
3. runs the production preflight with explicit HTTPS origin and trusted-proxy values;
4. requires every static check to pass while `productionApprovalGranted` remains false;
5. reruns the command with unsafe production defaults and requires a non-zero result plus machine-readable failure evidence.

The main Continuous Integration workflow separately exercises `/ready` against the disposable Compose/PostgreSQL/attachment-volume stack. This validates live dependency readiness without converting CI into production-environment evidence.

## Production Gates Still Open

This boundary closes only the source-level unsafe-default and basic runtime-readiness gap. Production still requires separate evidence for:

- final Family Services VM placement and persistent storage paths;
- final Caddy route and exact trusted-proxy CIDRs;
- DNS and NetBird/private-publication reconstruction;
- publication-layer abuse controls and monitoring;
- target-environment attachment ownership, permissions, capacity, quota, scanning/quarantine, and large-object policy;
- production Kopia repository, encryption, retention, off-host/off-site protection, monitoring, and notification routing;
- selected RPO and measured RTO;
- isolated production-representative restore;
- protected-copy Memos attachment extraction and production-representative migration rehearsal;
- target administrator/account lifecycle procedures;
- production image/release policy and rollback validation;
- final administrator acceptance.

The transitional `GoreeCloud/memos` service and `notes.goreecloud.com` publication remain protected and unchanged until those gates are validated together. A green Production Runtime Preflight must not be used as justification to retire Memos, migrate production data, change DNS/Caddy/NetBird, or enable permanent deletion.
