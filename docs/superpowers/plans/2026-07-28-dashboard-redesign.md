# Tenant Dashboard Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the tenant home dashboard's flat KPI-card layout and the disliked `DayStrip` with a question-driven, adaptive page where every number, badge, and chart traces to a real query — zero fabricated data.

**Architecture:** Backend adds a prior-window trend computation to the existing `GET /api/v1/analytics/overview` endpoint (three new response fields, no new endpoint, no schema change — reuses the `_pct_trend` pattern already proven in `operator.py`'s fleet endpoint). Frontend replaces `DashboardClient.tsx`'s render body with six composed section components, using `recharts` (already a dependency, already used on `/dashboard/analytics`) for real sparklines instead of hand-drawn SVG paths.

**Tech Stack:** FastAPI (`backend/app/routes/analytics.py`), Next.js 14 App Router (`frontend/app/dashboard/`), Supabase (`leads`, `lead_stage_events`, `messages`, `chat_handovers`, `ad_campaigns` tables — all pre-existing, no migration), recharts, SWR (`useOverview`, `useApi.ts`).

## Global Constraints

- No fake, hardcoded, or decorative-only data anywhere on the redesigned page (spec requirement, non-negotiable). Every number/badge/chart must come from a real API field.
- No new database tables or columns — every section is backed by data that already exists (spec: Out of Scope).
- No changes to `/dashboard/analytics` (the deep-dive page) or to the operator console's own `DayStrip` usage in `client/[id]/views/analytics.tsx` — that file is untouched.
- Adaptive sections (Team & Calls, Ad Spend) render only when their gating condition is true: `enabledFeatures.includes("telecalling")` for Team & Calls; a non-empty `campaigns` array from `/analytics/ad-performance` for Ad Spend.
- Deep violet `#5b21b6` accent (design preference), cream surface — match the existing `/dashboard/analytics` recharts styling exactly (same gradient stop colors, same grid/tooltip styling) rather than inventing a new palette.
- Visual verification is via actual Playwright screenshots against a real tenant (Astro Tamil, `eba3ed94-277c-430f-a992-19bbe855e2f4`) at 320/768/1024/1440 — not just typecheck/lint passing.

---

## File Structure

**Backend:**
- Modify: `backend/app/routes/analytics.py` — add `_pct_trend` helper and extend `overview_analytics()` (lines ~921-1064) with three new response fields.
- Create: `backend/tests/test_analytics_overview.py` — first test file for this endpoint (none exists today).

**Frontend:**
- Modify: `frontend/lib/api.ts` — extend `AnalyticsOverview` interface; add `chatHandovers.count()` wrapper.
- Create: `frontend/components/dashboard/TrendBadge.tsx` — renders a trend % or nothing when `null`.
- Create: `frontend/components/dashboard/TrendBadge.test.tsx` — vitest unit tests.
- Create: `frontend/components/dashboard/HeroSparkline.tsx` — recharts mini-`AreaChart` wrapper, no axes.
- Create: `frontend/components/dashboard/PipelinePulse.tsx` — hero row (Total Leads / New Hot Leads (7d) / Conversions (7d)).
- Create: `frontend/components/dashboard/AiWorkloadSection.tsx` — "Is my AI carrying its weight?"
- Create: `frontend/components/dashboard/LeadSourceSection.tsx` — "Where are leads coming from?"
- Create: `frontend/components/dashboard/TeamCallsSection.tsx` — adaptive, telecalling.
- Create: `frontend/components/dashboard/AdSpendSection.tsx` — adaptive, ad campaigns.
- Modify: `frontend/app/dashboard/DashboardClient.tsx` — rewrite render body to compose the six sections; remove `TodaySnapshot`/`DayStrip` usage and the two fake-data blocks.

---

### Task 1: Backend — `_pct_trend` helper + Total Leads / Conversions trend fields on `/overview`

**Files:**
- Modify: `backend/app/routes/analytics.py:921-1064` (the `overview_analytics` function)
- Test: `backend/tests/test_analytics_overview.py` (new)

**Interfaces:**
- Produces: `_pct_trend(current: int, prior: int) -> float | None` (module-level function in `analytics.py`)
- Produces: three new top-level fields on the `/overview` JSON response: `daily_leads_trend_pct: float | None`, `converted_7d_trend_pct: float | None`, `ad_attributed_leads: int`

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for GET /api/v1/analytics/overview -- the tenant home dashboard's
data source. Covers the prior-window trend fields (D6 of the 2026-07-28
dashboard redesign spec): daily_leads_trend_pct, converted_7d_trend_pct,
new_hot_leads_7d / new_hot_leads_7d_trend_pct."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.tenant import get_tenant_and_role


class AnalyticsOverviewTrendTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_tenant_and_role] = lambda: {
            "tenant_id": "tenant-1", "role": "owner", "permissions": [],
        }

    def tearDown(self):
        app.dependency_overrides.clear()

    def _mock_db(self, mock_get_db, leads_rows, prior_leads_rows, msgs_rows,
                 stage_events_rows, prior_stage_events_rows, handover_count=0):
        db = MagicMock()

        leads_tbl = MagicMock()
        leads_chain = leads_tbl.select.return_value.eq.return_value.is_.return_value
        leads_chain.execute.return_value = MagicMock(data=leads_rows)
        # prior-window leads fetch adds .gte().lt()
        leads_chain.gte.return_value.lt.return_value.execute.return_value = MagicMock(data=prior_leads_rows)

        msgs_tbl = MagicMock()
        msgs_tbl.select.return_value.eq.return_value.gte.return_value.execute.return_value = MagicMock(data=msgs_rows)

        events_tbl = MagicMock()
        events_chain = events_tbl.select.return_value.eq.return_value.eq.return_value.gte.return_value
        events_chain.execute.return_value = MagicMock(data=stage_events_rows)
        # Prior-window fetch is select->eq->eq->gte->lt->execute (a single .gte()
        # call, not two) -- .lt() is chained directly off events_chain, not off
        # events_chain.gte again.
        events_chain.lt.return_value.execute.return_value = MagicMock(data=prior_stage_events_rows)

        def table(name):
            return {"leads": leads_tbl, "messages": msgs_tbl, "lead_stage_events": events_tbl}[name]

        db.table.side_effect = table
        mock_get_db.return_value = db
        return db

    @patch("app.routes.analytics.get_supabase")
    def test_daily_leads_trend_pct_none_when_no_prior_baseline(self, mock_get_db):
        self._mock_db(mock_get_db, leads_rows=[], prior_leads_rows=[], msgs_rows=[],
                       stage_events_rows=[], prior_stage_events_rows=[])

        res = self.client.get("/api/v1/analytics/overview?range=7d")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertIsNone(body["daily_leads_trend_pct"])
        self.assertIsNone(body["converted_7d_trend_pct"])
        self.assertIsNone(body["new_hot_leads_7d_trend_pct"])

    @patch("app.routes.analytics.get_supabase")
    def test_ad_attributed_leads_counts_leads_with_ad_campaign_id(self, mock_get_db):
        current_leads = [
            {"id": "l1", "created_at": "2026-07-20T10:00:00+00:00", "segment": "C",
             "source": "whatsapp", "converted_at": None, "ad_campaign_id": "camp-1"},
            {"id": "l2", "created_at": "2026-07-20T10:00:00+00:00", "segment": "C",
             "source": "whatsapp", "converted_at": None, "ad_campaign_id": None},
        ]
        self._mock_db(mock_get_db, leads_rows=current_leads, prior_leads_rows=[],
                       msgs_rows=[], stage_events_rows=[], prior_stage_events_rows=[])

        res = self.client.get("/api/v1/analytics/overview?range=7d")
        body = res.json()
        self.assertEqual(body["ad_attributed_leads"], 1)

    @patch("app.routes.analytics.get_supabase")
    def test_daily_leads_trend_pct_computed_against_prior_window(self, mock_get_db):
        from datetime import datetime, timezone, timedelta
        today = datetime.now(timezone.utc).date().isoformat()
        prior_day = (datetime.now(timezone.utc) - timedelta(days=10)).date().isoformat()

        current_leads = [{"id": f"l{i}", "created_at": f"{today}T10:00:00+00:00", "segment": "C",
                           "source": "whatsapp", "converted_at": None} for i in range(3)]
        prior_leads = [{"id": f"p{i}", "created_at": f"{prior_day}T10:00:00+00:00", "segment": "C",
                         "source": "whatsapp", "converted_at": None} for i in range(2)]

        self._mock_db(mock_get_db, leads_rows=current_leads, prior_leads_rows=prior_leads,
                       msgs_rows=[], stage_events_rows=[], prior_stage_events_rows=[])

        res = self.client.get("/api/v1/analytics/overview?range=7d")
        body = res.json()
        # 3 current vs 2 prior -> +50%
        self.assertEqual(body["daily_leads_trend_pct"], 50)

    @patch("app.routes.analytics.get_supabase")
    def test_new_hot_leads_7d_counted_from_lead_stage_events(self, mock_get_db):
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).date().isoformat()
        stage_events = [
            {"lead_id": "l1", "to_segment": "A", "created_at": f"{today}T09:00:00+00:00"},
            {"lead_id": "l2", "to_segment": "A", "created_at": f"{today}T11:00:00+00:00"},
        ]
        self._mock_db(mock_get_db, leads_rows=[], prior_leads_rows=[], msgs_rows=[],
                       stage_events_rows=stage_events, prior_stage_events_rows=[])

        res = self.client.get("/api/v1/analytics/overview?range=7d")
        body = res.json()
        self.assertEqual(body["new_hot_leads_7d"], 2)
        self.assertIsInstance(body["new_hot_leads_7d_daily"], list)
        self.assertIsNone(body["new_hot_leads_7d_trend_pct"])  # empty prior window


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && venv/bin/python3.14 -m pytest tests/test_analytics_overview.py -v`
Expected: FAIL — `daily_leads_trend_pct` / `converted_7d_trend_pct` / `new_hot_leads_7d*` keys don't exist yet on the response, and the mocked `leads`/`lead_stage_events` chains don't match the current query shape.

- [ ] **Step 3: Add `_pct_trend` helper**

Add directly above `overview_analytics` in `backend/app/routes/analytics.py` (same logic as the proven `operator.py:1047` helper, copied rather than imported cross-module — this file has no existing shared-util import for it and every other route module keeps its own small helpers):

```python
def _pct_trend(current: int, prior: int) -> float | None:
    """None when there's no meaningful baseline (prior window had zero
    activity) -- going from 0 to any activity isn't a "% increase," it's new,
    and dividing by zero would misrepresent that."""
    if prior <= 0:
        return None
    return round((current - prior) / prior * 100)
