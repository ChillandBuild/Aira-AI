# Tenant Dashboard Redesign — Design

**Date:** 2026-07-28
**Status:** Approved, ready for implementation planning

Full redesign of the tenant-facing home dashboard (`frontend/app/dashboard/DashboardClient.tsx`),
replacing the current KPI-card layout and the recently-added `DayStrip` component with a
question-driven, adaptive page — and eliminating every fabricated number on it.

## Problem

The current dashboard (`DashboardClient.tsx`) has two kinds of issues:

1. **It's not useful.** It's a flat grid of stat cards with no narrative — "Total Leads",
   "Hot Leads", "Performance", "Automation & Traffic", a pipeline bar. A tenant owner opening
   it can't answer "is my AI doing its job" or "where are my leads coming from" without
   leaving the page. The just-shipped `DayStrip` (day-by-day Inbound/Outbound/AI-handled strip)
   was meant to add depth here but reads as plumbing, not product — flagged directly by the
   user as not good enough to keep.
2. **Parts of it are fake.** Two specific defects, both in `DashboardClient.tsx`:
   - `↑ 12.4%` (line 263) and `↑ 36.8%` (line 298) — hardcoded trend badges on the Total
     Leads and Hot Leads cards. Never computed from anything.
   - Two SVG sparkline `<path>` elements (lines 253–254, 288–289) — fixed decorative curves,
     not driven by `overview` data at all.

   The user's explicit requirement: **no fake or dummy data anywhere on this page, ever.**
   Every number, badge, and chart must trace to a real query. Where real data doesn't exist
   yet, either build the real thing or don't show it — never fake it.

## Decisions

