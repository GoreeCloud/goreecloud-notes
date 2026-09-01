# Browser capture intent replay guard

Status: Development

GoreeCloud Notes now has a bounded process-local one-time intent guard for the future GoreeCloud Browser capture write path.

The guard issues cryptographically random opaque tokens, stores only a SHA-256 token digest plus owner ID and expiry, enforces a five-minute default / fifteen-minute maximum lifetime, caps active intent state, and removes a token only after a successful same-owner consumption. Replays, unknown tokens, expired tokens, and cross-owner attempts share one rejection boundary. A cross-owner attempt cannot consume the rightful owner's valid intent.

No captured title, URL, selected text, note document, or page content is stored in the intent guard. A future transport must carry the opaque intent through an approved authenticated request mechanism rather than captured content in a URL.

## Remaining production gate

This guard is deliberately in-process Development state. Before a live write endpoint can be approved, GoreeCloud must select and validate one-time intent persistence or coordination appropriate to the deployed topology so multi-process/restart behavior cannot reopen replay windows.

The service write endpoint, Browser adapter, production authorization, Privacy Shield/Wardveil acceptance, deployment, and Stable qualification remain false/open.
