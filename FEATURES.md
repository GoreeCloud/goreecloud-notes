# GoreeCloud Notes — Features

GoreeCloud Notes is a native GoreeCloud application in active development. This list records source-implemented capabilities separately from still-open migration and production-readiness work.

## Current source-implemented capabilities

- Core private note creation and management
- Private authentication and owner/user isolation
- Glaze UI account and security surfaces
- Rich structured editing
- Revision recovery
- Indexed PostgreSQL-backed search
- Private attachments and inline images
- Read-only attachment-storage integrity auditing
- Bounded login security and trusted-proxy validation
- Password recovery
- Append-only privileged-account audit boundary
- Full-library portable export through CLI and authenticated browser delivery
- Empty-target native portable re-import
- Migration-provenance preservation through export, re-import, and re-export
- Reproducible frontend and backend dependency locks
- Disposable PostgreSQL-and-attachment backup/restore validation
- Controlled synthetic Memos-to-native import and equivalence validation
- Per-owner attachment quota enforcement
- Canonical Glaze UI adoption with local System, Light, and Dark appearance modes
- Shared Glaze UI interaction and accessibility foundation
- Unsaved-draft navigation protection
- Frontend JavaScript bundle performance budget
- Read-only Evernote ENEX migration inspection with source fingerprinting and safety checks
- Controlled ENEX resource extraction evidence
- Provider-neutral exact-ENML normalization
- Zero-write ENML-to-`goreecloud.blocks` conversion review
- Private note templates
- Owner-scoped internal note links and backlinks
- Guarded connected-note and inline note-link navigation
- Automated backend, frontend, migration, security-boundary, Compose, and production-preflight validation in the development workflow

## Migration and portability foundations

- Historical Memos-based Notes environment retained as a protected migration source
- Controlled Memos inventory and synthetic migration validation
- Evernote ENEX inspection, resource extraction, normalization, and conversion stages designed to avoid silent source or target mutation
- Markdown remains a required portable interchange/export representation even though the native editor uses a structured note model

## Planned / acceptance-gated capabilities

- Protected-source production Memos migration rehearsal
- Final target-environment production readiness and deployment acceptance
- Controlled cutover of `notes.goreecloud.com` to the native application
- Final production attachment capacity, quota, scanning, and storage policy
- Production monitoring, abuse controls, backup, off-host/off-site recovery, RPO/RTO, and operator runbooks
- Broader notebook/collection and advanced knowledge-workspace features as native milestones continue
- Firefox-first WebExtensions clipping for articles, selections, URLs, bookmarks, and quick-note capture
- Future mobile clients and offline/synchronization work where separately designed and validated
- Later OCR or other advanced capture capabilities only when they can be implemented without required proprietary AI dependence

## Product boundary

GoreeCloud Notes is the full knowledge-management and long-term notes application. GoreeCloud Memos remains the separate lightweight quick-capture product. Shared concepts or controlled interoperability do not merge their roles.

## Status rule

Passing source tests or CI does not by itself establish production acceptance. Features that depend on deployment, migration, real-device behavior, or production infrastructure remain acceptance-gated until those boundaries are validated.
