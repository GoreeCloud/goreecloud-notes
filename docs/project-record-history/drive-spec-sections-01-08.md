# Notes Drive Project Specification History — Sections 1–8

**Source:** Google Drive `Project Specification — Notes.docx`  
**Source file ID:** `1-RUxapBX-fQjf7XkU7IKR4gX0vsXR0ZL`  
**Migration treatment:** Source-grounded normalized history. The original Drive source remains protected while this migration is pending.  
**Authority:** Historical/source-era evidence only. Current authority is `PROJECT-SPECIFICATIONS.md`, repository-native feature/change records, and accepted `main`.

## 1. Role

The source defines GoreeCloud Notes as the private, self-hosted GoreeCloud application for note-taking, knowledge management, and personal productivity.

## 2. Purpose

The intended product is a GoreeCloud-owned alternative to Evernote-class knowledge tools while retaining the quick-capture strengths proven in earlier work. Its planned scope includes quick notes, structured notebooks, tags, search, attachments, portable exports, knowledge relationships, and future browser/mobile clients. Privacy, independent maintainability, portability, and recoverability are core requirements.

## 3. Problem being solved

The project is intended to avoid making important notes, attachments, research, and accumulated personal knowledge dependent on a proprietary cloud platform, vendor account, closed data model, subscription-controlled feature set, or provider-controlled product lifecycle.

The source explicitly separates product roles:
- GoreeCloud Notes owns deeper organization, retrieval, long-term knowledge, and broader productivity.
- GoreeCloud Memos owns lightweight quick-note capture.

## 4. Development decision

Notes began as a maintained Memos fork to validate product identity, Glaze UI direction, private publication, quick capture, labels, note state, export behavior, and deployment assumptions.

The source records the later decision to build native GoreeCloud Notes as the long-term architecture. The earlier Notes-branded Memos implementation remains historical engineering evidence and a migration source, not the architecture that future Notes development must inherit.

The historical Memos foundation provided reference capabilities including Markdown quick capture, responsive views, pin/archive behavior, task lists, tags and colors, attachments, search, private user accounts, multiple database backends, Docker deployment, REST/gRPC interfaces, deployment-owned configuration, and no required telemetry.

Future Notes architecture, data model, APIs, UI, testing, and release process are to be defined from GoreeCloud Notes requirements. GoreeCloud Memos may continue independently inside its quick-capture scope.

## 5. Product design

The accepted Memos RC3 interface is retained as a workflow/reference input for a future Notes Quick Notes experience, including patterns such as a collapsed quick composer, card presentation, direct search, labels, direct note actions, responsive behavior, accessibility, and Glaze UI direction.

The native Notes product is intended to expand beyond that model into an Evernote-class knowledge workspace, including a broader three-pane-style workflow where appropriate.

The source requires a structured note model suitable for rich editing, search, notebooks, links, revisions, and future synchronization. Markdown remains a required portable interchange/export representation rather than a requirement that the database exactly mirror the Memos schema.

## 6. Historical Memos MVP required features — migration baseline

The source records these historical Memos-based Notes baseline features:
- GoreeCloud Notes branding and terminology;
- private-by-default use;
- a quick “Take a note…” composer;
- responsive card-grid and optional list presentation;
- pinned notes;
- editable title behavior derived from the first H1 heading;
- Markdown content;
- checklists;
- labels and label colors;
- attachments and inline images;
- search and filtering;
- Archive and restore;
- individual user accounts;
- Light and Dark appearance;
- mobile-friendly responsive UI;
- portable note export in an open machine-readable format;
- documented Docker deployment;
- documented backup/restore; and
- automated tests for GoreeCloud-specific behavior.

These entries are historical migration/reference evidence and are not automatically claims about the native Notes implementation on authoritative `main`.

## 7. Historical Memos MVP exclusions — superseded by native roadmap

The original Memos MVP excluded public/social discovery, public-by-default sharing, reactions/social interaction, collaborative real-time editing, reminders and scheduled notifications, ntfy reminder integration, handwriting/drawing, OCR, voice transcription, dependence on OpenAI/Gemini or required external AI APIs, location-based features, native mobile applications, offline-first synchronization, and web-clipper customization.

The source later reclassifies this list as an MVP-era boundary rather than a permanent prohibition. Browser clipping, OCR, offline work, mobile clients, and similar capabilities may appear in later native Notes phases when governed requirements and evidence are satisfied.

## 8. Historical GoreeCloud-specific Memos changes

The source records the Notes-branded Memos implementation as MIT-licensed with required Memos attribution and now transitional/historical for the Notes project.

Material historical changes included:
- RC2/RC3 movement from a timeline-oriented interface toward a notes-oriented GoreeCloud workspace and product-polish pass;
- private note creation as the normal workflow;
- public/social/discovery surfaces removed from the primary experience;
- a Keep-style quick composer, inline search, label chips, and streamlined card actions;
- persistent note colors;
- recoverable Trash instead of immediate ordinary-user permanent deletion;
- individual Markdown export and full-library Markdown/JSON export; and
- deployment/release-validation documentation plus isolated authenticated persistence checks for note content, checklist data, source-derived labels, color, pin/archive/Trash state, and linked attachment bytes.

The historical full-library JSON export preserved normalized attachment metadata but not attachment binary payloads.

The source treats this evidence as useful migration/data-preservation input while keeping deployed browser workflow acceptance, durable backup/restore, and full migration validation open. A Stable Memos-based GoreeCloud Notes release is not presented as the next Notes milestone.

## Interpretation

These sections document the historical product evolution that led to the native Notes decision. They do not override the current Notes/Memos separation, accepted `main` state, or the candidate-only status of the native Draft stack.
