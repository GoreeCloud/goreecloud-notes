# Browser capture intent presented-token bound

Status: Development

The process-local Browser capture replay guard now bounds presented opaque-token input before hashing it.

Issued capture intents still use 32 random bytes through `secrets.token_urlsafe(...)`. Consumption accepts only non-empty presented tokens up to 128 characters; longer malformed values enter the same generic `capture intent rejected` boundary as unknown, expired, replayed, or cross-owner tokens and are rejected before SHA-256 work.

Regression coverage proves an oversized rejected token does not consume or invalidate the rightful owner's valid outstanding intent and proves issued tokens fit inside the reviewed presentation bound.

## Privacy and authority boundary

The guard continues to retain only owner ID, opaque-token digest, and expiry. It stores no captured title, URL, selected text, note document, or page content.

This is an input-abuse hardening for the existing process-local Development primitive. It does not select or implement production one-time-intent persistence/coordination, enable the Browser capture write endpoint, authorize transport, complete Privacy Shield/Wardveil review, deploy the feature, or establish Stable qualification.
