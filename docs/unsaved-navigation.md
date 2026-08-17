# Unsaved Draft Navigation Protection

GoreeCloud Notes uses explicit Save for note content. Navigation must therefore never silently replace a local draft or stale conflict state.

## Scope

The browser root mounts `WorkspaceNavigationGuard` for the native Notes workspace. The guard protects context-changing actions when the current note is dirty, still saving, failed to save, or in optimistic-concurrency conflict.

Protected actions currently include:

- switching notes from the note list;
- Home, Notebooks, Tags, Archive, and Trash navigation;
- direct notebook and tag navigation from the sidebar;
- creating a new note from the primary and quick-capture actions;
- signing out; and
- Archive, Trash, and Restore actions that would leave the current editing context.

The guard also registers `beforeunload` protection for browser close, refresh, or other page-unload attempts while a draft is at risk.

## Glaze UI behavior

The in-app guard is a Glaze Overlay dialog rather than a browser `confirm()` prompt. It uses the locally vendored Glaze semantic tokens and provides:

- Cancel;
- Discard & continue, explicitly marked as destructive; and
- Save & continue, delegated to the existing application Save control.

The dialog keeps the background workspace inert while open, traps keyboard focus within its actions, supports Escape cancellation when a save is not in progress, restores focus after cancellation, uses practical Glaze target sizes, becomes a Compact bottom sheet below 600 CSS pixels, and includes reduced-motion, reduced-transparency, no-backdrop-filter, increased-contrast, and forced-colors behavior.

No analytics, remote UI runtime, remote font, CDN asset, or additional frontend package is introduced.

## Save and conflict boundary

`Save & continue` does not implement a second persistence path. It activates the existing Save button and waits for the existing save-state contract to resolve.

- If the existing save succeeds, the originally requested navigation is replayed exactly once.
- If the save fails, navigation stays blocked and the draft remains open.
- If optimistic concurrency reports a conflict, the guard does not overwrite the newer server version. The user must use the existing server-version reload path or explicitly discard the local draft before navigation.
- If saving does not resolve within the bounded wait, navigation remains blocked rather than guessing that persistence succeeded.

`Discard & continue` is the only path that intentionally allows navigation while local changes remain unsaved. Its destructive wording is deliberate.

## Implementation contract

This checkpoint intentionally avoids changing the established App persistence model. The guard observes stable semantic class hooks already emitted by the workspace (`save-state`, `save-button`, note cards, navigation controls, and context-changing editor actions) and intercepts navigation in the browser capture phase before React handles the original click.

`frontend/scripts/validate-navigation-guard.mjs` fails the production frontend build if required interaction hooks, dialog semantics, Glaze resilience behavior, browser-unload protection, or the local-only dependency boundary are removed.

A later App-state refactor may replace these DOM hooks with an explicit navigation-intent API, but it must preserve the same user-visible safety contract and cannot weaken optimistic-concurrency protection.

## Safety boundary

This is source-level browser behavior only. It does not authorize production deployment, hostname cutover, Memos modification or retirement, permanent deletion, merge, or Stable release. Real-device and target-browser acceptance remains part of the existing production-readiness gate.