| # | Decision | Rationale |
|---|---|---|
| D1 | Informational dashboard; deep-dive analytics stays on `/dashboard/analytics` | User: "it should be informational ...and the deep analytics should be in the analytics page." This page answers "how am I doing right now," not "let me slice by channel and date range." |
| D2 | Adaptive sections, gated on `enabledFeatures` and on whether the tenant has the underlying data | User: "it should adapt to what each tenant actually uses." A tenant with no ad campaigns doesn't get an empty Ad Spend card; a tenant without telecalling enabled doesn't get a Team & Calls card. |
| D3 | Structure: question-driven story sections (Approach B) + hero-row treatment for the top section (Approach C) | User approved "B with C." Sections are framed as the question a tenant actually has ("Is my AI carrying its weight?", "Where are leads coming from?"), and the first section reads as a hero band, not another card in a grid. |
| D4 | Drop `DayStrip` from the home dashboard entirely | User explicitly rejected it visually. It is not deleted from the codebase — the operator console's per-client analytics view keeps its own `DayStrip` usage, since that critique was about the home dashboard's execution, not the component's existence. |
| D5 | Reframe "Hot Leads" → "New Hot Leads (7d)" and back it with `lead_stage_events` | A raw `by_segment.A` count is a snapshot — trending it week-over-week is meaningless (a lead can sit in segment A for a month; the number moving up or down says nothing about *this week's* activity). Counting `lead_stage_events` rows where `to_segment = 'A'` and `created_at` falls in the last 7 days turns this into a real, trendable flow metric, using a table that already exists and is already written on every segment transition. |
| D6 | Add a `trend_pct` + prior-window comparison to `/api/v1/analytics/overview`, mirroring the existing pattern in the operator fleet endpoint | The only way to make the hero row's WoW badges real is to compute them server-side against a prior window, exactly as `operator.py`'s `/token-usage/fleet` already does for AI Spend. Reuses a proven pattern instead of inventing a new one. |
| D7 | Escalations count comes from the existing `GET /api/v1/chat-handovers/count` endpoint | Already returns a real, live count of `chat_handovers` rows with `status = "pending"`. No new backend needed. |
| D8 | Ad Spend section sourced from the existing `build_ad_performance()` / `GET /analytics/ad-performance` | Already-built, already-real. Section is simply hidden when `campaigns` is empty (existing behavior of that function). |
| D9 | Team & Calls section sourced from the existing `GET /analytics/telecalling` endpoint | Already-built, already-real (backed by the `get_telecalling_all_time_stats` RPC). Section is gated on `enabledFeatures.includes("telecalling")`. |

## Page Structure

### 1. Pipeline Pulse (hero row)

Three cards, hero-styled (larger, top of page, no surrounding grid competing for attention):

- **Total Leads** — headline number is `overview.total_leads` (cumulative, all-time). The
  sparkline and the WoW `trend_pct` badge underneath it do **not** trend the cumulative total
  itself (a number that only ever goes up isn't meaningfully "trendable") — they trend *new
  leads added per day*, built from `overview.daily_leads`, comparing this week's daily-add
  volume against last week's (see D6). The badge label makes this explicit, e.g. "+12% new
  leads vs last week," not a bare percentage next to the cumulative total.
- **New Hot Leads (7d)** — count of `lead_stage_events` where `to_segment = 'A'` in the last
  7 days (see D5), same sparkline/trend treatment.
- **Conversions (7d)** — `overview.converted_7d`, same treatment.

Each card's sparkline is generated from the real daily series returned by the endpoint — no
decorative paths. If a metric has zero data points to draw from, the card shows the number
with no sparkline rather than a fake flat line.

### 2. "Is my AI carrying its weight?"

Replaces the old "Today" card and the `DayStrip`. Four data points, real, all already computed
or trivially derivable from the existing `/overview` payload:

- **AI Auto-Reply Share %** — already computed client-side from `overview.ai_vs_human` (kept,
  it's real).
- **AI vs Human split** — `overview.ai_vs_human.ai` / `.human` (kept, it's real).
- **Inbound / Outbound today** — already available per-day in `overview.daily_messages` (take
  today's entry).
- **Escalations awaiting a human** — new: `GET /api/v1/chat-handovers/count` (see D7).

### 3. Pipeline distribution

The existing `PipelineBar` (Hot/Warm/Cold/Disqualified stacked bar + tiles) is kept as-is — it
was already real data (`overview.by_segment`). Visual restyle only, to match the new page's
rhythm; no data changes.

### 4. "Where are leads coming from?"

New section using `overview.channel_breakdown`, which the `/overview` endpoint already
computes and returns but which nothing in the frontend currently renders. Shows the channel
split (WhatsApp / Instagram / Facebook / Telegram / upload / manual) as a simple breakdown,
plus organic vs. ad-attributed split (a lead counts as ad-attributed if `ad_campaign_id` is
set — already the exact rule `build_ad_performance()` uses for `tracked_leads`).

### 5. "Team & Calls" (adaptive)

Rendered only if `enabledFeatures.includes("telecalling")` (see D9). Sourced from
`GET /analytics/telecalling`.

### 6. "Ad Spend" (adaptive)

Rendered only if the tenant has at least one row in `ad_campaigns` (see D8) — checked by
calling `/analytics/ad-performance` and hiding the section when `campaigns` comes back empty,
the same convention `build_ad_performance()` already uses for its own "no campaigns" case.

## Honesty Audit — every fake element and its fix

| Current fake element | Location | Fix |
|---|---|---|
| `↑ 12.4%` hardcoded badge | `DashboardClient.tsx:263` | Replaced by real `trend_pct` from new backend comparison (D6) |
| `↑ 36.8%` hardcoded badge | `DashboardClient.tsx:298` | Replaced by real `trend_pct` on the "New Hot Leads (7d)" card, computed the same way |
| Decorative SVG sparkline path (Total Leads) | `DashboardClient.tsx:253-254` | Replaced by a real path generated from `overview.daily_leads` |
| Decorative SVG sparkline path (Hot Leads) | `DashboardClient.tsx:288-289` | Replaced by a real path generated from `lead_stage_events` daily counts |
| `DayStrip` on home dashboard | `TodaySnapshot` in `DashboardClient.tsx` | Removed from this page (D4); section 2 above replaces it with real, differently-shaped data |

No other numbers on the current page are fake — `converted_7d`, `unreplied_24h`,
`ai_handled_today`, `by_segment`, `ai_vs_human` were already real and are carried forward
unchanged.

## Backend Changes Required

1. **`GET /api/v1/analytics/overview`** — extend to also fetch a prior comparison window
   (same length as the requested range, immediately preceding it) for `daily_leads` and the
   "New Hot Leads" `lead_stage_events` count, and return `trend_pct` for each of the three
   hero metrics. Pattern: mirror `_range_params` + the prior-window `gte().lt()` fetch already
   used in `operator.py`'s `/token-usage/fleet` (see D6). `trend_pct` is `None` when there's no
   prior-window baseline to compare against (empty prior window) — same convention the fleet
   endpoint already follows, not a new invention.
2. **New Hot Leads (7d)** — query `lead_stage_events` for `to_segment = 'A'` within the
   current range and the prior comparison window, tenant-scoped. No schema change; the table
   and columns already exist (`growth.py`, `assignment.py`, `whatsapp_notify.py` already write
   to it).
3. No changes needed for: escalations count (`/chat-handovers/count` already exists), Ad Spend
   (`/analytics/ad-performance` already exists), Team & Calls (`/analytics/telecalling` already
   exists), channel breakdown (`overview.channel_breakdown` already computed and returned, just
   currently unused by the frontend).

## Frontend Changes Required

- `DashboardClient.tsx` — full rewrite of the render body per the structure above. `TodaySnapshot`
  and its `DayStrip` usage removed from this file.
- `PipelineBar` — kept, restyled only.
- `frontend/components/DayStrip.tsx` — **not deleted**; the operator console's per-client
  analytics view (`operator/(console)/client/[id]/views/analytics.tsx`) still uses it (D4).
- New small presentational pieces: a real sparkline renderer (given a numeric series, draw a
  path — no fixed curves), a trend badge (renders nothing, not a fake arrow, when `trend_pct`
  is `null`), and the two new adaptive section components (Team & Calls, Ad Spend).
- `lib/api.ts` — extend `AnalyticsOverview` type with `trend_pct` fields on the relevant hero
  metrics and the "new hot leads" series/count.

## Testing

- Backend: unit tests for the new prior-window comparison logic on `/overview` (mirroring the
  existing `test_operator_fleet_token_usage.py` trend tests: null when all-time or no prior
  baseline, correct `trend_pct` math against a known baseline) and for the new
  `lead_stage_events`-backed "new hot leads" count.
- Frontend: visual regression screenshots at 320/768/1024/1440 for the redesigned page in both
  the adaptive-off (no telecalling, no ad campaigns) and adaptive-on states, plus a zero-data
  tenant state (no leads yet) — verified live via Playwright against a real tenant, not just
  typecheck/lint passing.

## Out of Scope

- No changes to `/dashboard/analytics` (the deep-dive page) — this redesign is the home page
  only (D1).
- No changes to the operator console's own dashboard/analytics views beyond leaving their
  existing `DayStrip` usage untouched.
- No new database tables or columns — every section is backed by data that already exists.
