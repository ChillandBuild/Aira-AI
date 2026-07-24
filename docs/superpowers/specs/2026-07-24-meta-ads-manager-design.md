# Meta Ads Manager (In-Dashboard) — Design

## Purpose

Aira's clients today either run Meta ads themselves (most are first-time advertisers — a
cafe owner with 100 WhatsApp contacts, not a marketer) or don't run ads at all because
Meta Ads Manager is too intimidating for someone who's never touched Meta Business Suite.
This build puts a simplified campaign creator *and* a full performance/analytics view
inside Aira's own dashboard, so a client never has to leave Aira or understand Meta's own
UI to run WhatsApp-lead-generating ads.

This is additive to, and reuses, the existing Ad-Creative Attribution & Analytics system
(`docs/superpowers/specs/2026-07-17-ad-creative-attribution-analytics-design.md`) — that
system's `ad_campaigns`/`ad_creatives`/`ad_insights_daily` tables, the Meta Insights sync
job, and the referral/prefilled-code attribution logic are all extended here, not replaced.

## What stays unchanged

**Inbound Leads → Ad Performance tab** (`frontend/app/dashboard/inbound-leads/AdPerformanceTab.tsx`,
`backend/app/routes/inbound_leads.py`'s `/ad-performance` endpoints) is untouched by this
build. It stays scoped to exactly what it is today: per-creative Click-to-WhatsApp lead
attribution (Clicked / Messaged / Qualified / Hot / Sales / Spend / CPC), answering "which
ad drove this lead" for the existing lead list. No code changes there.

Everything below lives in a **new** top-level sidebar page.

## Permission model & rollout dependency

Ad creation/publishing and any write action (pause, budget edit) requires Meta's
`ads_management` permission at **Advanced Access**. As of this design, Aira has already
**submitted** the `ads_management` use case to Meta App Review — not yet approved.

This does not block building or testing the feature: **Standard Access** (pre-approval)
already lets Aira's app call `ads_management` against ad accounts Aira itself administers.
The plan is to build and live-verify the entire Create flow against Aira's own test/sandbox
ad account now, exactly the way the existing Insights sync was live-verified against a real
account before being considered done (see the 2026-07-17 design's verification note). The
code path does not change once Advanced Access is granted — only which ad accounts are
authorized targets. Publish UI must therefore support an explicit "draft, pending Meta
approval" state (see Create → Publish behavior below), not assume every tenant's ad account
is immediately reachable.

Both the WhatsApp Embedded Signup (already approved) and this new Ads consent are
permissions on **Aira's own Meta app** — a client never submits anything to Meta App Review
themselves, for either. For Ads specifically, a client connects via **Facebook Login for
Business** (the ads-world equivalent of WhatsApp Embedded Signup): an OAuth-style consent
screen where they pick/create a Business Manager + ad account and grant Aira's system user
access. Two things this flow cannot remove, and Aira's UI should set expectations for
plainly: the client still needs their own personal Facebook login (created inline if they
don't have one), and once an ad account exists, **the client must personally add a payment
method** to it — Meta ties ad-spend liability to the account owner, and Tech Provider status
doesn't allow Aira to skip or hide that step.

## Page structure

New sidebar item: **Meta Ads** (own route, e.g. `/dashboard/meta-ads`), three tabs:

1. **Create** — build and publish a Click-to-WhatsApp campaign
2. **Ad Performance** — full account performance, all campaigns/objectives, with live
   status/budget management
3. **Analytics** — KPI cards + charts built from data only Aira has (lead quality, not
   just Meta's click/spend numbers)

---

## Tab 1: Create

### Layout

Single scrolling page (not a linear wizard) with sections stacked top-to-bottom —
Objective, Audience, Budget & Schedule, Creative — and a **sticky live ad-preview panel**
on the right that updates as fields are filled in. This mirrors Meta's own Ads Manager
creation UX (verified via live research — see Meta Ads research earlier this session), on
the reasoning that clients will eventually see the same shape of tool if they ever look at
real Meta Ads Manager, so there's no re-learning cost later.

### Objective — v1 scope: Click-to-WhatsApp only, locked

No objective picker in v1 — a single pre-selected, plain-language card ("Get WhatsApp
messages"). This is the one objective that plugs into everything already built
(auto-imported creatives, referral-based attribution, the existing funnel metrics).

**Explicitly deferred, not designed here**: Website Traffic and App Promotion objectives
(each would need a destination-URL/app-link field, no attribution payoff since they don't
route through WhatsApp) and Leads/Sales/Awareness objectives (need Meta's native Lead Form
builder and/or Conversions API/Pixel wiring respectively — substantially larger, separate
features). Adding a new objective later only means extending the picker + adding
objective-specific fields to Audience/Creative — the wizard/page structure, Budget &
Schedule section, and Publish flow do not need to be rebuilt.

### Audience

Three fields only: **Location**, **Age range**, **Gender** — plus a small plain-language
link/checkbox for Meta's legally-required Special Ad Category disclosure ("Is this ad about
housing, jobs, credit, or a social issue?", default No), since Meta requires
`special_ad_categories` on every campaign-creation call regardless of UI simplicity.

No manual placement controls and no interest/behavior targeting are exposed. This is not a
simplification that loses capability: Meta deprecated "Detailed Targeting" (interest/behavior
browsing) in January 2026 in favor of Advantage+ automatic targeting, and removed the
manual-vs-Advantage+ toggle from its own product the same year — third-party reporting
corroborates this (see Sources below; Meta's own Help Center page did not return readable
content when checked directly). Mechanically: Aira's campaign-creation payload simply never
populates `targeting.publisher_platforms`/`facebook_positions`/`instagram_positions` or
`targeting.flexible_spec` — leaving those fields unset is what makes Meta apply Advantage+
placements and broad audience-finding. Custom/Lookalike audiences are explicitly deferred
(need a source — uploaded customer list or pixel data — that doesn't exist yet).

### Budget & Schedule

- Budget type: Daily or Total (lifetime), single ₹ amount field
- Runs: start date (default today), end date optional ("until I turn it off" default)
- Budget is set at the **campaign level** (Meta's Campaign Budget Optimization), not split
  across ad sets — required for Advantage+ to fully apply, and simpler than asking a
  first-time user to allocate budget per ad set
- Bid strategy is hardcoded to Meta's automatic lowest-cost bidding ("Highest volume") — no
  cost-cap/bid-cap controls, consistent with the no-manual-dials approach in Audience
- Soft guardrail helper text: recommend at least ₹1,500 total and 7 days, matching Meta's
  own guidance that its delivery system needs a short learning period

### Creative

- Creative name (free text, tenant's own label — shown in Ad Performance/Analytics later)
- Media upload (image or video)
- Ad text (primary text shown above the image/video)
- WhatsApp number picker — the tenant's active numbers, from the existing Numbers Pool
- Pre-filled greeting (editable plain text) — Aira automatically appends the invisible
  attribution tag to this before it's used as the ad's CTA pre-filled message, per the
  existing `prefilled_message_code` mechanism from the 2026-07-17 design. The tenant only
  ever sees/edits the friendly greeting portion.
- CTA button fixed to "Send Message" (no picker — locked by the Objective decision above)

### Publish behavior

On Publish, Aira creates Campaign → Ad Set → Ad via the Marketing API in that order,
submitted Active (Meta's own ~24h ad review applies regardless of caller). **While
`ads_management` remains Standard Access** (pending the Advanced Access approval described
above), Publish targets Aira's own test ad account, and the UI shows "Draft ready — will go
live on your account once Meta approves ads_management" instead of a real spend
confirmation. This is a UI-state distinction only (`draft_pending_approval` vs `published`),
not a different code path — once Advanced Access clears, the same publish call targets the
tenant's real connected ad account.

### Attribution improvement this unlocks

Because Aira is now the one creating the ad, it knows the Meta `ad_id` **at creation time**
and can link `ad_creatives` to it immediately — more reliable than today's reactive
attribution-system behavior, which only discovers a creative once Meta starts reporting
insights for it (a brand-new ad with zero delivery doesn't show up yet). This doesn't change
the existing referral/prefilled-code matching logic, just removes the "wait for first
insights row" lag for Aira-created ads specifically.

---

## Tab 2: Ad Performance

Full account performance — **every campaign regardless of objective** (unlike the
WhatsApp-only Inbound Leads tab), mirroring Meta's own Campaigns table plus live management
actions:

- **Status toggle** (Active/Paused) per row — writes Meta's campaign/ad status via
  `ads_management`, optimistic-UI update
- **Inline budget edit** (pencil icon) — since budget lives at the campaign level (see
  Budget & Schedule above), editing it from a creative's row is a campaign-level action;
  UI must disclose "this budget is shared across N ads" so it doesn't read as a
  per-creative dial
- **Status badges** beyond Active/Paused, sourced from Meta's `effective_status`: **In
  review** (first ~24h post-publish), **Rejected** (shown with Meta's rejection reason),
  **Learning** (still in the delivery-optimization learning phase)
- Standard columns: Campaign/Ad Set/Ad name, Spend, Results (per the ad set's own
  optimization goal — installs/conversations/link clicks/etc., not forced into a single
  metric), Cost per Result

### Data requirement this needs

Today's sync (`meta_ads_insights_sync.py`) fetches only
`ad_id,ad_name,adset_id,adset_name,campaign_id,campaign_name,inline_link_clicks,clicks,spend`
at `level=ad`. This tab needs the fetch widened to include the `actions` field (Meta's
unified conversion-event array — covers app installs, website purchases, messaging
conversations, landing page views, everything, regardless of objective) plus
`objective`/`optimization_goal`/`effective_status`, and needs campaign/ad-set-level rollups
in addition to today's ad-level granularity. No new Meta permission is required for this —
`ads_read` already covers it; this is a fetch-scope change, not an access-scope change.
(Caveat carried over from the original data-gap conversation: install/website-conversion
numbers only exist if the client's own app/site already reports to Meta via SDK/Pixel — not
something Aira's dashboard can backfill.)

---

## Tab 3: Analytics

### Why these charts, not a re-skin of Meta's own numbers

Meta's own visibility ends at "message sent" — it has zero insight into whether a
Click-to-WhatsApp conversation was any good. Aira's CRM has the other half: lead scoring
(Hot/Warm/Cold/Disqualified), qualification, conversion. Every chart here is chosen because
it needs *both* halves — Meta's spend/click data joined with Aira's own lead-quality data —
which is exactly the thing Meta's own Ads Manager structurally cannot show.

### KPI cards

Spend (period), Messages, Qualified, **Cost per Hot Lead** (Aira's signature metric — cost
per *click* is a Meta number anyone can see; cost per genuinely hot lead is not), and ROAS
— shown explicitly greyed out with "needs revenue tracking, not built yet" rather than a
fake ₹0, since `leads.converted_at`/deal-value tracking doesn't exist yet (tracked
separately in the active backlog; a real prerequisite, not in scope here).

### Charts

- **Funnel** (stacked bars): Clicked → Messaged → Qualified → **Hot** → Sale. Hot only for
  v1 — Warm is deliberately *not* broken out as its own stage yet (existing "Qualified"
  metric already combines Hot+Warm; a separate Warm line is a small, well-understood
  follow-on, deferred by explicit user choice during this brainstorm, not a limitation of
  the data — segment B is already computed by the existing scoring engine).
- **Creative leaderboard**: ranked by cost-per-hot-lead (not spend, not clicks) — this is
  the chart that can reorder "your best ad" entirely relative to Meta's own volume-based
  framing.
- **Line trend**: spend vs. qualified-leads/day over time, single axis (spend indexed/area
  behind the qualified-leads line — never a dual-axis chart).
- **Heatmap**: day-of-week × hour-of-day, single hue ramped by *qualified-lead* density
  (not click density) — surfaces scheduling insight Meta's own tool can't compute, since it
  only knows click timing, not lead-quality timing.
- **Spend Efficiency Quadrant**: scatter of Spend (x) vs. Cost-per-Hot-Lead (y) per
  creative, bubble size = hot-lead volume. Answers "where should next month's budget go"
  directly — bottom-left (low spend, low cost/lead) = scale up; top-right (high spend, high
  cost/lead) = cut or fix.
- **Spend Distribution donut**: where budget is currently concentrated, one fixed
  violet-shade-family color per creative, kept consistent with the same creative's color
  across the leaderboard and quadrant charts on the same page (per the dataviz principle:
  color follows the entity, never re-cycled).

All of the above except ROAS run on data `ad_performance.py` already computes today
(messages/qualified/hot/sales/spend/cpc/cost_per_qualified/cost_per_hot) — this tab is
primarily a visualization layer over existing aggregation logic, not new backend math.

---

## Data model changes (new)

Refined at implementation-plan time, but the shape needed:

- **`ad_campaigns`**: add `status` (Meta `effective_status`), `daily_budget`/
  `lifetime_budget`, `bid_strategy`, `objective`, `special_ad_category`, and a
  `created_via` flag (`aira` vs `imported`) to distinguish campaigns Aira created from
  ones merely discovered via the Insights sync.
- **New `ad_sets` table**: `id, tenant_id, campaign_id (FK), meta_adset_id, adset_name,
  targeting (jsonb: location/age/gender/special_category), optimization_goal, status,
  created_at, updated_at`. Needed because Ad Performance now shows ad-set-level rows
  directly (not just derived by grouping creative rows, today's pattern) and because
  Create needs to persist what it wrote to Meta at ad-set creation.
- **`ad_creatives`**: add `created_by_aira` (bool), `prefilled_greeting` (the editable
  portion, separate from the full tagged message), `media_asset_ref` (Meta's returned
  `image_hash`/`video_id`), `cta_type`.
- **`ad_insights_daily`**: widen columns captured per day to include `impressions`,
  `reach`, and a generic `actions` jsonb blob (Meta's full conversion-event array) —
  campaign/ad-set-level performance in Ad Performance/Analytics is computed by rolling up
  ad-level rows in the aggregation service, the same pattern `build_creative_performance`
  already uses today, rather than adding separate per-level insight tables.

## Placement summary

- **Frontend**: new `frontend/app/dashboard/meta-ads/` route + sidebar entry; `CreateTab`,
  `AdPerformanceTab` (new, distinct from the existing Inbound Leads one of the same name —
  needs a distinguishing name at implementation time), and `AnalyticsTab` components.
- **Backend**: new write-capable service (`backend/app/services/meta_ads_manager.py` or
  similar) wrapping campaign/ad-set/ad creation, status toggle, and budget-update Marketing
  API calls; widened fetch in `meta_ads_insights_sync.py`; new routes under a `meta-ads`
  router distinct from `inbound_leads.py`.
- **Schema**: one new migration for the `ad_campaigns` column additions, the new `ad_sets`
  table, `ad_creatives` additions, and `ad_insights_daily` column additions described above.
- **Credentials**: extends the existing per-tenant `app_settings` pattern
  (`meta_ads_access_token`/`meta_ads_account_id`) — the token's granted scope becomes
  `ads_management` instead of `ads_read` once Advanced Access clears; no new credential
  storage pattern needed, same manual-paste-in (or, once built, Facebook-Login-for-Business
  consent flow) model as today.

## Suggested build sequencing (for the implementation plan)

This spec covers all three tabs together because they share one page shell and one
underlying data model, but they don't share the same blockers, so the implementation plan
should likely split into two tracks rather than one linear build:

1. **Ad Performance + Analytics** (widened Insights fetch, new schema columns, the charts)
   — no external dependency, `ads_read` already covers it, can ship as soon as it's built.
2. **Create** (campaign/ad-set/ad write calls, the wizard, publish flow) — build and
   live-test against Aira's own test ad account now, but real-tenant publishing stays
   gated behind Meta's Advanced Access approval regardless of engineering readiness.

## Explicitly out of scope for this build

- Objectives beyond Click-to-WhatsApp (Website Traffic, App Promotion, Leads, Sales,
  Awareness) — each is a real, separately-scoped follow-on (see Objective section above).
- Custom/Lookalike audiences, manual placement controls, interest/behavior targeting —
  deliberately not built; Meta itself is moving away from manual targeting.
- Warm as a distinct funnel/Analytics stage — deferred by explicit choice; Hot only for v1.
- ROAS / revenue-weighted metrics — blocked on lead conversion + deal-value tracking, which
  doesn't exist yet (separate piece of work, already tracked in the active backlog).
- Sankey flow-diagram treatment of the funnel — considered during this brainstorm, replaced
  by simple stacked funnel bars plus the Spend Efficiency Quadrant and Spend Distribution
  donut instead.
- Meta Conversions API — as already noted in the 2026-07-17 design, still deferred.

## Sources consulted during this design

- [Meta Advanced Access: Which Permissions Need App Review](https://singhamandeep.com/what-is-meta-advanced-access/)
- [Meta Ads API: Setup, Automation & Real Limits (2026)](https://admanage.ai/blog/meta-ads-api)
- [How to Give an Agency Access to Meta Business Manager](https://herocontent.ai/gb/blog/give-agency-access-to-meta-business-manager)
- [WhatsApp Business API Permissions Explained – Avoid App Rejection (2026)](https://anjoktechnologies.in/blog/-whatsapp-business-api-permissions-explained-avoid-app-rejection-2026-)
- [Facebook Ads Campaign Structure: The Complete 2026 Guide](https://blog.adnabu.com/facebook-ads/facebook-ads-campaign-structure/)
- [Meta Advantage+ Placements: When to Use Them (2026)](https://blog.adnabu.com/facebook/meta-advantage-plus-placements/)
- [Meta Ads Manager vs. Meta Business Suite](https://metricool.com/ads-manager-vs-meta-business-suite/)
