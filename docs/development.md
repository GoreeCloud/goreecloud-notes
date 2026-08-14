# GoreeCloud Notes Development

## Requirements

The initial local development workflow expects:

- Python 3.13
- Node.js 24
- npm
- Docker Engine and Docker Compose
- Git

## Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The default API address is `http://127.0.0.1:8000`.

Validation:

```bash
pytest
python -m compileall -q app migrations
```

`/health` is the dependency-free liveness endpoint. `/ready` is the database-backed readiness endpoint and succeeds only after the API can execute a real PostgreSQL query. The readiness response is deliberately non-sensitive and does not expose database connection details.

## Frontend

For a clean install from the reviewed dependency graph:

```bash
cd frontend
npm ci
npm run lint
npm run build
npm run dev
```

The default frontend address is `http://127.0.0.1:5173` and Vite proxies `/api` and `/health` to the local backend.

Direct frontend dependency versions are pinned in `package.json`, and the resolved npm dependency graph is committed in `frontend/package-lock.json`. Continuous Integration uses `npm ci` so a mismatch between the manifest and lockfile fails instead of silently rewriting the dependency graph.

When intentionally changing frontend dependencies, use the appropriate `npm install` command to update both `package.json` and `package-lock.json`, review the resulting lockfile diff, and commit the two files together. Do not hand-edit npm integrity hashes or resolved transitive versions.

## Docker Development

Create local configuration and a file-backed PostgreSQL password:

```bash
cp .env.example .env
mkdir -p secrets
python -c 'import secrets; print(secrets.token_urlsafe(48))' > secrets/postgres_password
sudo chgrp 20001 secrets/postgres_password
chmod 600 .env
chmod 640 secrets/postgres_password
```

The numeric group must match `APP_SECRET_GID` in `.env`. Docker Compose grants that supplementary group to the non-root API process so the process can read the secret without making the file world-readable or running the application as root. File-backed Compose secrets preserve the source file's host ownership and mode, so changing the secret to mode `0600` without changing its owner to the API UID will prevent the non-root API process from reading it.

Validate and start PostgreSQL/API:

```bash
docker compose config --quiet
docker compose build api
docker compose up -d db
docker compose run --rm api alembic upgrade head
docker compose up -d api
docker compose ps
curl --fail http://127.0.0.1:8000/health
curl --fail http://127.0.0.1:8000/ready
curl --fail http://127.0.0.1:8000/api/v1/meta
```

The readiness check validates more than process startup: it requires the non-root API process to load its file-backed database credential and complete a real PostgreSQL query.

No production service publication is authorized by these commands. The API host port is bound to loopback only and PostgreSQL has no published host port.

## Private Account Creation

GoreeCloud Notes does not expose an open registration endpoint. Create development or approved private accounts from the server-side CLI after migrations are applied:

```bash
docker compose exec api python -m app.cli create-user \
  --username example-user \
  --display-name 'Example User'
```

The command prompts for the password twice without placing it on the command line. `--password-stdin` exists for controlled automation such as CI, but should not be used with a shell command that would expose a reusable password in history.

Passwords are stored as salted `scrypt` hashes. User identity is stored separately from credential material.

## Browser Authentication

The browser uses opaque database-backed sessions rather than self-contained JWT access tokens. The browser receives:

- `goreecloud_notes_session`: an HTTP-only session secret;
- `goreecloud_notes_csrf`: a readable CSRF secret used for the double-submit check.

Only SHA-256 digests of those browser secrets are persisted in PostgreSQL. State-changing authenticated requests send the CSRF value in the `X-CSRF-Token` header. Cookies use `SameSite=Strict`; `Secure` is automatically enabled outside the development environment. The default session lifetime is 12 hours and is controlled by `GOREECLOUD_NOTES_SESSION_TTL_SECONDS`.

Current authentication endpoints are:

- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me`
- `POST /api/v1/auth/logout`

Logout revokes the server-side session rather than merely deleting a browser cookie.

## Native Workspace API

The foundation now exposes the first authenticated persistence boundary:

- `GET /api/v1/notebooks`
- `POST /api/v1/notebooks`
- `GET /api/v1/notes`
- `POST /api/v1/notes`
- `GET /api/v1/notes/{note_id}`
- `PATCH /api/v1/notes/{note_id}`
- `DELETE /api/v1/notes/{note_id}`
- `GET /api/v1/notes/{note_id}/revisions`

Every query and mutation is explicitly scoped to the authenticated user. A request for another user's note or notebook receives the same not-found behavior as an unknown identifier. Ordinary note deletion moves the note to recoverable Trash rather than hard-deleting it.

The current editor bridge stores an application-owned structured document envelope named `goreecloud.blocks`. This is intentionally independent of a final rich-text editor library. Title/document edits create immutable pre-change revision snapshots. The frontend currently provides manual Save; autosave and the final rich-text editor remain later gates.

## Database Migrations

Alembic is the native schema-migration boundary. The foundation includes the first native notes schema and the separate authentication migration.

After adding or changing SQLAlchemy models:

```bash
cd backend
alembic revision --autogenerate -m 'describe migration'
alembic upgrade head
```

Every generated migration must be reviewed before it is committed. Data-destructive migrations require an explicit migration, backup, rollback, and validation plan.

CI validates an `upgrade head -> alembic check -> downgrade base -> upgrade head -> alembic check` round trip against PostgreSQL.

## Branch Workflow

Create work from the current reviewed `main` branch:

```bash
git switch main
git pull --ff-only
git switch -c feature/<focused-name>
```

Validate the affected components, push the branch, and open a pull request. Do not make `main` the normal development workspace.

## Data Rules

Use synthetic note content and synthetic users during development. Do not import the production/transitional Memos dataset into an ordinary development environment merely for convenience.

Migration development should begin with copied, isolated, protected source data and should never mutate the authoritative transitional source by default.
