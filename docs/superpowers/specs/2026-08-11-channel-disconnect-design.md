# Channel Disconnect and Connect-Page Polish

**Date:** 2026-08-11
**Surface:** `/dashboard/settings` → Channels tab
**Builds on:** `docs/superpowers/specs/2026-08-11-connect-channels-redesign-design.md`

## Problem

The Channels page is connect-only. Grepping `backend/app/routes/app_settings.py` for
`disconnect` returns zero matches — no route, no UI, no way back. A tenant who connects the
wrong WhatsApp number, wants to stop read-only ad reporting, or is leaving Aira has no
self-service path.

Three smaller issues ship alongside it:

- The violet Zephyr was shrunk to a `compact` size to stop it inflating the Manual section's
  header band. It should be as prominent as the green one.
- The two section header gradients do not mirror each other. Embedded currently reads
  `from-emerald-50 via-white to-[#f4f0ff]` — it fades into *violet*, the Manual section's
  colour, which looks like a copy-paste mistake.
- The settings tab is labelled "Messaging Channels", but the tab also holds Meta Ads
  (reporting) and Razorpay (payments). Neither is messaging.

## The Asset-Claim Trap

`meta_asset_claims` (`backend/supabase/migrations/162_meta_asset_claims.sql`, extended by
`171_meta_asset_claim_whatsapp.sql`) records that a Meta asset belongs to exactly one tenant,
keyed `PRIMARY KEY (asset_type, asset_id)`. There is a `claim_meta_assets` RPC and **no
release path** — nothing in the codebase ever deletes a claim row.

This is invisible today because the conflict check is `claim.tenant_id <> p_tenant_id`, so a
tenant reconnecting their own assets succeeds. But a customer moving their WhatsApp number to
a different Aira workspace is permanently blocked and needs manual database intervention.
Shipping disconnect without a release path makes that worse: users would disconnect, expect to
be free, and still be locked.

## Decisions

From the design conversation:

- **Disconnect is available at two granularities.** A whole-connection "Disconnect Meta" tears
  down all four Meta channels; each channel row and manual card also has its own disconnect.
- **Full teardown**: unsubscribe webhooks at Meta, delete credentials, clear status and source.
- **Releasing the asset claim is opt-in**, a checkbox in the confirm dialog, default off.
  Unchecked, the tenant can reconnect at will but the asset stays reserved to them. Checked,
  the asset is freed for any other workspace to claim.

## Migration `172_release_meta_assets.sql`

```sql
CREATE OR REPLACE FUNCTION public.release_meta_assets(
  p_tenant_id uuid,
  p_assets jsonb
) RETURNS void
```

Deletes from `meta_asset_claims` where `(asset_type, asset_id)` matches an entry in `p_assets`
**and** `tenant_id = p_tenant_id`. That final predicate is the security property: a workspace
can never release another workspace's claim, even if it guesses the asset id. Validates
`p_assets` shape identically to `claim_meta_assets`, is `SECURITY DEFINER` with
`SET search_path = public, pg_temp`, and grants EXECUTE to `service_role` only.

## Route `POST /api/v1/settings/disconnect`

Gated by the existing `require_settings_manage` dependency. Request body:

```
{ "channel": "meta" | "whatsapp" | "instagram" | "facebook" | "meta_ads" | "telegram" | "razorpay",
  "release_assets": bool }
```

`"meta"` runs whatsapp, instagram, facebook and meta_ads in one call and reports each outcome.

