# Ad-Creative Attribution & Analytics — Design

## Purpose

Today Aira AI can tell that a lead came from an ad campaign (`ad_campaigns`), but not *which specific ad creative* (video, poster, product variant, etc.) within that campaign drove the message. When a tenant runs several creatives under one campaign — e.g. four videos under "Astro Tamil," or one ad per sweet under a "Sweets" campaign — they need per-creative visibility: clicks, messages, and the funnel from message through to sale, so they can tell which creative is actually working.

This is a generic, reusable feature for any tenant/campaign, not a one-off for a specific campaign.

## Ad setup (no change to how ads are built in Meta)

- Native Meta **Click-to-WhatsApp** ads, unchanged.
- One ad per creative (one video, one poster, one product variant — whatever the tenant is comparing).
- Same WhatsApp Business number across all ads in a campaign.
- Each ad gets a unique prefilled message code embedded in its CTA text (e.g. `Hi, I am interested in Astro Tamil. Code: AT-V01`).

No redirect domain, no custom tracking link, no change to Meta ad destination/objective. This preserves Meta's native ad-delivery optimization for message completion and keeps Meta's `referral` payload intact on inbound messages.

## Data model (new)

**`ad_creatives`** — one row per ad/creative:
- `id`, `tenant_id`, `campaign_id` (FK `ad_campaigns`)
- `creative_label` (e.g. `AT-V01`, or a sweet's name/SKU — generic, not video-specific)
- `meta_ad_id`
- `prefilled_message_code`

**`ad_insights_daily`** — one row per creative per day, populated by a scheduled sync job:
- `ad_creative_id`, `date`, `clicks`, `spend`

**`leads`** — new column:
- `attributed_ad_creative_id` (nullable FK to `ad_creatives`)

## Attribution logic (extends existing webhook parsing, doesn't replace it)

At `backend/app/routes/webhook.py:437-459` (already parses Meta's `referral` object for campaign-level attribution), add creative-level matching in priority order:

1. **Referral ad_id** (`referral.source_id`) → match to `ad_creatives.meta_ad_id`. Primary signal; reliable because the ad remains native Click-to-WhatsApp.
2. **Message text code** (e.g. `AT-V01`) → match to `ad_creatives.prefilled_message_code`. Fallback when referral is absent.

No third "match to most recent click" fallback — deliberately dropped. Without stored individual click identities, a recency-based guess risks silently misattributing a lead to the wrong creative when two people click close together. Both remaining signals are unambiguous.

## Click counts ("clicked but never messaged")

Meta does not emit a webhook event for a click that never becomes a message — this is a hard limitation of native Click-to-WhatsApp ads, not a gap in this design. The click count per creative comes from **Meta's Ads Insights API** (`level=ad`), pulled by a scheduled backend job (new: `backend/app/services/meta_ads_insights_sync.py`) and stored in `ad_insights_daily`.

Verified against current Meta documentation (not assumed from training knowledge): the Ads Insights API supports `level=ad` queries returning `clicks`/`spend` per ad, using `ads_read`/`business_management` scopes, and Meta's own recommended token type for unattended server-side access is a Business Manager **System User token** (no short expiry, unlike a regular OAuth user token). Sources: [Ads Insights API](https://developers.facebook.com/documentation/ads-commerce/marketing-api/insights), [Click to WhatsApp ads](https://developers.facebook.com/documentation/ads-commerce/marketing-api/ad-creative/messaging-ads/click-to-whatsapp/).

### Per-tenant credentials

There is currently no Marketing/Ads Insights API integration anywhere in this codebase — only WhatsApp Cloud API (messaging scopes). This is new integration work, not an extension of `meta_cloud.py`.

Aira AI's existing pattern for Meta-family credentials (`meta_access_token`, `instagram_access_token`, `facebook_access_token` in `onboarding.py`/`app_settings`) is manual paste-in, not an OAuth consent flow — and that pattern is actually the *correct* fit here too: a System User token (what we want, since it doesn't expire) can only be generated manually in Meta Business Manager, never via an OAuth redirect. A real "Login with Facebook" flow would both require additional Meta App Review for ads permissions and yield a worse (expiring, ~60-day) token than what tenants would paste in manually. So: two new per-tenant settings fields, `meta_ads_access_token` and `meta_ads_account_id`, following the exact existing settings-paste pattern — no OAuth flow, no token refresh cron. The sync job iterates over tenants that have these fields populated.

Per creative, "clicked but no message" is a **derived dashboard number**, not an individual lead status:

```
clicked_no_message = ad_insights_daily.clicks (for the period) − count(leads where attributed_ad_creative_id = X)
```

This number can be occasionally imprecise at date-range edges (Meta's click count and Aira's message count are independently sourced — e.g. someone clicks on the last day of a range and messages the next day), and self-corrects over a campaign's full lifetime. Not a defect to fix; an expected characteristic of combining two independent data sources.

## Lead status ladder (revised from the original 6-status plan)

Because individual click identity isn't tracked (no redirect/click-capture layer), a lead record can't carry a `clicked` or `whatsapp_click_no_message` status — those aren't identified leads, they're an aggregate count. The per-lead ladder is:

```
message_received → qualified → hot_lead → converted
```

`clicked` and `whatsapp_click_no_message` exist only as aggregate dashboard metrics per creative (see above), never as a value on an individual lead row.

## Placement

- **Frontend**: new Analytics section inside `frontend/app/dashboard/inbound-leads/` (not the top-level `dashboard/analytics/` page — inbound-leads already models ad-attributed vs. organic leads via `ad_campaign_id`, making it the closer conceptual home). Campaign filter → per-creative breakdown table (Clicks, Messages, Clicked/no-message, Qualified, Hot leads, Sales, Spend, Cost per click, Cost per WhatsApp conversation, Cost per qualified lead, Cost per hot lead, Sales revenue, ROAS) → CSV export button.
- **Backend**: new endpoints in `backend/app/routes/inbound_leads.py` (which already has the `ad_campaign_id`-based filtering plumbing), including a CSV export endpoint following the proven `csv.DictWriter` + `Response(media_type="text/csv")` pattern already used in `backend/app/routes/leads.py:474`.
- **Schema**: one new Supabase migration adding `ad_creatives`, `ad_insights_daily`, `leads.attributed_ad_creative_id`, and the two new `app_settings` fields (`meta_ads_access_token`, `meta_ads_account_id`), numbered after the latest existing migration.
- **Sync job**: new scheduled service (`backend/app/services/meta_ads_insights_sync.py`) pulling Meta Ads Insights data daily per `meta_ad_id`, for each tenant with `meta_ads_access_token`/`meta_ads_account_id` configured.

## Explicitly out of scope for this build (Phase 2)

- **Meta Conversions API** — sending qualified-lead / hot-lead / converted / purchase events back to Meta for ad optimization. Deferred; can bolt on later without changing this design, since it only adds an outbound event on existing status transitions.

## Explicitly dropped from the original plan

- **Own redirect/tracking domain for individual click capture.** Considered and rejected: it requires switching ads from native Click-to-WhatsApp destination to a Website/Traffic destination, which (a) removes Meta's automatic `referral` object from inbound messages, forcing full reliance on the message-text code, and (b) changes what Meta optimizes ad delivery for (link clicks vs. message completion). Meta's own Ads Insights API already gives accurate per-ad click counts without either cost.
- **"Match to most recent click" attribution fallback** — see Attribution logic above.