```

- [ ] **Step 4: Add `ad_campaign_id` to the existing leads select and tally ad-attributed leads**

Change the existing `leads_rows` select at line 936 from:

```python
.select("id,phone,segment,score,source,created_at,converted_at,ai_enabled,deleted_at")
```

to:

```python
.select("id,phone,segment,score,source,created_at,converted_at,ai_enabled,deleted_at,ad_campaign_id")
```

Inside the existing `for lead in leads_rows:` loop (starting line 957), add one line to tally ad-attributed leads (same rule `build_ad_performance()` already uses — a lead counts as ad-attributed when `ad_campaign_id` is set):

```python
    ad_attributed_leads = 0
    for lead in leads_rows:
        # ... existing loop body unchanged ...
        if lead.get("ad_campaign_id"):
            ad_attributed_leads += 1
```

- [ ] **Step 5: Extend `overview_analytics` with the prior-window leads fetch and Total-Leads / Conversions trend**

In `backend/app/routes/analytics.py`, inside `overview_analytics` (after `window_start_dt, days_iso = _range_params(range)` at line 931), compute the prior window's bounds and fetch it:

```python
    window_start_dt, days_iso = _range_params(range)
    window_span = now - window_start_dt
    prior_window_start_dt = window_start_dt - window_span
```

Immediately after the existing `leads_rows` fetch (lines 933-941), add the prior-window fetch:

```python
    prior_leads_rows = (
        await asyncio.to_thread(
            db.table("leads")
            .select("id,created_at,converted_at")
            .eq("tenant_id", tenant_id)
            .is_("deleted_at", "null")
            .gte("created_at", prior_window_start_dt.isoformat())
            .lt("created_at", window_start_dt.isoformat())
            .execute
        )
    ).data or []
