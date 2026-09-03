# GoreeCloud Notes Knowledge Home

## Status

Knowledge Home is an active native source-development checkpoint on `feature/knowledge-home-foundation`. It is not a production deployment, Stable-release claim, or proof of complete current GLAZE UI V1.0 acceptance.

The surface is inspired by useful knowledge-home information architecture seen in note applications, including the user-supplied Evernote references, but its implementation, state model, styling, privacy boundaries, and interaction behavior are GoreeCloud-owned.

## Current foundation

The source implementation is exposed through the local `#knowledge-home` application route and reads the authenticated user's existing GoreeCloud Notes data through the established owner-scoped API.

Implemented modules are:

- Recent Notes, ordered by existing note update timestamps.
- Pinned Notes, derived from native `is_pinned` state.
- Scratch Pad, using session-scoped browser storage for transient capture with explicit promotion into a normal Note.
- Shortcuts, summarizing current Notes, notebooks, Archive, and Trash counts.
- Tags, derived from the authenticated user's existing tag collection.

The Home customizer supports module visibility, ordering, and the currently supported standard/wide size choice. These are presentation preferences stored locally in the browser under a user-specific key; they are not server-authoritative knowledge state and are not exported as Notes data.

## Scratch Pad boundary

Scratch Pad remains deliberately transient until the user chooses **Save as note**. Its working text is stored in `sessionStorage`, scoped to the active browser tab and authenticated user identifier, with a 4,000-character UI limit.

Saving creates one normal owner-scoped GoreeCloud Note through the existing authenticated and CSRF-protected Notes API. Initial title and document content are sent in the same note-creation request so promotion does not rely on an empty-note-then-patch sequence. The first non-empty Scratch Pad line supplies a bounded title and the complete captured text is converted through the native GoreeCloud document contract.

The durable create request completes before any transient cleanup is attempted. Knowledge Home clears the visible Scratch Pad only when this tab's `sessionStorage` confirms removal of its transient copy. If durable note creation fails, the captured text remains available and the failure is surfaced. If durable creation succeeds but transient cleanup fails, the new Note remains created, the captured text intentionally remains visible, and the UI warns that the transient copy could not be cleared so the user can retry **Clear**. Manual Clear follows the same storage-aware rule and does not hide text when transient removal fails.

A successfully created Note is immediately added to Knowledge Home's current-note state so Recent Notes and the current-note summary reflect it without requiring a reload.

Scratch Pad is not a second note database and does not become durable merely because text exists in the transient capture field.

## Platform-system boundary for Scratch Pad promotion

This increment reuses the existing owner-scoped Notes authority rather than introducing a new product or control plane. GoreeCloud Identity remains represented by the established authenticated account/session boundary; the existing CSRF-protected Notes write path remains the security boundary for the create operation; no new sharing, external transfer, attachment, or cross-application data flow is introduced. Durable Notes continue to use the application's existing portability, export, and recovery path rather than a separate Scratch Pad persistence model.

GoreeCloud Manager receives no new administrative operation in this increment. Privacy Shield and Wardveil Security responsibilities remain within the existing Notes data-flow and authenticated write controls. Everkeep continuity remains attached to normal Notes data. GoreeCloud Mesh is not invoked because Scratch Pad promotion is internal to Notes. Glaze UI applies to the new save/status controls and their adaptive/accessibility behavior.

These statements describe the source-level boundary of this increment; they do not claim complete application-wide conformance with every current Platform System contract.

## Non-fabrication boundaries

The approved product direction includes additional modules, but this checkpoint intentionally withholds them when their authoritative data or behavior is not implemented:

- Suggested or Relevant Notes are not shown until deterministic ranking or separately approved intelligence is implemented and validated.
- Recently Captured is not shown until capture-source provenance and actual capture state are connected.
- GoreeCloud Tasks and GoreeCloud Calendar modules are not shown until their authoritative capabilities are discoverable through GoreeCloud Mesh and the Notes consumer boundary is implemented.

GoreeCloud Notes does not create duplicate Tasks or Calendar stores for Knowledge Home.

## Draft-safety boundary

The current editor uses explicit conflict-safe Save. Opening a different in-tab application surface can therefore discard an unsaved editor component if it is unmounted without passing through the established navigation guard.

For this checkpoint, the Notes utility launcher opens Knowledge Home in a new browser tab with `noopener`. The active Notes tab and any local editor draft remain mounted. Knowledge Home can then return to the Notes workspace within its own tab.

This is a deliberate foundation behavior, not the final integrated navigation model. A later primary-home integration must participate directly in the established unsaved-draft navigation contract before it replaces this separate-tab boundary.

## GLAZE UI treatment

Knowledge Home uses the locally available Glaze semantic surface and interaction variables already present in GoreeCloud Notes. New Home content modules use solid content surfaces; glazed treatment is concentrated in transient top-level chrome. Covered Home controls, including Scratch Pad's durable-save action, use 48-pixel minimum targets, and the surface includes compact safe-area handling, reduced-motion behavior, reduced-transparency and no-backdrop-filter fallbacks, and forced-colors behavior.

This does not establish complete current GLAZE UI V1.0 conformance for GoreeCloud Notes. The broader application still requires canonical current-design-system reconciliation plus fresh exact-revision rendered, accessibility, resilience, layout, material, motion, interaction, performance, and representative-device acceptance before that claim is allowed.

## Validation contract

`frontend/scripts/validate-knowledge-home.mjs` is part of the normal frontend production build. It fails closed if the implemented module set, transient/local state boundaries, atomic Scratch Pad promotion contract, storage-aware cleanup and failure-preservation behavior, non-fabrication statements, route/draft-preservation hooks, solid content-surface requirement, 48-pixel covered target requirement, safe-area behavior, or required accessibility/resilience fallbacks disappear.

This source validator supplements TypeScript, lint, build, and integration validation. It is not a substitute for rendered browser or real-device acceptance.

## Still open

The following remain outside this source checkpoint:

- direct item-level navigation from Home cards into the primary workspace;
- integration of Knowledge Home as the primary in-app Home destination under the unsaved-draft guard;
- deterministic Suggested/Relevant Notes;
- provenance-backed Recently Captured;
- GoreeCloud Mesh-backed Tasks and Calendar modules;
- user-configurable background/canvas personalization;
- additional module sizing/layout options;
- complete GLAZE UI V1.0 application-wide reconciliation and rendered acceptance;
- production deployment, publication, monitoring, recovery, migration, and Stable-release approval.