# Unified Meta Business Onboarding

## Goal

Give an Aira client one Meta connection journey for WhatsApp, Facebook Messenger, Instagram Direct, and optional read-only Meta Ads analytics.

## Chosen approach

Use the Meta Embedded Signup configuration `2026693308738446` in one popup. The popup code is exchanged exactly once by the backend. The backend keeps the access token private, stages the result, and returns only safe Page and ad-account names/IDs for the client to choose. The final request validates those choices against Meta again and saves WhatsApp, Page/Messenger, linked Instagram, and the optional ad account together.

## Scope

- WhatsApp is required for the unified route.
- A Facebook Page is required; its linked Instagram account is connected when present.
- An ad account is optional and used only for Aira's `ads_read` analytics.
- Meta Catalog is deliberately excluded. Aira's existing Catalog page is an internal product catalog, not a Meta Commerce catalog.
- Existing manual and legacy connection endpoints remain available.

## Safety

- Never send Meta access tokens to the browser.
- Verify every selected asset was returned by Meta for the current signup session.
- Claim Page, Instagram, WhatsApp business account, WhatsApp phone number, and ad account atomically so an asset cannot be connected to two Aira workspaces.
- Do not remove a previously connected asset when the client simply leaves an optional asset unselected.

## Testing

- Backend tests cover safe staged discovery, rejection of ungranted assets, and saving WhatsApp plus explicitly selected assets.
- Frontend typecheck and lint verify the settings UI.
- A manual test with the owner's Meta account confirms Meta's production response shape before client rollout.
