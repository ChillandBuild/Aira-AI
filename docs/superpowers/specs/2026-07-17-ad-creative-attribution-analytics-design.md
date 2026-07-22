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
- `meta_ad_id`, `meta_adset_id`, `meta_adset_name`, `meta_campaign_id`
- `creative_label` (e.g. `AT-V01`, or a sweet's name/SKU — generic, not video-specific)
- `prefilled_message_code`

`meta_adset_id`/`meta_adset_name` are stored so the dashboard can filter/group at ad-set level (all confirmed present in the live Insights response on 2026-07-23).

**`ad_insights_daily`** — one row per creative per day, populated by a scheduled sync job:
- `ad_creative_id`, `date`, `clicks`, `inline_link_clicks`, `spend`

Field note: Meta's Insights API returns two click metrics — `clicks` (all ad engagement, broader than intended) and `inline_link_clicks` (actual taps on the ad's CTA/link). Store both, but use `inline_link_clicks` as the "Clicks" value throughout the dashboard/CSV and in the derived "clicked/no-message" formula — it's the precise measure of people who tapped through toward WhatsApp, not general ad engagement.

**`leads`** — new column:
- `attributed_ad_creative_id` (nullable FK to `ad_creatives`)

## Attribution logic (extends existing webhook parsing, doesn't replace it)