```

After the existing `for lead in leads_rows:` loop (which produces `daily_leads_map`, `converted_7d`, etc.), add the prior-window tallies and the two trend fields:

```python
    prior_new_leads = len(prior_leads_rows)
    current_new_leads = sum(daily_leads_map.values())
    daily_leads_trend_pct = _pct_trend(current_new_leads, prior_new_leads)

    prior_converted_7d = sum(
        1 for lead in prior_leads_rows
        if lead.get("converted_at") and lead["converted_at"] >= prior_window_start_dt.isoformat()
    )
    converted_7d_trend_pct = _pct_trend(converted_7d, prior_converted_7d)
```

- [ ] **Step 6: Wire the three fields into the response dict**

In the `return {...}` block (lines 1038-1064), add:

```python
        "daily_leads_trend_pct": daily_leads_trend_pct,
        "converted_7d_trend_pct": converted_7d_trend_pct,
        "ad_attributed_leads": ad_attributed_leads,
```

- [ ] **Step 7: Run tests, confirm the trend and ad-attributed tests pass (new-hot-leads tests still fail)**

Run: `cd backend && venv/bin/python3.14 -m pytest tests/test_analytics_overview.py -v`
Expected: `test_daily_leads_trend_pct_none_when_no_prior_baseline`, `test_ad_attributed_leads_counts_leads_with_ad_campaign_id`, and `test_daily_leads_trend_pct_computed_against_prior_window` PASS. `test_new_hot_leads_7d_counted_from_lead_stage_events` still FAILS (built in Task 2).

- [ ] **Step 8: Commit**

```bash
cd "/Users/prem/Documents/Aira AI"
git add backend/app/routes/analytics.py backend/tests/test_analytics_overview.py
git commit -m "feat(analytics): add prior-window trend to dashboard overview endpoint"
```

---

### Task 2: Backend — New Hot Leads (7d) from `lead_stage_events`

**Files:**
- Modify: `backend/app/routes/analytics.py` (same `overview_analytics` function)
- Test: `backend/tests/test_analytics_overview.py` (already created in Task 1)

**Interfaces:**
- Consumes: `_pct_trend()` from Task 1, `days_iso` / `prior_window_start_dt` / `window_start_dt` from Task 1's changes
- Produces: three new response fields — `new_hot_leads_7d: int`, `new_hot_leads_7d_daily: [{day, count}]`, `new_hot_leads_7d_trend_pct: float | None`

- [ ] **Step 1: Add the current + prior `lead_stage_events` fetch**

In `overview_analytics`, after the `prior_leads_rows` fetch from Task 1, add:

```python
    stage_events_rows = (
        await asyncio.to_thread(
            db.table("lead_stage_events")
            .select("lead_id,to_segment,created_at")
            .eq("tenant_id", tenant_id)
            .eq("to_segment", "A")
            .gte("created_at", window_start_dt.isoformat())
            .execute
        )
    ).data or []

    prior_stage_events_rows = (
        await asyncio.to_thread(
            db.table("lead_stage_events")
            .select("lead_id,to_segment,created_at")
            .eq("tenant_id", tenant_id)
            .eq("to_segment", "A")
            .gte("created_at", prior_window_start_dt.isoformat())
            .lt("created_at", window_start_dt.isoformat())
            .execute
        )
    ).data or []
```

- [ ] **Step 2: Build the daily series and trend**

```python
    new_hot_leads_daily_map = {d: 0 for d in days_iso}
    for event in stage_events_rows:
        day = (event.get("created_at") or "")[:10]
        if day in new_hot_leads_daily_map:
            new_hot_leads_daily_map[day] += 1

    new_hot_leads_7d = sum(new_hot_leads_daily_map.values())
    new_hot_leads_7d_trend_pct = _pct_trend(new_hot_leads_7d, len(prior_stage_events_rows))
```

- [ ] **Step 3: Wire the three fields into the response dict**

```python
        "new_hot_leads_7d": new_hot_leads_7d,
        "new_hot_leads_7d_daily": [{"day": d, "count": new_hot_leads_daily_map[d]} for d in days_iso],
        "new_hot_leads_7d_trend_pct": new_hot_leads_7d_trend_pct,
