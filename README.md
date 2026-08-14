# GoreeCloud Notes

GoreeCloud Notes is a privacy-first, self-hosted note-taking, knowledge-management, and personal-productivity application developed as original GoreeCloud-owned software.

## Status

**Milestone 0 — Native Foundation is in progress. Production deployment is not approved.**

The native repository is being established independently from the transitional Memos-based GoreeCloud Notes implementation. `GoreeCloud/memos` remains preserved as a migration source, historical engineering record, and visual reference for the accepted Quick Notes experience until migration and replacement validation are complete.

## Product Direction

GoreeCloud Notes will combine fast capture with an Evernote-class knowledge workspace. Planned product capabilities include:

- Quick Notes and a low-friction capture workflow.
- Notebooks and nested notebooks.
- All Notes, tags, favorites, shortcuts, pinned notes, Archive, and recoverable Trash.
- Rich structured editing with Markdown interoperability.
- Attachments and inline images.
- Full-text search and filters.
- Internal note links and backlinks.
- Revision history and recovery.
- Portable full-library export and controlled import/migration tooling.
- Firefox-first browser clipping in a later milestone.
- Future offline and mobile clients after the server API and synchronization model mature.

## Native Architecture

```text
Browser / future clients
        |
        | versioned HTTPS API
        v
React + TypeScript + Vite
        |
        v
FastAPI / Python
        |
        +---- PostgreSQL
        |
        +---- GoreeCloud-managed attachment storage
```

Initial technology direction:

- Frontend: React + TypeScript + Vite.
- Design language: GoreeCloud Glaze UI.
- Backend: Python + FastAPI.
- Database: PostgreSQL.
- Search: PostgreSQL full-text search initially.
- API: versioned HTTP API designed for web, browser-extension, and future mobile clients.
- Deployment: Docker and Docker Compose after development validation.
- License: GNU Affero General Public License v3.0 only (`AGPL-3.0-only`).

## Repository Structure

```text
goreecloud-notes/
├── frontend/                 # React/TypeScript/Vite web application
├── backend/                  # FastAPI application and tests
├── docker/                   # Container/deployment support
├── docs/                     # Architecture, security, development, and migration records
├── tests/                    # Cross-component and future end-to-end tests
├── .github/workflows/        # Continuous integration
├── .env.example              # Sanitized development configuration template
├── compose.yml               # Development Compose stack
├── CONTRIBUTING.md
├── LICENSE
└── README.md
```

## Development Safety Boundaries

- Do not commit passwords, tokens, private keys, production session values, or other reusable credentials.
- Do not use production personal/family notes as a convenient development dataset.
- Do not modify or delete the transitional Memos database or attachments merely because native development has started.
- Do not publish backend ports directly to the public internet.
- Do not treat a development container, migration, or local test as production approval.
- Preserve data portability, migration traceability, backup requirements, and rollback capability throughout development.

## Milestone 0

The native foundation milestone establishes:

- Repository and branch governance.
- AGPL-3.0-only licensing.
- React/TypeScript/Vite frontend foundation.
- FastAPI backend foundation.
- PostgreSQL development service.
- Initial database/migration boundary.
- Authentication and authorization architecture.
- Glaze UI application shell.
- CI for backend tests and frontend lint/build.
- Development, security, architecture, and migration documentation.

Milestone 0 is not complete until the foundation is validated and the remaining database, authentication, authorization, migration, and dependency-locking work is explicitly closed.

## Branch Model

- `main` — reviewed stable repository state.
- `feature/*` — isolated feature development.
- `fix/*` — bug fixes.
- `security/*` — security changes.

A permanent `develop` branch is not required unless project complexity later demonstrates a real need.

## License

GoreeCloud Notes is licensed under the GNU Affero General Public License v3.0 only (`AGPL-3.0-only`). See `LICENSE`.