| Channel | Remote call | Claims released (when opted in) | Keys deleted |
|---|---|---|---|
| whatsapp | `DELETE {waba_id}/subscribed_apps` | `whatsapp_business_account`, `whatsapp_phone_number` | `meta_access_token`, `meta_phone_number_id`, `meta_waba_id` |
| facebook | `DELETE {page_id}/subscribed_apps` (page token) | `facebook_page` | `facebook_access_token`, `facebook_page_id` |
| instagram | none — see below | `instagram_account` | `instagram_access_token`, `instagram_page_id`, `instagram_app_secret` |
| meta_ads | none | `ad_account` | `meta_ads_access_token`, `meta_ads_account_id`, `meta_ads_account_name`, `meta_ads_last_sync_at` |
| telegram | `deleteWebhook` | — | `telegram_bot_token`, `telegram_webhook_secret` |
| razorpay | none | — | `razorpay_key_id`, `razorpay_key_secret`, `razorpay_webhook_secret` |

Every channel additionally deletes `<channel>_status` and `<channel>_connection_source`, then
`invalidate_cache()` runs once and `record_audit_event(action="settings.channel_disconnected")`
records the channel and whether assets were released.

### Three rules that are wrong in the obvious implementation

1. **Instagram makes no Meta call.** Instagram messaging rides the *Facebook Page* webhook
   subscription. Calling `DELETE {page_id}/subscribed_apps` to disconnect Instagram would
   silently kill Messenger for a tenant who only asked to drop Instagram.

2. **`meta_app_secret` and `meta_webhook_verify_token` are shared** by WhatsApp, Instagram and
   Messenger — the Meta app secret verifies inbound signatures for all three. They are deleted
   only once no Meta channel has credentials left. Deleting them while another Meta channel is
   still connected breaks that channel's webhook signature verification.

3. **The `phone_numbers` row is deactivated, not deleted.** Unified signup upserts a row
   (`app_settings.py:1147`) that call and message history references. WhatsApp disconnect sets
   `status: "inactive"` and `paused_outbound: true` for the matching `meta_phone_number_id`.

### Failure handling

A remote unsubscribe that fails must not abort the local teardown — a tenant whose token is
already revoked at Meta still needs the local disconnect to complete. Remote failures are
logged and reported in the response as a per-channel `webhook_unsubscribed: false`, and the
UI surfaces that as "Disconnected locally — remove Aira in Meta Business Settings to stop
delivery." Claim release failures, by contrast, are surfaced as errors, since a silently
unreleased claim is exactly the trap this feature exists to close.

## UI

- **Embedded section header:** a `Disconnect` ghost button beside Reconnect, rendered only
  when at least one Meta channel is configured.
- **Channel status rows and manual cards:** a `⋯` overflow menu with a single Disconnect item,
  rendered only when that channel is configured.
- **Confirm dialog** (`DisconnectDialog.tsx`), stating exactly what stops:
  - the channels that will stop working, by name
  - that Aira's webhooks are unsubscribed at Meta
  - that stored tokens are deleted
  - an unchecked checkbox: *"Also release these assets so they can be connected to a different
    Aira workspace"*
  - Confirm is destructive-styled; Cancel is the default focus.
- WhatsApp's per-channel disconnect adds a line noting that Instagram and Messenger share the
  same Meta token and will need reconnecting if they were provisioned together.

## Polish

- `ZephyrCourier` loses the `compact` prop. Both section header bands become `relative`, and
  the illustration is positioned to overhang the band rather than setting its height, so the
  full-size art no longer leaves an empty strip.
- Header gradients mirror: embedded `from-emerald-50 via-white to-emerald-50/40`, manual
  `from-violet-50 via-white to-violet-50/40`.
- `frontend/app/dashboard/settings/page.tsx:425` — "Messaging Channels" becomes "Channels".
  The `?tab=channels` query value is already correct and does not change.

## Verification

- `pytest` covering: each channel's key deletion; the shared-key rule in both directions;
  Instagram making no remote call; release running only when opted in; release never touching
  another tenant's row; a failed remote unsubscribe still completing the local teardown.
- `npm run typecheck`, `npm run lint`, `npm test`.
- Rendered screenshots at 1440 and 768 of both sections and the confirm dialog.
- Migration 172 is **not** applied to the live Supabase project as part of implementation.
  That is a separate, explicitly authorised step.
