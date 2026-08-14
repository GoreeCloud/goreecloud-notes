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
fastapi dev
```

The default API address is `http://127.0.0.1:8000`.

Validation:

```bash
pytest
python -m compileall -q app migrations
```

`/health` is the dependency-free liveness endpoint. `/ready` is the database-backed readiness endpoint and succeeds only after the API can execute a real PostgreSQL query. The readiness response is deliberately non-sensitive and does not expose database connection details.

## Frontend

```bash
cd frontend
npm install
npm run lint
npm run build
npm run dev
```

The default frontend address is `http://127.0.0.1:5173` and Vite proxies `/api` and `/health` to the local backend.

The foundation branch intentionally pins direct frontend dependency versions in `package.json`, but a committed npm lockfile remains an outstanding Milestone 0 task. Do not describe frontend dependency locking as complete until `package-lock.json` is generated, reviewed, committed, and CI changes to `npm ci`.

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

## Database Migrations

Alembic is established as the native schema-migration boundary.

After adding or changing SQLAlchemy models:

```bash
cd backend
alembic revision --autogenerate -m 'describe migration'
alembic upgrade head
```

Every generated migration must be reviewed before it is committed. Data-destructive migrations require an explicit migration, backup, rollback, and validation plan.

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
