# Glaze UI conformance — GoreeCloud Notes

## Status

GoreeCloud Notes targets **Glaze UI 1.0.0** from canonical revision `d6e446fd8ef251259d16368d50aad90d9287a774` of `GoreeCloud/glaze-ui`.

This document records source-level conformance. It does not replace real-device visual acceptance and does not grant production approval.

## Adoption model

Notes vendors the canonical Glaze UI 1.0 web foundation locally under `frontend/src/glaze/`. The snapshot is deliberately kept separate from Notes-specific styling:

- `frontend/src/glaze/glaze.css` — canonical semantic tokens and reusable web primitives.
- `frontend/src/glaze/glaze.accessibility.css` — canonical resilience and accessibility fallbacks.
- `frontend/src/glaze/SOURCE.md` — exact version and revision provenance.
- `frontend/src/glaze-foundation.css` — Notes-specific semantic mapping and product composition.

The browser never needs a remote Glaze stylesheet, remote font, remote icon set, analytics service, advertising technology, or third-party UI CDN.

## Surface hierarchy

Notes intentionally maps the Glaze UI surface hierarchy as follows:

- **Canvas** — the atmospheric application background.
- **Glaze** — the primary desktop application shell and compact utility dock.
- **Solid** — reading/editor panes where clarity is more important than translucency.
- **Raised** — note cards, quick capture, organizational controls, attachment panels, and security controls that need local separation.
- **Overlay** — the fixed application utility dock because it must remain clearly separated from workspace content.

Translucency is not required everywhere. Solid fallbacks are retained for unsupported blur, reduced-transparency preferences, increased contrast, and forced-colors environments.

## Appearance behavior

The application supports System, Light, and Dark appearance preferences.

The preference is intentionally local to the browser and stored only in `localStorage` under `goreecloud.notes.appearance` when the user chooses Light or Dark. System mode removes the explicit theme override and follows the operating-system preference through CSS. Failure or denial of browser storage falls back safely to System mode.

No appearance preference is sent to the GoreeCloud Notes backend, synchronized to the account, or exposed to a third party.

## Adaptive layout

The Notes Glaze layer records and validates the Glaze UI 1.0 adaptive ranges:

- Compact: through 599 px.
- Medium: 600–1023 px.
- Expanded: 1024–1439 px.
- Wide: 1440 px and above.

The application retains its Notes-specific three-pane knowledge-workspace personality at larger widths. At smaller widths it changes navigation visibility, workspace composition, editor/list proportions, utility placement, and target sizing instead of treating the desktop composition as a fixed canvas.

## Interaction and accessibility

The source contract includes:

- visible `:focus-visible` treatment for links, buttons, inputs, selects, textareas, and editable rich-text content;
- practical 44 px targets for high-frequency controls and coarse-pointer environments;
- hover elevation only where real hover/fine-pointer capability exists;
- pressed-state feedback through the shared Glaze primitive contract;
- reduced-motion handling that removes nonessential motion;
- reduced-transparency and no-backdrop-filter fallbacks using solid surfaces;
- increased-contrast strengthening;
- forced-colors behavior that removes decorative depth and preserves selected/active state visibility;
- semantic success, warning, error, and destructive colors through shared Glaze tokens;
- locally rendered controls with no external icon/font dependency introduced by Glaze UI.

## Application-level conformance test

`frontend/scripts/validate-glaze-foundation.mjs` runs before every production frontend build. It verifies:

- the exact recorded Glaze UI version and canonical revision;
- the expected canonical semantic-token, surface, motion, adaptive, and accessibility contracts;
- load order: canonical Glaze first, product styles next, Notes Glaze mapping last;
- local System/Light/Dark appearance behavior;
- the Compact/Medium/Expanded/Wide range contract;
- reduced-transparency, increased-contrast, forced-colors, reduced-motion, and no-backdrop-filter fallbacks;
- absence of remote CSS/font dependencies in the vendored Glaze foundation;
- the presence of the shared utility/appearance surface.

## Stable-release visual acceptance still required

Before a stable release, manually review representative Compact and Expanded layouts in both Light and Dark appearances on supported target browsers/devices. The acceptance review must confirm that Notes remains readable, coherent, ergonomic, performant, and recognizably Glaze UI while preserving its Evernote-class knowledge-workspace role.

Any material Glaze UI requirement that cannot be met in production must be documented as an explicit exception with its reason, user-visible impact, approved alternative, and future review condition. No such production exception is authorized by this source checkpoint.
