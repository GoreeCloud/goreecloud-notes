# Security

GoreeCloud Notes is a privacy-first application intended to hold personal and family knowledge. Security defects that could expose note content, attachments, credentials, sessions, authorization boundaries, exports, backups, or migration data are treated as high-impact issues.

## Repository Security Rules

- Never commit reusable passwords, tokens, API keys, private keys, session values, database credentials, or production secrets.
- Never commit real private note content or personal/family data as test fixtures.
- Use synthetic development data.
- Keep backend services loopback-only or private during development.
- Treat every note, attachment, notebook, tag, export, search result, and revision as user-scoped data unless an explicit sharing model is implemented and authorized.
- Re-check authorization at the mutation and export boundaries rather than trusting browser state.
- Keep migration tooling read-safe by default and validate source/target counts and ownership before retirement of a source system.

## Authentication and Authorization Direction

Milestone 0 establishes the architecture but does not yet claim a production-ready authentication system.

The native application will use individual accounts, opaque server-side session identifiers, secure HTTP-only cookies, CSRF protection for browser mutations, password hashing suitable for interactive authentication, and explicit authorization helpers that scope every user-data query before filtering or mutation.

Authentication success must never imply unrestricted access to another user's notes, notebooks, tags, attachments, exports, revisions, or search results.

## Production Gate

Production publication is not approved until authentication, authorization, session storage, CSRF behavior, database protection, attachment storage, backup, restoration, migration, monitoring, and private-service publication have been reviewed and validated together.