```

- [ ] **Step 4: Run all analytics-overview tests**

Run: `cd backend && venv/bin/python3.14 -m pytest tests/test_analytics_overview.py -v`
Expected: all 3 tests PASS.

- [ ] **Step 5: Run the full backend suite to confirm no regression**

Run: `cd backend && venv/bin/python3.14 -m pytest tests/ -q`
Expected: all tests pass (628 + 4 new = 632).

- [ ] **Step 6: Commit**

```bash
cd "/Users/prem/Documents/Aira AI"
git add backend/app/routes/analytics.py backend/tests/test_analytics_overview.py
git commit -m "feat(analytics): back New Hot Leads (7d) with lead_stage_events"
```

---

### Task 3: Frontend — extend `AnalyticsOverview` type + `chatHandovers.count()` wrapper

**Files:**
- Modify: `frontend/lib/api.ts:341-350` (`AnalyticsOverview` interface), `frontend/lib/api.ts:1855-1861` (`chatHandovers`)

**Interfaces:**
- Produces: updated `AnalyticsOverview` interface (consumed by every component in Tasks 4-9); `api.chatHandovers.count(): Promise<{ count: number }>`

- [ ] **Step 1: Extend `AnalyticsOverview`**

Replace the interface at `frontend/lib/api.ts:341-350`:

```typescript
export interface AnalyticsOverview {
  daily_leads: { day: string; count: number }[];
  daily_leads_trend_pct: number | null;
  daily_messages: { day: string; inbound: number; outbound: number; ai: number; human: number }[];
  funnel: { inquiries: number; engaged: number; hot: number; converted: number };
  ai_vs_human: { ai: number; human: number };
  unreplied_24h: number;
  converted_7d: number;
  converted_7d_trend_pct: number | null;
  ai_handled_today: number;
  by_segment: Record<"A" | "B" | "C" | "D", number>;
  channel_breakdown: { whatsapp: number; instagram: number; facebook: number; telegram: number; upload: number; manual: number };
  total_leads: number;
  ad_attributed_leads: number;
  new_hot_leads_7d: number;
  new_hot_leads_7d_daily: { day: string; count: number }[];
  new_hot_leads_7d_trend_pct: number | null;
}
```

(`channel_breakdown` and `total_leads` were already returned by the backend but missing from this type — the backend never changed them, only this TS type was out of date.)

- [ ] **Step 2: Add `chatHandovers.count()`**

In `frontend/lib/api.ts`, inside the existing `chatHandovers` object (line ~1855):

```typescript
  chatHandovers: {
    count: () => apiFetch<{ count: number }>(`/api/v1/chat-handovers/count`),
    assign: (handoverId: string, callerId: string) =>
      apiFetch<{ assigned: boolean }>(`/api/v1/chat-handovers/${handoverId}/assign`, {
        method: "PATCH",
        body: JSON.stringify({ caller_id: callerId }),
      }),
  },
```

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npm run typecheck`
Expected: PASS. (If `AnalyticsOverviewExtended` or other call sites reference the old narrower shape, they still satisfy the new one since all original fields are preserved — this is additive-only.)

- [ ] **Step 4: Commit**

```bash
cd "/Users/prem/Documents/Aira AI"
git add frontend/lib/api.ts
git commit -m "feat(dashboard): extend AnalyticsOverview type with trend fields, add chatHandovers.count()"
```

---

### Task 4: Frontend — `TrendBadge` component

**Files:**
- Create: `frontend/components/dashboard/TrendBadge.tsx`
- Test: `frontend/components/dashboard/TrendBadge.test.tsx`

**Interfaces:**
- Produces: `TrendBadge({ pct, label }: { pct: number | null; label: string })` — renders nothing when `pct` is `null` (never a fake arrow), a green up-badge when `pct > 0`, a red down-badge when `pct < 0`, a gray flat badge when `pct === 0`.
- Consumed by: `PipelinePulse.tsx` (Task 6)

- [ ] **Step 1: Write the failing test**

```typescript
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { TrendBadge } from "./TrendBadge";

describe("TrendBadge", () => {
  it("renders nothing when pct is null", () => {
    const { container } = render(<TrendBadge pct={null} label="vs last week" />);
    expect(container.firstChild).toBeNull();
  });

  it("renders an up badge for positive pct", () => {
    render(<TrendBadge pct={12} label="vs last week" />);
    expect(screen.getByText("↑ 12%")).toBeInTheDocument();
    expect(screen.getByText("vs last week")).toBeInTheDocument();
  });

  it("renders a down badge for negative pct", () => {
    render(<TrendBadge pct={-8} label="vs last week" />);
    expect(screen.getByText("↓ 8%")).toBeInTheDocument();
  });

  it("renders a flat badge for zero pct", () => {
    render(<TrendBadge pct={0} label="vs last week" />);
    expect(screen.getByText("→ 0%")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run components/dashboard/TrendBadge.test.tsx`
Expected: FAIL — `./TrendBadge` module doesn't exist.

- [ ] **Step 3: Write the implementation**

```tsx
interface TrendBadgeProps {
  pct: number | null;
  label: string;
}

export function TrendBadge({ pct, label }: TrendBadgeProps) {
  if (pct === null) return null;

  const badgeClass = pct > 0 ? "badge-green" : pct < 0 ? "badge-red" : "badge-gray";
  const arrow = pct > 0 ? "↑" : pct < 0 ? "↓" : "→";

  return (
    <div className="mt-8 flex items-center">
      <span className={`badge ${badgeClass} font-semibold`}>
        {arrow} {Math.abs(pct)}%
      </span>
      <span className="text-xs text-ink-muted ml-2 font-medium">{label}</span>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run components/dashboard/TrendBadge.test.tsx`
