# Production Runtime Readiness Boundary

GoreeCloud Notes is not approved for production by source configuration alone. This document defines the source-level production runtime preflight, attachment-quota, administrative suspension, Glaze UI interaction, and frontend bundle boundaries added during Milestone 0 and separates those source controls from target-environment publication, monitoring, backup, migration, operator authorization, and final administrator acceptance.

## Purpose

Development defaults are intentionally convenient for an isolated workstation or disposable CI environment. They are not valid production values. A production process must fail closed rather than silently starting with localhost browser origins, an unresolved reverse-proxy trust boundary, relative attachment storage, an unbounded owner-level attachment allowance, or an inline database password.

The production runtime boundary therefore has two layers:

1. `Settings` rejects known unsafe production configuration before the application starts.
2. `python -m app.production_check` verifies non-secret target filesystem and configuration prerequisites without connecting to PostgreSQL or mutating application data.

A separate account-lifecycle boundary allows an authorized local operator to suspend or reinstate an account without deleting its data. Shared Glaze UI interaction checks and a production JavaScript chunk budget protect accessibility and initial-load performance from silent regression. None of these source-level controls grants production approval.

## Production Configuration Requirements

When `GOREECLOUD_NOTES_ENVIRONMENT=production`, the application requires:

- one or more explicit credentialed CORS origins;
- HTTPS for every production browser origin;
- no localhost or loopback browser origin;
- no wildcard credentialed CORS origin;
- one or more explicitly verified trusted reverse-proxy CIDRs so forwarded-source handling does not silently collapse every browser behind the proxy into one login-rate source;
- an absolute attachment-storage root;
- an explicit positive owner-level attachment quota;
- an owner-level attachment quota at least as large as the configured maximum permitted single attachment;
- a file-backed PostgreSQL password path rather than an inline database password;
- an absolute database-secret file path.

The application does not guess production Caddy, Docker, VM, VLAN, NetBird, storage-capacity, or quota values. Those values must come from the validated target topology and an approved storage-capacity decision.

The normal development/test configuration remains separate and can keep the owner-level attachment quota disabled with `GOREECLOUD_NOTES_ATTACHMENT_USER_QUOTA_BYTES=0`. This convenience is rejected in production.

## Owner Attachment Quota Boundary

The per-file attachment limit and the owner-level total-storage quota are separate protections. A file can be smaller than the permitted single-file size while still exceeding the authenticated owner's remaining total allowance.

Uploads are first streamed to a server-generated temporary file. Before the temporary file becomes the durable attachment object, the backend locks the authenticated user's stable database row and calculates that owner's current attachment-byte total. Only one final quota decision for the same owner can commit at a time. This prevents concurrent requests from both observing the same stale usage value and jointly exceeding the configured allowance.

When an upload would exceed the owner quota, the API returns HTTP `413`, rolls back the database transaction, and removes temporary/final upload artifacts. The quota is owner-scoped rather than a global application pool, so one user's exhausted allowance does not consume another user's configured allowance.

The source implementation deliberately does **not** select the final production quota value. Actual production capacity, reserve margin, quota size, filesystem/object-storage placement, monitoring, backup implications, and growth policy remain target-environment decisions.

## Production Preflight Command

With the intended production environment variables and mounted secret/storage paths present, run:

```bash
python -m app.production_check
```

Machine-readable output is available with:

```bash
python -m app.production_check --json
```

Schema-v1 output reports only non-sensitive check names and boolean state. It does not print the database secret, database URL, attachment path, proxy addresses, quota value, or application data.

The static preflight checks:

- production environment selection;
- secure-cookie behavior;
- HTTPS credentialed origins;
- presence of an explicit trusted-proxy boundary;
- database secret-file existence, regular-file status, non-empty size, readability, non-symlink status, and absence of world permissions;
- attachment-root existence, directory status, non-symlink status, and process read/write/traverse access;
- presence of a positive owner-level attachment quota that is at least the maximum permitted single-attachment size.

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

The development Dockerfile and Compose service health checks use `/ready` rather than `/health`. An API process whose required persistence layers are unavailable is therefore not advertised as a healthy service merely because the Python process is running.

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

## Glaze UI and Frontend Performance Boundary

The native frontend now has a shared `glaze-foundation.css` layer loaded after feature/component styles. It centralizes interaction-sensitive Glaze UI behavior without replacing mature product-specific styling. The shared boundary includes:

- reusable Glaze accent, focus, geometry, touch-target, motion-duration, and easing tokens;
- a 44-pixel minimum target for high-frequency and coarse-pointer controls covered by the shared layer;
- visible keyboard-focus treatment;
- card elevation only on fine-pointer devices that genuinely support hover;
- removal of retained hover elevation on coarse/no-hover devices;
- `prefers-reduced-motion: reduce` handling for the shared Glaze interactions.

`frontend/scripts/validate-glaze-foundation.mjs` is part of the production build and fails if the required shared accessibility/input-mode rules disappear or if the foundation stylesheet is no longer loaded after component styles.

The rich Tiptap editor is also loaded through a React lazy/Suspense boundary rather than being part of the initial application JavaScript chunk. The measured Vite production output changed from a single 635.72 kB initial JavaScript chunk to:

- 239.33 kB initial application JavaScript;
- 397.46 kB on-demand `RichNoteEditorCore` JavaScript.

The build no longer emits Vite's previous greater-than-500-kB chunk warning. `frontend/scripts/validate-bundle-budget.mjs` now fails the production build if any emitted JavaScript chunk exceeds 500,000 bytes. This ceiling records the warning threshold that exposed the regression; it is not a substitute for later real-device/network performance acceptance.

## CI Evidence

`.github/workflows/production-readiness.yml` provides a dedicated **Production Runtime Preflight** source gate. It uses only synthetic temporary paths and a synthetic secret. The workflow:

1. installs the locked backend dependency graph;
2. creates an isolated synthetic attachment directory and file-backed database secret;
3. runs the production preflight with explicit HTTPS origin, trusted-proxy values, and an explicit synthetic owner-level attachment quota;
4. requires every static check to pass while `productionApprovalGranted` remains false;
5. reruns the command with unsafe production defaults, including a disabled owner quota, and requires a non-zero result plus machine-readable failure evidence.

The main Continuous Integration workflow separately exercises `/ready` against the disposable Compose/PostgreSQL/attachment-volume stack and validates the administrative account lifecycle against a disposable account. The authentication gate proves that disable requires confirmation, revokes the active session, blocks login without disclosing account state, preserves the credential for later reinstatement, prevents stale-cookie resurrection, and permits a fresh login after re-enable.

The live attachment-quota gate configures a deliberately small synthetic allowance. It proves that a 40,000-byte attachment can be stored, another 30,000-byte attachment for the same owner is rejected with HTTP `413` even though it remains far below the per-file 50 MiB limit, only the accepted attachment remains in metadata, a second user retains an independent allowance, and rejected uploads leave no `.part` objects behind.

The frontend job runs both Glaze UI foundation validation and the JavaScript chunk budget as part of the ordinary production build. The exact source checkpoint `cb658e0e549871bacd37e3fff3c1babac3fe3827` passed Continuous Integration run `31867634865` / run #280 and Production Runtime Preflight run `31867634897` / run #31. The measured build at that checkpoint emitted a 239.33 kB initial JavaScript chunk and a 397.46 kB lazy rich-editor chunk; the bundle budget reported 397,460 bytes as the largest JavaScript asset.

These checks validate source behavior without converting CI into production-environment, real-device, or operator-authorization evidence.

## Production Gates Still Open

The implemented source boundary closes the unsafe-default/basic runtime-readiness gap, establishes bounded owner-level attachment quota enforcement, provides reversible administrative account suspension, and protects selected Glaze UI/performance behavior from source regression. Production still requires separate evidence for:

- final Family Services VM placement and persistent storage paths;
- final Caddy route and exact trusted-proxy CIDRs;
- DNS and NetBird/private-publication reconstruction;
- publication-layer abuse controls, production monitoring, and alert routing;
- target-environment attachment ownership and permissions;
- approved production attachment-storage capacity and the selected real owner quota value;
- malware scanning/quarantine and large-object/resumable-upload policy;
- final production filesystem/object-storage design;
- production Kopia repository, encryption, retention, off-host/off-site protection, monitoring, and notification routing;
- selected RPO and measured RTO;
- isolated production-representative restore;
- protected-copy Memos attachment extraction and production-representative migration rehearsal;
- final operator authorization, auditing, and runbooks for account creation, recovery, suspension, and reinstatement;
- production image/release policy and rollback validation;
- real-device/network frontend performance and final administrator acceptance.

The transitional `GoreeCloud/memos` service and `notes.goreecloud.com` publication remain protected and unchanged until those gates are validated together. A green Production Runtime Preflight, quota test, Glaze check, bundle budget, or lifecycle test must not be used as justification to retire Memos, migrate production data, change DNS/Caddy/NetBird, or enable permanent deletion.
