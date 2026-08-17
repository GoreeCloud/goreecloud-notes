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

Inline `noteLink` marks inside the editable document remain document semantics rather than separate browser anchors in this checkpoint. Direct click-to-open behavior for the inline mark itself can be evaluated separately without changing the portable relationship contract.

## Glaze UI and accessibility

The relationship panel uses GoreeCloud Glaze semantic variables for text, muted text, lines, accent treatment, and surfaces. It includes:

- visible keyboard focus;
- Glaze minimum pointer targets for Connected-note buttons;
- comfortable targets on coarse-pointer devices;
- compact and single-column responsive layouts;
- forced-colors behavior;
- reduced-transparency fallback; and
- status messages for link insertion and relationship refresh outcomes.

## Validation

The implementation is gated by:

1. server document-contract unit tests for canonical UUID links and invalid mark rejection;
2. Alembic upgrade/check/downgrade/upgrade validation;
3. live Compose validation proving same-owner outgoing links and backlinks;
4. live cross-account opacity validation;
5. live proof that another account's UUID cannot become a resolved relationship row;
6. frontend lint, TypeScript build, Glaze foundation validation, bundle-budget validation, and the navigation-guard source contract verifying both outgoing and backlink navigation; and
7. existing native export/re-import and backup/restore gates, which continue to exercise the authoritative document and PostgreSQL database respectively.

## Deliberate boundaries

This checkpoint does not add public URLs, remote sharing, web-link previews, cross-account linking, automatic title mutation, direct inline-mark browser navigation, or permanent-deletion semantics. Those features require separate privacy, security, migration, and usability decisions.