Expected: PASS, all 4 tests.

- [ ] **Step 5: Commit**

```bash
cd "/Users/prem/Documents/Aira AI"
git add frontend/components/dashboard/TrendBadge.tsx frontend/components/dashboard/TrendBadge.test.tsx
git commit -m "feat(dashboard): add TrendBadge component, real trend or nothing"
```

---

### Task 5: Frontend — `HeroSparkline` component

**Files:**
- Create: `frontend/components/dashboard/HeroSparkline.tsx`

**Interfaces:**
- Produces: `HeroSparkline({ data, dataKey, color }: { data: { day: string; count: number }[]; dataKey: "count"; color: string })` — renders a real recharts `AreaChart` with no axes/grid/tooltip, sized for a card corner. Renders nothing when `data` is empty (never a placeholder curve).
- Consumed by: `PipelinePulse.tsx` (Task 6)

- [ ] **Step 1: Write the implementation**

No unit test for this one — it's a thin recharts wrapper; correctness is verified visually in Task 10's Playwright pass, consistent with how `/dashboard/analytics`'s own recharts usage is untested at the unit level.

```tsx
"use client";
import { AreaChart, Area, ResponsiveContainer } from "recharts";

interface HeroSparklineProps {
  data: { day: string; count: number }[];
  color: string;
  gradientId: string;
}

export function HeroSparkline({ data, color, gradientId }: HeroSparklineProps) {
  if (data.length === 0) return null;

  return (
    <ResponsiveContainer width={96} height={40}>
      <AreaChart data={data} margin={{ top: 2, right: 2, bottom: 2, left: 2 }}>
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor={color} stopOpacity={0.25} />
            <stop offset="95%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <Area
          type="monotone"
          dataKey="count"
          stroke={color}
          fill={`url(#${gradientId})`}
          strokeWidth={2.5}
          dot={false}
          isAnimationActive={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npm run typecheck`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
cd "/Users/prem/Documents/Aira AI"
git add frontend/components/dashboard/HeroSparkline.tsx
git commit -m "feat(dashboard): add HeroSparkline, real recharts data or nothing"
```

---

### Task 6: Frontend — `PipelinePulse` hero row

**Files:**
- Create: `frontend/components/dashboard/PipelinePulse.tsx`

**Interfaces:**
- Consumes: `AnalyticsOverview` (Task 3), `TrendBadge` (Task 4), `HeroSparkline` (Task 5)
- Produces: `PipelinePulse({ overview }: { overview: AnalyticsOverview })`
- Consumed by: `DashboardClient.tsx` (Task 10)

- [ ] **Step 1: Write the implementation**

```tsx
import { MessageSquare, TrendingUp, CheckCircle2 } from "lucide-react";
import { AnalyticsOverview } from "@/lib/api";
import { TrendBadge } from "./TrendBadge";
import { HeroSparkline } from "./HeroSparkline";

interface HeroCardProps {
  icon: React.ReactNode;
  iconGradient: string;
  glowColor: string;
  label: string;
  value: number;
  sparklineData: { day: string; count: number }[];
  sparklineColor: string;
  gradientId: string;
  trendPct: number | null;
  trendLabel: string;
}

function HeroCard({
  icon, iconGradient, glowColor, label, value,
  sparklineData, sparklineColor, gradientId, trendPct, trendLabel,
}: HeroCardProps) {
  return (
    <div className="group relative overflow-hidden card rounded-[32px] p-8 flex flex-col justify-between hover:-translate-y-1 hover:shadow-md transition-all duration-300">
      <div className={`absolute top-0 right-0 -mt-4 -mr-4 w-32 h-32 rounded-full ${glowColor} blur-2xl transition-all duration-300`} />
      <div>
        <div className="flex items-center justify-between mb-6">
          <div className={`w-11 h-11 rounded-full ${iconGradient} text-white flex items-center justify-center shadow-md`}>
            {icon}
          </div>
          <HeroSparkline data={sparklineData} color={sparklineColor} gradientId={gradientId} />
        </div>
        <div className="text-xs font-semibold text-ink-muted uppercase tracking-wider">{label}</div>
        <div className="font-mono font-bold text-[40px] text-ink tracking-tight leading-none mt-2">
          {value}
        </div>
      </div>
      <TrendBadge pct={trendPct} label={trendLabel} />
    </div>
  );
}

export function PipelinePulse({ overview }: { overview: AnalyticsOverview }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
      <HeroCard
        icon={<MessageSquare size={18} />}
        iconGradient="bg-gradient-to-tr from-emerald-500 to-teal-400"
        glowColor="bg-emerald-500/5 group-hover:bg-emerald-500/10"
        label="Total Leads"
        value={overview.total_leads}
        sparklineData={overview.daily_leads}
        sparklineColor="#10b981"
        gradientId="totalLeadsGrad"
        trendPct={overview.daily_leads_trend_pct}
        trendLabel="new leads vs last week"
      />
      <HeroCard
        icon={<TrendingUp size={18} />}
        iconGradient="bg-gradient-to-tr from-amber-500 to-orange-500"
        glowColor="bg-amber-500/5 group-hover:bg-amber-500/10"
        label="New Hot Leads (7d)"
        value={overview.new_hot_leads_7d}
        sparklineData={overview.new_hot_leads_7d_daily}
        sparklineColor="#f59e0b"
        gradientId="hotLeadsGrad"
        trendPct={overview.new_hot_leads_7d_trend_pct}
        trendLabel="vs last week"
      />
      <HeroCard
        icon={<CheckCircle2 size={18} />}
        iconGradient="bg-gradient-to-tr from-violet-600 to-purple-500"
        glowColor="bg-violet-500/5 group-hover:bg-violet-500/10"
        label="Conversions (7d)"
        value={overview.converted_7d}
        sparklineData={[]}
        sparklineColor="#5b21b6"
        gradientId="conversionsGrad"
        trendPct={overview.converted_7d_trend_pct}
        trendLabel="vs last week"
      />
    </div>
  );
}
```

The Conversions card's `sparklineData` is `[]`, not a derived series — the backend does not return a daily conversions series (only the 7-day total `converted_7d`), and per the Global Constraints no fake data is allowed, so this card intentionally shows its number and trend badge with no sparkline (`HeroSparkline`'s empty-data guard from Task 5 renders nothing for `[]`).

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npm run typecheck`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
cd "/Users/prem/Documents/Aira AI"
git add frontend/components/dashboard/PipelinePulse.tsx
git commit -m "feat(dashboard): add PipelinePulse hero row, real sparklines and trends only"
```

---

### Task 7: Frontend — `AiWorkloadSection` ("Is my AI carrying its weight?")

**Files:**
- Create: `frontend/components/dashboard/AiWorkloadSection.tsx`

**Interfaces:**
- Consumes: `AnalyticsOverview` (Task 3), `api.chatHandovers.count()` (Task 3)
- Produces: `AiWorkloadSection({ overview }: { overview: AnalyticsOverview })`
- Consumed by: `DashboardClient.tsx` (Task 10)

- [ ] **Step 1: Write the implementation**

```tsx
"use client";
import { useEffect, useState } from "react";
import { api, AnalyticsOverview } from "@/lib/api";

export function AiWorkloadSection({ overview }: { overview: AnalyticsOverview }) {
  const [escalations, setEscalations] = useState<number | null>(null);

  useEffect(() => {
    let active = true;
    api.chatHandovers.count()
      .then(res => { if (active) setEscalations(res.count); })
      .catch(() => { if (active) setEscalations(null); });
    return () => { active = false; };
  }, []);

  const totalReplies = overview.ai_vs_human.ai + overview.ai_vs_human.human;
  const aiPct = totalReplies > 0 ? Math.round((overview.ai_vs_human.ai / totalReplies) * 100) : 0;
  const today = overview.daily_messages[overview.daily_messages.length - 1];

  return (
    <div className="card rounded-[32px] p-8">
      <h2 className="font-display font-bold text-ink mb-6 text-[18px]">
        Is my AI carrying its weight?
      </h2>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-6 divide-x divide-[#f0ece4]">
        <div>
          <div className="text-xs font-semibold text-ink-muted uppercase tracking-wider">AI Auto-Reply Share</div>
          <div className="font-display font-bold text-[32px] text-ink tracking-tight mt-2">{aiPct}%</div>
          <div className="text-xs text-ink-muted mt-1 font-medium">
            {overview.ai_vs_human.ai} AI · {overview.ai_vs_human.human} human
          </div>
        </div>
        <div className="pl-6">
          <div className="text-xs font-semibold text-ink-muted uppercase tracking-wider">Inbound Today</div>
          <div className="font-display font-bold text-[32px] text-ink tracking-tight mt-2">{today?.inbound ?? 0}</div>
        </div>
        <div className="pl-6">
          <div className="text-xs font-semibold text-ink-muted uppercase tracking-wider">Outbound Today</div>
          <div className="font-display font-bold text-[32px] text-ink tracking-tight mt-2">{today?.outbound ?? 0}</div>
        </div>
        <div className="pl-6">
          <div className="text-xs font-semibold text-ink-muted uppercase tracking-wider">Escalations Awaiting Human</div>
          <div className={`font-display font-bold text-[32px] tracking-tight mt-2 ${(escalations ?? 0) > 0 ? "text-rose-600" : "text-ink"}`}>
            {escalations ?? "—"}
          </div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npm run typecheck`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
cd "/Users/prem/Documents/Aira AI"
git add frontend/components/dashboard/AiWorkloadSection.tsx
git commit -m "feat(dashboard): add AiWorkloadSection, replaces DayStrip with real escalation count"
```

---

### Task 8: Frontend — `LeadSourceSection` ("Where are leads coming from?")

**Files:**
- Create: `frontend/components/dashboard/LeadSourceSection.tsx`

**Interfaces:**
- Consumes: `AnalyticsOverview.channel_breakdown`, `.ad_attributed_leads`, `.total_leads` (Task 3)
- Produces: `LeadSourceSection({ overview }: { overview: AnalyticsOverview })`
- Consumed by: `DashboardClient.tsx` (Task 10)

- [ ] **Step 1: Write the implementation**

```tsx
import { AnalyticsOverview } from "@/lib/api";

const CHANNEL_LABELS: Record<string, string> = {
  whatsapp: "WhatsApp",
  instagram: "Instagram",
  facebook: "Facebook",
  telegram: "Telegram",
  upload: "Upload",
  manual: "Manual",
};

export function LeadSourceSection({ overview }: { overview: AnalyticsOverview }) {
  const breakdown = overview.channel_breakdown;
  const total = Object.values(breakdown).reduce((a, b) => a + b, 0);
  const entries = (Object.entries(breakdown) as [string, number][])
    .filter(([, count]) => count > 0)
    .sort((a, b) => b[1] - a[1]);

  const adAttributedPct = overview.total_leads > 0
    ? Math.round((overview.ad_attributed_leads / overview.total_leads) * 100)
    : 0;

  if (total === 0) {
    return (
      <div className="card rounded-[32px] p-8">
        <h2 className="font-display font-bold text-ink mb-2 text-[18px]">Where are leads coming from?</h2>
        <p className="text-sm text-ink-muted">No leads yet.</p>
      </div>
    );
  }

  return (
    <div className="card rounded-[32px] p-8">
      <h2 className="font-display font-bold text-ink mb-6 text-[18px]">Where are leads coming from?</h2>
      <div className="space-y-3">
        {entries.map(([channel, count]) => {
          const pct = total ? Math.round((count / total) * 100) : 0;
          return (
            <div key={channel} className="flex items-center gap-3">
              <div className="w-24 text-xs font-semibold text-ink-secondary">{CHANNEL_LABELS[channel] ?? channel}</div>
              <div className="flex-1 h-2 rounded-full bg-surface-mid overflow-hidden">
                <div className="h-full bg-[#5b21b6]" style={{ width: `${pct}%` }} />
              </div>
              <div className="w-16 text-right text-xs font-mono text-ink-muted">{count} · {pct}%</div>
            </div>
          );
        })}
      </div>
      <div className="mt-5 pt-5 border-t border-[#f0ece4] flex items-center justify-between">
        <span className="text-xs font-semibold text-ink-muted uppercase tracking-wider">Ad-attributed</span>
        <span className="text-sm font-mono font-semibold text-ink">
          {overview.ad_attributed_leads} of {overview.total_leads} ({adAttributedPct}%)
        </span>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npm run typecheck`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
cd "/Users/prem/Documents/Aira AI"
git add frontend/components/dashboard/LeadSourceSection.tsx
git commit -m "feat(dashboard): add LeadSourceSection using channel_breakdown and ad_attributed_leads"
```

---

### Task 9: Frontend — adaptive `TeamCallsSection` and `AdSpendSection`

**Files:**
- Create: `frontend/components/dashboard/TeamCallsSection.tsx`
- Create: `frontend/components/dashboard/AdSpendSection.tsx`

**Interfaces:**
- Consumes: `api.analytics.telecalling()` (existing, `frontend/lib/api.ts:1413`), `api.analytics.adPerformance()` (existing, `frontend/lib/api.ts:1411`)
- Produces: `TeamCallsSection()` (no props — fetches its own data, only rendered when the caller already knows `enabledFeatures.includes("telecalling")`), `AdSpendSection()` (fetches `adPerformance()`, renders `null` internally when `campaigns.length === 0`)
- Consumed by: `DashboardClient.tsx` (Task 10)

- [ ] **Step 1: Write `TeamCallsSection`**

```tsx
"use client";
import { useEffect, useState } from "react";
import { api, TelecallingAnalytics } from "@/lib/api";

export function TeamCallsSection() {
  const [data, setData] = useState<TelecallingAnalytics | null>(null);

  useEffect(() => {
    let active = true;
    api.analytics.telecalling().then(res => { if (active) setData(res); }).catch(() => {});
    return () => { active = false; };
  }, []);

  if (!data) return null;

  return (
    <div className="card rounded-[32px] p-8">
      <h2 className="font-display font-bold text-ink mb-6 text-[18px]">Team &amp; Calls</h2>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-6 divide-x divide-[#f0ece4]">
        <div>
          <div className="text-xs font-semibold text-ink-muted uppercase tracking-wider">Calls Today</div>
          <div className="font-display font-bold text-[32px] text-ink tracking-tight mt-2">{data.calls_today}</div>
        </div>
        <div className="pl-6">
          <div className="text-xs font-semibold text-ink-muted uppercase tracking-wider">Calls This Week</div>
          <div className="font-display font-bold text-[32px] text-ink tracking-tight mt-2">{data.calls_this_week}</div>
        </div>
        <div className="pl-6">
          <div className="text-xs font-semibold text-ink-muted uppercase tracking-wider">Converted</div>
          <div className="font-display font-bold text-[32px] text-ink tracking-tight mt-2">{data.outcome_breakdown.converted}</div>
        </div>
        <div className="pl-6">
          <div className="text-xs font-semibold text-ink-muted uppercase tracking-wider">Callback</div>
          <div className="font-display font-bold text-[32px] text-ink tracking-tight mt-2">{data.outcome_breakdown.callback}</div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Write `AdSpendSection`**

```tsx
"use client";
import { useEffect, useState } from "react";
import { api, AdPerformanceSummary } from "@/lib/api";

export function AdSpendSection() {
  const [data, setData] = useState<AdPerformanceSummary | null>(null);

  useEffect(() => {
    let active = true;
    api.analytics.adPerformance().then(res => { if (active) setData(res); }).catch(() => {});
    return () => { active = false; };
  }, []);

  if (!data || data.campaigns.length === 0) return null;

  return (
    <div className="card rounded-[32px] p-8">
      <h2 className="font-display font-bold text-ink mb-6 text-[18px]">Ad Spend</h2>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-6 divide-x divide-[#f0ece4]">
        <div>
          <div className="text-xs font-semibold text-ink-muted uppercase tracking-wider">Campaigns</div>
          <div className="font-display font-bold text-[32px] text-ink tracking-tight mt-2">{data.totals.campaigns}</div>
        </div>
        <div className="pl-6">
          <div className="text-xs font-semibold text-ink-muted uppercase tracking-wider">Tracked Leads</div>
          <div className="font-display font-bold text-[32px] text-ink tracking-tight mt-2">{data.totals.tracked_leads}</div>
        </div>
        <div className="pl-6">
          <div className="text-xs font-semibold text-ink-muted uppercase tracking-wider">Conversion Rate</div>
          <div className="font-display font-bold text-[32px] text-ink tracking-tight mt-2">{Math.round(data.totals.conversion_rate * 100)}%</div>
        </div>
        <div className="pl-6">
          <div className="text-xs font-semibold text-ink-muted uppercase tracking-wider">Progressive Rate</div>
          <div className="font-display font-bold text-[32px] text-ink tracking-tight mt-2">{Math.round(data.totals.progressive_rate * 100)}%</div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npm run typecheck`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
cd "/Users/prem/Documents/Aira AI"
git add frontend/components/dashboard/TeamCallsSection.tsx frontend/components/dashboard/AdSpendSection.tsx
git commit -m "feat(dashboard): add adaptive Team & Calls and Ad Spend sections"
```

---

### Task 10: Frontend — rewrite `DashboardClient.tsx` render body

**Files:**
- Modify: `frontend/app/dashboard/DashboardClient.tsx`

**Interfaces:**
- Consumes: `PipelinePulse` (Task 6), `AiWorkloadSection` (Task 7), `LeadSourceSection` (Task 8), `TeamCallsSection` + `AdSpendSection` (Task 9), existing `PipelineBar` (unchanged), `useAuthRole().enabledFeatures` (existing)

- [ ] **Step 1: Remove dead imports and the `TodaySnapshot`/`DayStrip` usage**

Remove `DayStrip` import (line 16), remove the `TodaySnapshot` function (lines 95-106) entirely, remove unused `Sparkles`... no, `Sparkles` is still used in the subscription-empty-state block — keep it. Remove only `TrendingUp` if no longer used directly in this file (it moves into `PipelinePulse`), keep `MessageSquare`/`ArrowRight`/`AlertCircle` as needed by other unchanged blocks in this file.

- [ ] **Step 2: Add new imports**

```tsx
import { PipelinePulse } from "@/components/dashboard/PipelinePulse";
import { AiWorkloadSection } from "@/components/dashboard/AiWorkloadSection";
import { LeadSourceSection } from "@/components/dashboard/LeadSourceSection";
import { TeamCallsSection } from "@/components/dashboard/TeamCallsSection";
import { AdSpendSection } from "@/components/dashboard/AdSpendSection";
```

- [ ] **Step 3: Replace the main return block's body**

Replace everything from `const total = overview?.funnel?.inquiries ?? 0;` through the closing `</div>` of the main return (the old lines 221-366) with:

```tsx
  if (!overview) {
    return <AiraLoader showRetryAfterMs={15000} onRetry={() => window.location.reload()} />;
  }

  return (
    <div className="animate-slide-up space-y-6 select-none">
      <PipelinePulse overview={overview} />

      <AiWorkloadSection overview={overview} />

      <PipelineBar by_segment={overview.by_segment ?? { A: 0, B: 0, C: 0, D: 0 }} />

      <LeadSourceSection overview={overview} />

      {enabledFeatures.includes("telecalling") && <TeamCallsSection />}

      <AdSpendSection />
    </div>
  );
```

(Note: `enabledFeatures` is already destructured from `useAuthRole()` at the top of this component — no new hook needed.)

- [ ] **Step 4: Typecheck and lint**

Run: `cd frontend && npm run typecheck && npm run lint`
Expected: both PASS. Fix any unused-import errors lint surfaces (e.g. drop `TrendingUp`/`cn` if this pass leaves them unused — check first with `grep -n "TrendingUp\|cn(" frontend/app/dashboard/DashboardClient.tsx` before removing).

- [ ] **Step 5: Commit**

```bash
cd "/Users/prem/Documents/Aira AI"
git add frontend/app/dashboard/DashboardClient.tsx
git commit -m "feat(dashboard): redesign home dashboard, remove DayStrip and all fake data"
```

---

### Task 11: Visual verification

**Files:** none (verification only)

- [ ] **Step 1: Start both dev servers**

Run: `cd backend && uvicorn app.main:app --reload` (background), `cd frontend && npm run dev` (background)

- [ ] **Step 2: Run the full backend suite**

Run: `cd backend && venv/bin/python3.14 -m pytest tests/ -q`
Expected: all tests pass.

- [ ] **Step 3: Playwright screenshots against the real Astro Tamil tenant**

Log in as the Astro Tamil owner (tenant `eba3ed94-277c-430f-a992-19bbe855e2f4`) and capture `/dashboard` (respecting the `/aira` `basePath`) at viewport widths 320, 768, 1024, 1440. Confirm:
- Hero row shows real numbers with either a real sparkline+trend badge or, correctly, none when there's no prior-window baseline (do not treat a missing badge as a bug — verify against the actual `/overview` response in the network tab).
- "Is my AI carrying its weight?" shows a real escalations count (cross-check against `/dashboard/conversations`' pending-handover badge — same underlying count).
- "Where are leads coming from?" matches the tenant's actual `channel_breakdown`.
- Team & Calls section presence matches whether `enabled_features` includes `"telecalling"` for this tenant (verify via the tenant's actual `enabled_features` value, not assumed).
- Ad Spend section is absent if Astro Tamil has zero rows in `ad_campaigns` (verify via a live query) — do not report this as a bug if so, it's the adaptive-hide working correctly.

- [ ] **Step 4: Zero-data state check**

If a second, low/no-data tenant is available, load `/dashboard` for it and confirm no section renders a fake fallback (channels/hero cards should show real zeros or hide, never placeholder curves).

- [ ] **Step 5: Report results**

State plainly, with the screenshots, which sections render correctly and which (if any) don't — per the project's Evidence Before Claims rule, do not report this task done without having looked at the rendered screenshots.

---
