# Glaze UI source snapshot

GoreeCloud Notes targets **Glaze UI 1.0.0**.

The reusable web foundation in this directory is vendored from the canonical GoreeCloud design-system repository so Notes does not depend on a remote stylesheet, third-party UI CDN, package registry at runtime, analytics service, remote font, or remote icon provider.

- Canonical repository: `GoreeCloud/glaze-ui`
- Glaze UI version: `1.0.0`
- Canonical revision: `d6e446fd8ef251259d16368d50aad90d9287a774`
- Vendored files:
  - `css/glaze.css` -> `frontend/src/glaze/glaze.css`
  - `css/glaze.accessibility.css` -> `frontend/src/glaze/glaze.accessibility.css`
- Canonical license: MIT
- Notes application license: AGPL-3.0-only

The vendored files remain byte-for-byte copies of the canonical revision. Product-specific Notes composition, component mapping, responsive behavior, and additional accessibility safeguards live in `frontend/src/glaze-foundation.css` rather than modifying the canonical snapshot.

When upgrading Glaze UI, update this record, replace both vendored files from one exact canonical revision, run `npm run check:glaze`, and perform light/dark Compact and Expanded visual acceptance before treating the upgrade as stable-release evidence.