At `backend/app/routes/webhook.py:437-459` (already parses Meta's `referral` object for campaign-level attribution), add creative-level matching in priority order:

1. **Referral ad_id** (`referral.source_id`) → match to `ad_creatives.meta_ad_id`. Primary signal; reliable because the ad remains native Click-to-WhatsApp.
2. **Message text code** (e.g. `AT-V01`) → match to `ad_creatives.prefilled_message_code`. Fallback when referral is absent.

No third "match to most recent click" fallback — deliberately dropped. Without stored individual click identities, a recency-based guess risks silently misattributing a lead to the wrong creative when two people click close together. Both remaining signals are unambiguous.

## Click counts ("clicked but never messaged")

Meta does not emit a webhook event for a click that never becomes a message — this is a hard limitation of native Click-to-WhatsApp ads, not a gap in this design. The click count per creative comes from **Meta's Ads Insights API** (`level=ad`), pulled by a scheduled backend job (new: `backend/app/services/meta_ads_insights_sync.py`) and stored in `ad_insights_daily`.

Verified two ways, not just from documentation: (1) against current Meta docs — the Ads Insights API supports `level=ad` queries returning `clicks`/`spend` per ad, using `ads_read`/`business_management` scopes, with a Business Manager **System User token** as the recommended type for unattended server-side access (no short expiry, unlike a regular OAuth user token). Sources: [Ads Insights API](https://developers.facebook.com/documentation/ads-commerce/marketing-api/insights), [Click to WhatsApp ads](https://developers.facebook.com/documentation/ads-commerce/marketing-api/ad-creative/messaging-ads/click-to-whatsapp/). (2) Live-tested on 2026-07-21 against the real "Astro Tamil" ad account (`act_1910086849857231`) with a System User token scoped to `ads_read` — confirmed 11 distinct ads returned individual `clicks`/`inline_link_clicks`/`spend` values correctly at `level=ad`.

### Per-tenant credentials

There is currently no Marketing/Ads Insights API integration anywhere in this codebase — only WhatsApp Cloud API (messaging scopes). This is new integration work, not an extension of `meta_cloud.py`.

Aira AI's existing pattern for Meta-family credentials (`meta_access_token`, `instagram_access_token`, `facebook_access_token` in `onboarding.py`/`app_settings`) is manual paste-in, not an OAuth consent flow — and that pattern is actually the *correct* fit here too: a System User token (what we want, since it doesn't expire) can only be generated manually in Meta Business Manager, never via an OAuth redirect. A real "Login with Facebook" flow would both require additional Meta App Review for ads permissions and yield a worse (expiring, ~60-day) token than what tenants would paste in manually. So: two new per-tenant settings fields, `meta_ads_access_token` and `meta_ads_account_id`, following the exact existing settings-paste pattern — no OAuth flow, no token refresh cron. The sync job iterates over tenants that have these fields populated.

Per creative, "clicked but no message" is a **derived dashboard number**, not an individual lead status:

```
clicked_no_message = ad_insights_daily.inline_link_clicks (for the period) − count(leads where attributed_ad_creative_id = X)
```

This number can be occasionally imprecise at date-range edges (Meta's click count and Aira's message count are independently sourced — e.g. someone clicks on the last day of a range and messages the next day), and self-corrects over a campaign's full lifetime. Not a defect to fix; an expected characteristic of combining two independent data sources.

## Lead status ladder (revised from the original 6-status plan)

Because individual click identity isn't tracked (no redirect/click-capture layer), a lead record can't carry a `clicked` or `whatsapp_click_no_message` status — those aren't identified leads, they're an aggregate count. The per-lead ladder is:

```
message_received → qualified → hot_lead → converted
```

`clicked` and `whatsapp_click_no_message` exist only as aggregate dashboard metrics per creative (see above), never as a value on an individual lead row.

## Creative auto-import (zero-config)

Creatives are **not** manually registered. Meta's Insights API (`level=ad`) returns `ad_id`, `ad_name`, `adset_name`, `campaign_name`, and `campaign_id` for every ad alongside the metrics — verified live on 2026-07-21 (returned names like "Clarity", "Baby", "Office"). The sync job therefore **upserts `ad_creatives` rows directly from the Insights response**:

- `meta_ad_id` ← `ad_id`
- `meta_adset_id`/`meta_adset_name` ← `adset_id`/`adset_name`
- `meta_campaign_id` ← `campaign_id`
- `creative_label` ← `ad_name` (tenant can rename later; sync never overwrites a tenant-edited label)
- `campaign_id` ← resolved to the existing `ad_campaigns` row via `growth.get_or_create_campaign()` keyed on Meta's `campaign_id`/`campaign_name`, keeping one source of truth for campaigns

Because the webhook's `referral.source_id` is that same `ad_id`, attribution matches an incoming message to an auto-imported creative with no setup step. A creative appears in the dashboard once it has spend/impressions (i.e., once Meta reports insights for it). Consequence to accept: a brand-new ad with zero delivery won't show until its first insights row syncs — expected, not a defect.

## Inbound Analytics — "Ad Performance" sub-tab (chosen layout)

The inbound-leads page gains a **two-tab switcher** at the top:

- **Leads** — the existing lead table (`InboundLeadsClient`), completely unchanged.
- **Ad Performance** — new. A per-creative comparison table, one row per `ad_creative`, grouped/filterable by campaign.

Rationale for sub-tabs over stacked/expandable: keeps the existing lead list untouched (lowest risk), gives the wide metric table its own full-width surface, and matches the tab pattern already used on `dashboard/analytics/page.tsx`. The performance table is aggregate per-creative data, a different granularity from the individual-lead list, so separating them by tab avoids mixing two data shapes on one scroll.

**Ad Performance table columns** (per creative), grouped for readability, horizontal scroll on narrow screens (reusing the existing `overflow-x-auto` table pattern):
- *Volume*: Creative, Clicks (`inline_link_clicks`), Messages (attributed leads), Clicked/no-message (derived)
- *Quality*: Qualified, Hot leads, Sales
- *Money*: Spend, **Cost per click (CPC = spend ÷ `inline_link_clicks`)**, Cost per WhatsApp conversation, Cost per qualified lead, Cost per hot lead, Sales revenue, ROAS

CPC is computed as `spend ÷ inline_link_clicks` (not Meta's raw `cpc` field, which divides by all clicks) so it stays consistent with the "Clicks" column shown everywhere else.

**Three-level filter (cascading)**: Campaign → Ad set → Creative. Selecting a campaign narrows the ad-set dropdown to that campaign's sets; selecting an ad set narrows the creative dropdown. Any level can be left at "All". Ad-set and creative options come from `ad_creatives` (`meta_adset_name`, `creative_label`). Campaign + date range stay shared with the Leads tab (same filter state); ad-set/creative filters are specific to the Ad Performance tab.

**Button styling**: all controls (tab pills, filter dropdowns, Download CSV, Refresh) follow the existing polished component styles already in `InboundLeadsClient.tsx` — `rounded-xl`/`rounded-full`, `shadow-sm`, violet hover states, `lucide-react` icons — so the new tab is visually consistent with (and as refined as) the current page. No plain/unstyled buttons.

**CSV export**: Ad Performance has its own CSV export (new endpoint) reflecting the current campaign/ad-set/creative/date filter; Leads keeps its existing `/inbound-leads/export`.

**Frontend structure**: extract the tab shell into `inbound-leads/page.tsx`'s client; the current body becomes a `LeadsTab` and the new view an `AdPerformanceTab` component in its own file (the existing `InboundLeadsClient.tsx` is already 706 lines — the new view goes in a sibling file, not appended to it).

## Placement summary

- **Frontend**: `frontend/app/dashboard/inbound-leads/` — add tab switcher + new `AdPerformanceTab` component (sibling file). Existing `InboundLeadsClient` lead table unchanged.
- **Backend**: new endpoints in `backend/app/routes/inbound_leads.py` — `GET /inbound-leads/ad-performance` (per-creative aggregation, accepts `campaign_id`/`adset_id`/`ad_creative_id`/`date_from`/`date_to` filters) and `GET /inbound-leads/ad-performance/export` (CSV, following the `csv.DictWriter` + `Response(media_type="text/csv")` pattern in `backend/app/routes/leads.py:474`). A supporting `GET /inbound-leads/ad-filters` returns the campaign→adset→creative option tree for the cascading dropdowns. Aggregation logic in a new `growth.py` function joining `ad_creatives` × `ad_insights_daily` × `leads`.
- **Schema**: one new Supabase migration adding `ad_creatives`, `ad_insights_daily`, `leads.attributed_ad_creative_id`, and the two new `app_settings` fields (`meta_ads_access_token`, `meta_ads_account_id`), numbered after the latest existing migration.
- **Sync job**: new scheduled service (`backend/app/services/meta_ads_insights_sync.py`) that, per tenant with `meta_ads_access_token`/`meta_ads_account_id` configured, pulls `level=ad` insights, upserts `ad_creatives` (auto-import above), and writes daily rows into `ad_insights_daily`.

## Explicitly out of scope for this build (Phase 2)

- **Meta Conversions API** — sending qualified-lead / hot-lead / converted / purchase events back to Meta for ad optimization. Deferred; can bolt on later without changing this design, since it only adds an outbound event on existing status transitions.

## Explicitly dropped from the original plan

- **Own redirect/tracking domain for individual click capture.** Considered and rejected: it requires switching ads from native Click-to-WhatsApp destination to a Website/Traffic destination, which (a) removes Meta's automatic `referral` object from inbound messages, forcing full reliance on the message-text code, and (b) changes what Meta optimizes ad delivery for (link clicks vs. message completion). Meta's own Ads Insights API already gives accurate per-ad click counts without either cost.
- **"Match to most recent click" attribution fallback** — see Attribution logic above.
