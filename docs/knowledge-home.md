# GoreeCloud Notes Knowledge Home

## Status

Knowledge Home is an active native source-development checkpoint on `feature/knowledge-home-foundation` and stacked continuation branches. It is not a production deployment, Stable-release claim, or proof of complete current GLAZE UI V1.0 acceptance.

The surface is inspired by useful knowledge-home information architecture seen in note applications, including the user-supplied Evernote references, but its implementation, state model, styling, privacy boundaries, and interaction behavior are GoreeCloud-owned.

## Current foundation

The source implementation is exposed through the local `#knowledge-home` application route and reads the authenticated user's existing GoreeCloud Notes data through the established owner-scoped API.

Implemented modules are:

- Recent Notes, ordered by existing note update timestamps.
- Relevant Notes, ranked deterministically and locally from already authorized native Notes state.
- Pinned Notes, derived from native `is_pinned` state.
- Scratch Pad, using session-scoped browser storage for transient capture with explicit promotion into a normal Note.
- Shortcuts, summarizing current Notes, notebooks, Archive, and Trash counts.
- Tags, derived from the authenticated user's existing tag collection.

The Home customizer supports module visibility, ordering, and the currently supported standard/wide size choice. These are presentation preferences stored locally in the browser under a user-specific key; they are not server-authoritative knowledge state and are not exported as Notes data.

## Relevant Notes boundary

Relevant Notes is deliberately transparent and deterministic. It is not an AI recommendation service and does not learn from clicks, dwell time, editor behavior, navigation history, account activity, or other behavioral signals.

The current ranking uses only note data already loaded for the authenticated owner by Knowledge Home:

1. native pin state contributes the strongest explicit relevance weight;
2. a non-empty title contributes one bounded point;
3. body substance contributes bounded points at the documented 240-character and 1,000-character thresholds;
4. existing `updated_at` order breaks equal-score ties; and
5. the existing note ID provides a final stable deterministic tie-break.

No ranking score, derived profile, click history, or recommendation history is persisted. The module performs no remote request and introduces no model, vector store, embedding service, telemetry dependency, or cross-application data source. Changing this ranking into personalized intelligence would require a separately reviewed privacy, authority, product, and platform-system contract.

## Scratch Pad boundary

Scratch Pad remains deliberately transient until the user chooses **Save as note**. Its working text is stored in `sessionStorage`, scoped to the active browser tab and authenticated user identifier, with a 4,000-character UI limit.

Saving creates one normal owner-scoped GoreeCloud Note through the existing authenticated and CSRF-protected Notes API. Initial title and document content are sent in the same note-creation request so promotion does not rely on an empty-note-then-patch sequence. The first non-empty Scratch Pad line supplies a bounded title and the complete captured text is converted through the native GoreeCloud document contract.

The durable create request completes before any transient cleanup is attempted. Knowledge Home clears the visible Scratch Pad only when this tab's `sessionStorage` confirms removal of its transient copy. If durable note creation fails, the captured text remains available and the failure is surfaced. If durable creation succeeds but transient cleanup fails, the new Note remains created, the captured text intentionally remains visible, and the UI warns that the transient copy could not be cleared so the user can retry **Clear**. Manual Clear follows the same storage-aware rule and does not hide text when transient removal fails.

A successfully created Note is immediately added to Knowledge Home's current-note state so Recent Notes, Relevant Notes, and the current-note summary reflect it without requiring a reload.

Scratch Pad is not a second note database and does not become durable merely because text exists in the transient capture field.

## Platform-system boundary for Knowledge Home

These increments reuse the existing owner-scoped Notes authority rather than introducing a new product or control plane. GoreeCloud Identity remains represented by the established authenticated account/session boundary; the existing CSRF-protected Notes write path remains the security boundary for Scratch Pad note creation; no new sharing, external transfer, attachment, or cross-application data flow is introduced by Relevant Notes.

GoreeCloud Manager receives no new administrative operation. Privacy Shield and Wardveil Security responsibilities remain within the existing Notes data-flow and authenticated write controls. Relevant Notes adds no behavioral profile or persisted recommendation state. Everkeep continuity remains attached to normal Notes data rather than Home presentation/ranking state. GoreeCloud Mesh is not invoked by the local relevance module or Scratch Pad promotion because both are internal to Notes. GLAZE UI V1.0 remains the mandatory application design target for the new module and controls.

These statements describe source-level boundaries only; they do not claim complete application-wide acceptance with every current Platform System contract.

## Non-fabrication boundaries

The approved product direction includes additional modules, but this checkpoint intentionally withholds them when their authoritative data or behavior is not implemented:

- Recently Captured is not shown until capture-source provenance and actual capture state are connected.
- GoreeCloud Tasks and GoreeCloud Calendar modules are not shown until their authoritative capabilities are discoverable through GoreeCloud Mesh and the Notes consumer boundary is implemented.

GoreeCloud Notes does not create duplicate Tasks or Calendar stores for Knowledge Home.

## Draft-safety boundary

The current editor uses explicit conflict-safe Save. Opening a different in-tab application surface can therefore discard an unsaved editor component if it is unmounted without passing through the established navigation guard.

For this checkpoint, the Notes utility launcher opens Knowledge Home in a new browser tab with `noopener`. The active Notes tab and any local editor draft remain mounted. Knowledge Home can then return to the Notes workspace within its own tab.

This is a deliberate foundation behavior, not the final integrated navigation model. A later primary-home integration must participate directly in the established unsaved-draft navigation contract before it replaces this separate-tab boundary.

## GLAZE UI treatment

Knowledge Home uses the locally available GLAZE UI V1.0 semantic surface and interaction variables already present in GoreeCloud Notes. New Home content modules use solid content surfaces; glazed treatment is concentrated in transient top-level chrome. Covered Home controls, including Scratch Pad's durable-save action, use 48-pixel minimum targets, and the surface includes compact safe-area handling, reduced-motion behavior, reduced-transparency and no-backdrop-filter fallbacks, and forced-colors behavior.

This does not establish complete current GLAZE UI V1.0 conformance for GoreeCloud Notes. The broader application still requires canonical current-design-system reconciliation plus fresh exact-revision rendered, accessibility, resilience, layout, material, motion, interaction, performance, and representative-device acceptance before that claim is allowed.

## Validation contract

`frontend/scripts/validate-knowledge-home.mjs` is part of the normal frontend production build. It fails closed if the implemented module set, transparent deterministic Relevant Notes ranking, transient/local state boundaries, atomic Scratch Pad promotion contract, storage-aware cleanup and failure-preservation behavior, non-fabrication statements, route/draft-preservation hooks, solid content-surface requirement, 48-pixel covered target requirement, safe-area behavior, or required accessibility/resilience fallbacks disappear.

Exact pull-request validation evidence belongs in pull-request and canonical GoreeCloud project records, not as a self-referential current-head value in this repository file.

This source validator and CI evidence supplement TypeScript, lint, build, and integration validation. They are not substitutes for rendered browser or representative-device acceptance.

## Still open

The following remain outside this source checkpoint:

- direct item-level navigation from Home cards into the primary workspace;
- integration of Knowledge Home as the primary in-app Home destination under the unsaved-draft guard;
- provenance-backed Recently Captured;
- GoreeCloud Mesh-backed Tasks and Calendar modules;
- user-configurable background/canvas personalization;
- additional module sizing/layout options;
- personalized or intelligence-backed recommendation behavior beyond the current transparent deterministic local ranking;
- complete GLAZE UI V1.0 application-wide reconciliation and rendered acceptance;
- production deployment, publication, monitoring, recovery, migration, and Stable-release approval.
