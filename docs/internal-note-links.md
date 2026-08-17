# GoreeCloud Notes — Internal Note Links and Backlinks

## Purpose

GoreeCloud Notes supports private internal note links as part of the native `goreecloud.blocks` document contract. The feature is designed so knowledge relationships remain portable, owner-isolated, recoverable, and independent from the rich-text editor implementation.

## Source of truth

The authoritative relationship is the `noteLink` text mark stored in a note document:

```json
{
  "type": "text",
  "text": "Related design decision",
  "marks": [
    {
      "type": "noteLink",
      "note_id": "00000000-0000-4000-8000-000000000000"
    }
  ]
}
```

The mark accepts only a canonical UUID reference. Generic external-link attributes, URLs, scripts, and arbitrary mark metadata are not part of this contract.

Because the relationship is embedded in the application-owned document, native full-library export and native re-import preserve link semantics without a separate portable relationship format.

## Derived PostgreSQL index

`note_links` is a derived lookup table used only for resolved outgoing-link and backlink queries. It is not independently editable application data.

Migration-owned PostgreSQL trigger logic refreshes the index whenever note document content is inserted or updated. It also rebuilds incoming references when a target note is inserted, which makes the index deterministic even when a native re-import restores a source note before its target.

The database uses same-owner composite foreign keys for both source and target notes. A link UUID that does not resolve to a note owned by the same account stays in the portable document but is omitted from the relationship index. This preserves unresolved references without exposing cross-account note metadata.

## API boundary

`GET /api/v1/notes/{note_id}/links` requires the authenticated account to own the requested note and returns only minimal relationship metadata:

- note ID;
- title;
- lifecycle state;
- pinned state; and
- updated timestamp.

The query repeats the owner predicate on relationship and note rows as defense in depth. Another account receives the same opaque not-found response used by other private workspace objects.

## Editor behavior

The rich editor implements `noteLink` as a local TipTap mark using the already-present editor core. No new package, remote script, analytics service, or external link resolver is introduced.

The Glaze UI toolbar can:

- choose an owned normal or archived note;
- link the current text selection;
- insert the target title as linked text when the selection is empty;
- remove a link mark from the current selection; and
- refresh resolved outgoing links and backlinks.

Code blocks refuse internal-link editing because the server document contract intentionally disallows inline marks inside code blocks.

## Connected-note navigation

Resolved outgoing links and backlinks in the **Connected notes** panel are navigation buttons. The button carries only the resolved same-owner note ID from the authenticated relationship response.

The App owns the navigation state transition. When a resolved relationship is opened, it:

1. resolves the target through the existing authenticated `GET /api/v1/notes/{note_id}` boundary;
2. selects the canonical lifecycle collection for the target — Home for normal notes, Archive for archived notes, and Trash for trashed notes;
3. reloads that owner-scoped collection;
4. clears the previous search/filter context so the target remains visible in the note list; and
5. opens the target through the existing `openNote()` and relation-loading path.

This avoids a second note-loading or persistence model. The relationship panel does not navigate by title, URL, DOM search, or cross-account metadata.

Every Connected-note navigation button uses the `note-link-open` guard hook. If the current note is dirty, still saving, failed to save, or in optimistic-concurrency conflict, `WorkspaceNavigationGuard` intercepts the button before the App navigation callback runs. Save & continue reuses the existing Save action; Discard & continue is the only intentional local-draft-loss path; conflicts remain fail-closed.

## Inline note-link navigation

The same portable `noteLink` mark now exposes a local navigation affordance inside the editable note body. It remains a `span` carrying only `data-note-id`; it does not become an `href`, route string, external URL, or browser location change.

A primary unmodified pointer click on the inline mark opens the linked note through the same App-owned `onOpenNote` callback used by the Connected notes panel. Modified pointer clicks remain available to normal editor/browser selection behavior instead of introducing a second navigation mode.

The inline mark also exposes `role="link"`, keyboard focus, and Enter activation. Enter synthesizes the same local click event rather than calling the App directly, which means dirty, saving, failed-save, and conflict states still pass through `WorkspaceNavigationGuard` before navigation can occur.

Before invoking the App, the editor verifies that the mark contains a canonical UUID supported by the current document contract and refuses self-navigation. Malformed or self-referential inline targets fail closed with a local status message. The server remains authoritative: the App subsequently resolves the target through the authenticated owner-scoped note API before opening it.

During unrelated busy operations the inline link receives `aria-disabled="true"`, the editor refuses navigation, and the root navigation guard ignores the disabled affordance. A save already in progress remains eligible for guard interception so Save & continue can wait for the existing persistence operation to resolve.

This behavior changes only the browser interaction surface. The stored `goreecloud.blocks` document, PostgreSQL `note_links` index, owner-isolation model, export format, re-import semantics, and backend API remain unchanged.

## Glaze UI and accessibility

The relationship panel and inline note-link affordance use GoreeCloud Glaze semantic variables for text, muted text, lines, accent treatment, and surfaces. They include:

- visible keyboard focus for Connected-note buttons and inline links;
- Glaze minimum pointer targets for Connected-note buttons;
- comfortable Connected-note targets and additional inline padding on coarse-pointer devices;
- compact and single-column responsive layouts;
- forced-colors behavior;
- reduced-transparency fallback;
- explicit disabled-state treatment for temporarily unavailable inline navigation; and
- status messages for link insertion, invalid inline targets, navigation availability, and relationship refresh outcomes.

## Validation

The implementation is gated by:

1. server document-contract unit tests for canonical UUID links and invalid mark rejection;
2. Alembic upgrade/check/downgrade/upgrade validation;
3. live Compose validation proving same-owner outgoing links and backlinks;
4. live cross-account opacity validation;
5. live proof that another account's UUID cannot become a resolved relationship row;
6. frontend lint, TypeScript build, Glaze foundation validation, bundle-budget validation, and the navigation-guard source contract verifying outgoing/backlink navigation plus inline pointer/keyboard activation, UUID/self validation, `aria-disabled` handling, and guarded replay; and
7. existing native export/re-import and backup/restore gates, which continue to exercise the authoritative document and PostgreSQL database respectively.

## Deliberate boundaries

This checkpoint does not add public URLs, remote sharing, web-link previews, cross-account linking, automatic title mutation, generic external-link browser routing, or permanent-deletion semantics. Those features require separate privacy, security, migration, and usability decisions.
