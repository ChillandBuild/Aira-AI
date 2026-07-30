# Period Comparison Analytics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a tenant compare any two date periods (this month vs last month, any custom range vs the preceding equal block) and see per-day inbound/outbound leads and messages, in a form a non-technical client understands at a glance.

**Architecture:** All aggregation moves into three Postgres RPCs that return one row per day instead of raw rows — this both enables the feature and fixes a live bug where PostgREST silently caps result sets at 1000 rows (the current 7-day message chart is missing 250 rows; a 30-day view would be missing over half). A pure-Python service layer handles period math, deltas, series alignment and the plain-English summary with zero DB access, so it is fully unit-testable. The frontend adds a Compare tab plus a shared range picker (presets + custom from/to) and renders the approved three-part layout: plain-English header, overlay chart, precise table.

**Tech Stack:** FastAPI + Python 3.11 (backend), Supabase/PostgreSQL (RPCs in SQL), Next.js 14 App Router + TypeScript + Tailwind + Recharts 3.8 (frontend), pytest/unittest + FastAPI TestClient (tests).

## Global Constraints

- **Reporting timezone is IST (`Asia/Kolkata`)** for every day bucket and every period boundary. The existing telecalling endpoint already does this (`IST_OFFSET` in `analytics.py`); overview/messaging/inbound currently use UTC and are wrong by 6.2% of rows. All new code uses IST.
- **Never fetch raw rows to aggregate them in Python.** PostgREST caps results at 1000 rows and returns no error. Aggregate in SQL. This is the root cause of the bug this plan fixes; migration `146_distinct_token_usage_pairs_rpc.sql` sets the precedent.
- **Multi-tenancy:** every RPC takes `p_tenant_id uuid` and filters on it. Every RPC ends with `REVOKE EXECUTE ON FUNCTION public.<name>(...) FROM anon, authenticated;` (Hard Invariant 6).
- **Segment labels are immutable:** A=Hot, B=Warm, C=Cold, D=Disqualified (Hard Invariant 2).
- **Lead score is always an integer 1–10** (Hard Invariant 1).
- **Migrations** are numbered `NNN_name.sql` in `backend/supabase/migrations/`, applied manually to live Supabase (project `ayftynkgmfkaqmmnlmoc`) via the Supabase MCP SQL tool, followed by `NOTIFY pgrst, 'reload schema';`. Latest existing migration is `152`, so this plan uses **153**.
- **Backwards compatibility:** `/analytics/overview` is consumed by the dashboard home (`AiWorkloadSection`, `PipelinePulse`, `LeadSourceSection`) and the operator console client view. Its existing `range` parameter and its entire response shape must keep working unchanged. New parameters are additive and optional.
- **Frontend build:** ESLint `no-unused-vars` fails the Next.js build. No unused imports, no unused variables.
- **Accent colour** is deep violet `#5b21b6`. Current period uses violet; comparison period uses a muted grey `#a8a29e` dashed line.
- **Work directly on the current checkout.** Do not create git worktrees.
- **`inbound` vs `outbound` has two distinct meanings** and both are built here, never conflated:
  - *Messages*: `direction` column — `inbound` = customer→us, `outbound` = us→customer.
  - *Leads*: `source` column — inbound = `whatsapp|instagram|facebook|telegram`, outbound = `upload|manual`.

## Known Data Reality (verified live 2026-07-30)

Implementers should expect these values when testing against the live DB (tenant `eba3ed94-277c-430f-a992-19bbe855e2f4`):

- 290 live leads, **all** `source = 'whatsapp'` → the outbound-leads series is legitimately all zeros today. That is correct output, not a bug.
- 2143 messages total, all `channel = 'whatsapp'`; 1250 in the last 7 days (this is what overflows the 1000 cap).
- Ad spend is live: ₹13,478 across 24 Jun → 29 Jul; 284 of 290 leads are ad-attributed.
- **0 leads have ever been marked converted.** The `converted` metric will read 0 in both periods. Expected.
- June has almost no data (₹83 spend, 0 leads). A "this month vs last month" comparison will look lopsided until 1 August. Use *last 14 days vs previous 14 days* when demoing.

## File Structure

| File | Responsibility |
|---|---|
| `backend/supabase/migrations/153_analytics_comparison_rpcs.sql` | **Create.** Three IST-bucketed aggregate RPCs. |
| `backend/app/services/analytics_compare.py` | **Create.** Pure logic: period resolution, previous-period math, deltas, series alignment, summary sentence, CSV rows. No DB, no network. |
| `backend/app/routes/analytics.py` | **Modify.** Add `GET /compare` and `GET /compare/export`; route `/overview` and `/messaging` message aggregation through the new RPC. |
| `backend/tests/test_analytics_compare_logic.py` | **Create.** Unit tests for the pure service. |
| `backend/tests/test_analytics_compare_routes.py` | **Create.** Route tests with mocked Supabase. |
| `frontend/components/analytics/RangePicker.tsx` | **Create.** Presets + custom from/to. Shared by the page header and the Compare tab. |
| `frontend/app/dashboard/analytics/CompareTab.tsx` | **Create.** The Compare tab and its three colocated sub-components (header, chart, table) — matching how `page.tsx` colocates `KpiCard`/`SectionCard`. |
| `frontend/app/dashboard/analytics/page.tsx` | **Modify.** Register the Compare tab. Currently 694 lines — keep new code out of it. |
| `frontend/lib/api.ts` | **Modify.** Add `ComparePayload` types and `api.analytics.compare` / `exportCompareCsv`. |

---

### Task 1: Aggregation RPCs (migration 153)

Foundation for everything else. Returns one row per day, so a 30-day range returns 30 rows instead of 2143 — the 1000-row cap becomes unreachable.

**Files:**
- Create: `backend/supabase/migrations/153_analytics_comparison_rpcs.sql`

**Interfaces:**
- Consumes: nothing.
- Produces: three RPCs callable via `db.rpc(name, {...})`:
  - `analytics_daily_messages(p_tenant_id uuid, p_start timestamptz, p_end timestamptz, p_channel text DEFAULT NULL)` → rows of `(day date, inbound bigint, outbound bigint, ai bigint, human bigint)`
  - `analytics_daily_leads(p_tenant_id uuid, p_start timestamptz, p_end timestamptz)` → rows of `(day date, inbound bigint, outbound bigint, hot bigint, warm bigint, cold bigint, disqualified bigint)`
  - `analytics_period_summary(p_tenant_id uuid, p_start timestamptz, p_end timestamptz)` → exactly one row of `(new_leads bigint, inbound_leads bigint, outbound_leads bigint, hot bigint, warm bigint, cold bigint, disqualified bigint, avg_score numeric, messages_in bigint, messages_out bigint, ai_replies bigint, human_replies bigint, converted bigint)`

- [ ] **Step 1: Write the migration file**

Create `backend/supabase/migrations/153_analytics_comparison_rpcs.sql`:

```sql
-- 153: IST-bucketed daily aggregates for the analytics comparison feature.
-- Aggregating in SQL (one row per day) instead of selecting raw rows into
-- Python is mandatory here: PostgREST caps result sets at 1000 rows and
-- returns no error, which was silently truncating the messages chart
-- (1250 rows in a 7-day window, 2143 in 30 days). Same reasoning as 146.
-- All day bucketing is Asia/Kolkata to match the telecalling endpoint.

-- p_channel is NULL for "all channels". It exists here (not only on
-- analytics_reply_sources) because /messaging supports a channel filter and
-- the daily series must honour it, not silently return every channel.
CREATE OR REPLACE FUNCTION public.analytics_daily_messages(
  p_tenant_id uuid,
  p_start timestamptz,
  p_end timestamptz,
  p_channel text DEFAULT NULL
)
RETURNS TABLE (
  day date,
  inbound bigint,
  outbound bigint,
  ai bigint,
  human bigint
)
LANGUAGE sql
STABLE
SET search_path = public
AS $$
  SELECT
    (created_at AT TIME ZONE 'Asia/Kolkata')::date AS day,
    count(*) FILTER (WHERE direction = 'inbound')                                   AS inbound,
    count(*) FILTER (WHERE direction = 'outbound')                                  AS outbound,
    count(*) FILTER (WHERE direction = 'outbound' AND is_ai_generated IS TRUE)      AS ai,
    count(*) FILTER (WHERE direction = 'outbound' AND is_ai_generated IS NOT TRUE)  AS human
  FROM messages
  WHERE tenant_id = p_tenant_id
    AND created_at >= p_start
    AND created_at <  p_end
    AND (p_channel IS NULL OR channel = p_channel)
  GROUP BY 1
  ORDER BY 1;
$$;

CREATE OR REPLACE FUNCTION public.analytics_daily_leads(
  p_tenant_id uuid,
  p_start timestamptz,
  p_end timestamptz
)
RETURNS TABLE (
  day date,
  inbound bigint,
  outbound bigint,
  hot bigint,
  warm bigint,
  cold bigint,
  disqualified bigint
)
LANGUAGE sql
STABLE
SET search_path = public
AS $$
  SELECT
    (created_at AT TIME ZONE 'Asia/Kolkata')::date AS day,
    count(*) FILTER (WHERE source IN ('whatsapp','instagram','facebook','telegram')) AS inbound,
    count(*) FILTER (WHERE source IN ('upload','manual'))                            AS outbound,
    count(*) FILTER (WHERE segment = 'A') AS hot,
    count(*) FILTER (WHERE segment = 'B') AS warm,
    count(*) FILTER (WHERE segment = 'C') AS cold,
    count(*) FILTER (WHERE segment = 'D') AS disqualified
  FROM leads
  WHERE tenant_id = p_tenant_id
    AND deleted_at IS NULL
    AND created_at >= p_start
    AND created_at <  p_end
  GROUP BY 1
  ORDER BY 1;
$$;

CREATE OR REPLACE FUNCTION public.analytics_period_summary(
  p_tenant_id uuid,
  p_start timestamptz,
  p_end timestamptz
)
RETURNS TABLE (
  new_leads bigint,
  inbound_leads bigint,
  outbound_leads bigint,
  hot bigint,
  warm bigint,
  cold bigint,
  disqualified bigint,
  avg_score numeric,
  messages_in bigint,
  messages_out bigint,
  ai_replies bigint,
  human_replies bigint,
  converted bigint
)
LANGUAGE sql
STABLE
SET search_path = public
AS $$
  WITH l AS (
    SELECT
      count(*)                                                                        AS new_leads,
      count(*) FILTER (WHERE source IN ('whatsapp','instagram','facebook','telegram')) AS inbound_leads,
      count(*) FILTER (WHERE source IN ('upload','manual'))                            AS outbound_leads,
      count(*) FILTER (WHERE segment = 'A') AS hot,
      count(*) FILTER (WHERE segment = 'B') AS warm,
      count(*) FILTER (WHERE segment = 'C') AS cold,
      count(*) FILTER (WHERE segment = 'D') AS disqualified,
      round(avg(score)::numeric, 2)         AS avg_score
    FROM leads
    WHERE tenant_id = p_tenant_id
      AND deleted_at IS NULL
      AND created_at >= p_start
      AND created_at <  p_end
  ),
  m AS (
    SELECT
      count(*) FILTER (WHERE direction = 'inbound')                                  AS messages_in,
      count(*) FILTER (WHERE direction = 'outbound')                                 AS messages_out,
      count(*) FILTER (WHERE direction = 'outbound' AND is_ai_generated IS TRUE)     AS ai_replies,
      count(*) FILTER (WHERE direction = 'outbound' AND is_ai_generated IS NOT TRUE) AS human_replies
    FROM messages
    WHERE tenant_id = p_tenant_id
      AND created_at >= p_start
      AND created_at <  p_end
  ),
  c AS (
    SELECT count(*) AS converted
    FROM leads
    WHERE tenant_id = p_tenant_id
      AND deleted_at IS NULL
      AND converted_at IS NOT NULL
      AND converted_at >= p_start
      AND converted_at <  p_end
  )
  SELECT
    l.new_leads, l.inbound_leads, l.outbound_leads,
    l.hot, l.warm, l.cold, l.disqualified, l.avg_score,
    m.messages_in, m.messages_out, m.ai_replies, m.human_replies,
    c.converted
  FROM l, m, c;
$$;

REVOKE EXECUTE ON FUNCTION public.analytics_daily_messages(uuid, timestamptz, timestamptz, text) FROM anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.analytics_daily_leads(uuid, timestamptz, timestamptz)    FROM anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.analytics_period_summary(uuid, timestamptz, timestamptz) FROM anon, authenticated;
```

- [ ] **Step 2: Apply the migration to live Supabase**

Use the Supabase MCP `apply_migration` tool against project `ayftynkgmfkaqmmnlmoc` with name `153_analytics_comparison_rpcs` and the full SQL above. Then reload the PostgREST schema cache with `execute_sql`:

```sql
NOTIFY pgrst, 'reload schema';
```

- [ ] **Step 3: Verify the RPC agrees with raw counts and does not truncate**

This is the critical check — it proves the 1000-row bug is gone. Run via Supabase MCP `execute_sql`:

```sql
WITH rpc AS (
  SELECT sum(inbound) i, sum(outbound) o, sum(ai) a, sum(human) h
  FROM analytics_daily_messages(
    'eba3ed94-277c-430f-a992-19bbe855e2f4'::uuid,
    now() - interval '7 days',
    now()
  )
),
raw AS (
  SELECT
    count(*) FILTER (WHERE direction='inbound')  i,
    count(*) FILTER (WHERE direction='outbound') o,
    count(*) FILTER (WHERE direction='outbound' AND is_ai_generated IS TRUE) a,
    count(*) FILTER (WHERE direction='outbound' AND is_ai_generated IS NOT TRUE) h
  FROM messages
  WHERE tenant_id='eba3ed94-277c-430f-a992-19bbe855e2f4'
    AND created_at >= now() - interval '7 days'
)
SELECT rpc.i = raw.i AND rpc.o = raw.o AND rpc.a = raw.a AND rpc.h = raw.h AS matches,
       rpc.i + rpc.o AS rpc_total, raw.i + raw.o AS raw_total
FROM rpc, raw;
```

Expected: `matches = true`, and `rpc_total` around **1250** — comfortably above 1000, which is exactly the point. If `rpc_total` comes back as 1000, the aggregation is not happening server-side and the migration is wrong.

- [ ] **Step 4: Verify the summary RPC returns exactly one row**

```sql
SELECT count(*) AS row_count FROM analytics_period_summary(
  'eba3ed94-277c-430f-a992-19bbe855e2f4'::uuid,
  '2026-07-01 00:00:00+05:30', '2026-08-01 00:00:00+05:30');
```

Expected: `row_count = 1`. Then inspect the row: `new_leads` should be **291**, `hot` **38**, `avg_score` about **6.04**, `converted` **0**.

- [ ] **Step 5: Commit**

```bash
git add backend/supabase/migrations/153_analytics_comparison_rpcs.sql
git commit -m "feat(analytics): add IST daily aggregate RPCs for period comparison"
```

---

### Task 2: Period resolution (pure logic)

Turns a preset name or a custom from/to pair into concrete IST date bounds, and derives the comparison period.

**Files:**
- Create: `backend/app/services/analytics_compare.py`
- Test: `backend/tests/test_analytics_compare_logic.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `PRESETS: tuple[str, ...]` — the valid preset names.
  - `resolve_period(preset: str | None, start: str | None, end: str | None, today: date) -> tuple[date, date]` — returns `(start_date, end_date)` **inclusive** of both ends. Raises `ValueError` on bad input.
  - `previous_period(start: date, end: date, preset: str | None) -> tuple[date, date]` — the comparison window.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_analytics_compare_logic.py`:

```python
"""Unit tests for app/services/analytics_compare.py -- pure period math, no DB."""
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.analytics_compare import resolve_period, previous_period


class ResolvePeriodTests(unittest.TestCase):
    TODAY = date(2026, 7, 30)

    def test_this_month_runs_from_the_first_to_today(self):
        self.assertEqual(
            resolve_period("this_month", None, None, self.TODAY),
            (date(2026, 7, 1), date(2026, 7, 30)),
        )

    def test_last_month_is_the_whole_previous_calendar_month(self):
        self.assertEqual(
            resolve_period("last_month", None, None, self.TODAY),
            (date(2026, 6, 1), date(2026, 6, 30)),
        )

    def test_last_7d_includes_today_and_spans_seven_days(self):
        start, end = resolve_period("last_7d", None, None, self.TODAY)
        self.assertEqual((start, end), (date(2026, 7, 24), date(2026, 7, 30)))
        self.assertEqual((end - start).days + 1, 7)

    def test_last_14d_spans_fourteen_days(self):
        start, end = resolve_period("last_14d", None, None, self.TODAY)
        self.assertEqual((start, end), (date(2026, 7, 17), date(2026, 7, 30)))

    def test_custom_uses_the_supplied_dates(self):
        self.assertEqual(
            resolve_period("custom", "2026-03-05", "2026-03-19", self.TODAY),
            (date(2026, 3, 5), date(2026, 3, 19)),
        )

    def test_custom_without_dates_is_rejected(self):
        with self.assertRaises(ValueError):
            resolve_period("custom", None, None, self.TODAY)

    def test_reversed_custom_range_is_rejected(self):
        with self.assertRaises(ValueError):
            resolve_period("custom", "2026-03-19", "2026-03-05", self.TODAY)

    def test_unknown_preset_is_rejected(self):
        with self.assertRaises(ValueError):
            resolve_period("since_the_dawn_of_time", None, None, self.TODAY)


class PreviousPeriodTests(unittest.TestCase):
    def test_month_preset_compares_to_the_previous_calendar_month(self):
        # July 1-30 vs June 1-30 -- calendar months, not "the 30 days before".
        self.assertEqual(
            previous_period(date(2026, 7, 1), date(2026, 7, 30), "this_month"),
            (date(2026, 6, 1), date(2026, 6, 30)),
        )

    def test_custom_range_compares_to_the_immediately_preceding_equal_block(self):
        # 14 days (Jul 17-30) -> the 14 days before it (Jul 3-16), no overlap.
        self.assertEqual(
            previous_period(date(2026, 7, 17), date(2026, 7, 30), "custom"),
            (date(2026, 7, 3), date(2026, 7, 16)),
        )

    def test_previous_block_never_overlaps_the_current_one(self):
        prev_start, prev_end = previous_period(date(2026, 7, 24), date(2026, 7, 30), "last_7d")
        self.assertLess(prev_end, date(2026, 7, 24))

    def test_single_day_compares_to_the_day_before(self):
        self.assertEqual(
            previous_period(date(2026, 7, 30), date(2026, 7, 30), "custom"),
            (date(2026, 7, 29), date(2026, 7, 29)),
        )
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_analytics_compare_logic.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.analytics_compare'`

- [ ] **Step 3: Write the implementation**

Create `backend/app/services/analytics_compare.py`:

```python
"""Pure logic for the analytics period-comparison feature.

No DB, no network, no clock reads -- `today` is always passed in so every
function is deterministic and unit-testable. All dates are IST calendar
dates; the caller converts them to timestamptz bounds.
"""

from datetime import date, timedelta

PRESETS = (
    "this_month",
    "last_month",
    "this_week",
    "last_week",
    "last_7d",
    "last_14d",
    "last_30d",
    "custom",
)

# Presets whose natural comparison is the previous *calendar* month rather
# than "the same number of days, immediately before".
_MONTH_PRESETS = ("this_month", "last_month")


def _first_of_month(d: date) -> date:
    return d.replace(day=1)


def _last_of_month(d: date) -> date:
    return _first_of_month(_next_month(d)) - timedelta(days=1)


def _next_month(d: date) -> date:
    return d.replace(day=28) + timedelta(days=4)


def _prev_month(d: date) -> date:
    return _first_of_month(d) - timedelta(days=1)


def resolve_period(
    preset: str | None,
    start: str | None,
    end: str | None,
    today: date,
) -> tuple[date, date]:
    """Resolve a preset (or an explicit start/end pair) to inclusive IST dates."""
    preset = preset or "last_7d"
    if preset not in PRESETS:
        raise ValueError(f"Unknown preset: {preset}")

    if preset == "custom":
        if not start or not end:
            raise ValueError("custom range requires both start and end")
        try:
            start_date = date.fromisoformat(start)
            end_date = date.fromisoformat(end)
        except ValueError as exc:
            raise ValueError("start and end must be YYYY-MM-DD") from exc
        if end_date < start_date:
            raise ValueError("end must not be earlier than start")
        return start_date, end_date

    if preset == "this_month":
        return _first_of_month(today), today
    if preset == "last_month":
        prev = _prev_month(today)
        return _first_of_month(prev), _last_of_month(prev)
    if preset == "this_week":
        return today - timedelta(days=today.weekday()), today
    if preset == "last_week":
        this_monday = today - timedelta(days=today.weekday())
        last_monday = this_monday - timedelta(days=7)
        return last_monday, last_monday + timedelta(days=6)

    days = {"last_7d": 7, "last_14d": 14, "last_30d": 30}[preset]
    return today - timedelta(days=days - 1), today


def previous_period(
    start: date,
    end: date,
    preset: str | None,
) -> tuple[date, date]:
    """The comparison window for a resolved period.

    Month presets compare to the previous calendar month (what a client
    means by "last month"). Everything else compares to the immediately
    preceding block of the same length, which never overlaps the current one.
    """
    if preset in _MONTH_PRESETS:
        prev = _prev_month(start)
        return _first_of_month(prev), _last_of_month(prev)

    span_days = (end - start).days + 1
    prev_end = start - timedelta(days=1)
    return prev_end - timedelta(days=span_days - 1), prev_end
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_analytics_compare_logic.py -v`
Expected: PASS — 12 tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/analytics_compare.py backend/tests/test_analytics_compare_logic.py
git commit -m "feat(analytics): add period resolution and previous-period math"
```

---

### Task 3: Deltas and series alignment (pure logic)

Two periods can have different lengths (July has 31 days, June 30). The overlay chart therefore plots by **day index**, not calendar date, so the two lines are comparable.

**Files:**
- Modify: `backend/app/services/analytics_compare.py`
- Test: `backend/tests/test_analytics_compare_logic.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `pct_delta(current: float | None, previous: float | None) -> float | None` — rounded whole-number percentage change; `None` when there is no meaningful baseline.
  - `fill_days(rows: list[dict], start: date, end: date, keys: tuple[str, ...]) -> list[dict]` — expands sparse RPC rows into one entry per calendar day, zero-filling gaps. Each entry is `{"day": "YYYY-MM-DD", <key>: int, ...}`.
  - `align_series(current: list[dict], previous: list[dict], key: str) -> list[dict]` — entries of `{"index": int, "label": str, "current_day": str | None, "current": int | None, "previous_day": str | None, "previous": int | None}`.
  - `build_deltas(current: dict, previous: dict, metrics: tuple[str, ...]) -> dict[str, dict]` — per metric, `{"current": v, "previous": v, "delta_pct": p}`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_analytics_compare_logic.py`:

```python
from app.services.analytics_compare import (
    align_series,
    build_deltas,
    fill_days,
    pct_delta,
)


class PctDeltaTests(unittest.TestCase):
    def test_growth_is_a_positive_whole_percentage(self):
        self.assertEqual(pct_delta(287, 190), 51)

    def test_decline_is_negative(self):
        self.assertEqual(pct_delta(50, 100), -50)

    def test_no_baseline_returns_none_rather_than_infinity(self):
        # 0 -> 287 is not a "% increase", it is new activity.
        self.assertIsNone(pct_delta(287, 0))

    def test_both_zero_returns_none(self):
        self.assertIsNone(pct_delta(0, 0))

    def test_missing_values_return_none(self):
        self.assertIsNone(pct_delta(None, 100))
        self.assertIsNone(pct_delta(100, None))


class FillDaysTests(unittest.TestCase):
    def test_gaps_are_zero_filled(self):
        rows = [{"day": "2026-07-02", "inbound": 5, "outbound": 3}]
        out = fill_days(rows, date(2026, 7, 1), date(2026, 7, 3), ("inbound", "outbound"))
        self.assertEqual(out, [
            {"day": "2026-07-01", "inbound": 0, "outbound": 0},
            {"day": "2026-07-02", "inbound": 5, "outbound": 3},
            {"day": "2026-07-03", "inbound": 0, "outbound": 0},
        ])

    def test_every_day_in_range_is_present(self):
        out = fill_days([], date(2026, 7, 1), date(2026, 7, 31), ("inbound",))
        self.assertEqual(len(out), 31)

    def test_rows_outside_the_range_are_ignored(self):
        rows = [{"day": "2026-06-30", "inbound": 99}]
        out = fill_days(rows, date(2026, 7, 1), date(2026, 7, 1), ("inbound",))
        self.assertEqual(out, [{"day": "2026-07-01", "inbound": 0}])


class AlignSeriesTests(unittest.TestCase):
    def test_series_are_aligned_by_day_index_not_calendar_date(self):
        current = [{"day": "2026-07-01", "v": 10}, {"day": "2026-07-02", "v": 20}]
        previous = [{"day": "2026-06-01", "v": 5}, {"day": "2026-06-02", "v": 7}]
        out = align_series(current, previous, "v")
        self.assertEqual(out[0], {
            "index": 1, "label": "Day 1",
            "current_day": "2026-07-01", "current": 10,
            "previous_day": "2026-06-01", "previous": 5,
        })

    def test_longer_period_leaves_the_shorter_series_empty_at_the_tail(self):
        current = [{"day": "2026-07-01", "v": 1}, {"day": "2026-07-02", "v": 2}]
        previous = [{"day": "2026-06-01", "v": 9}]
        out = align_series(current, previous, "v")
        self.assertEqual(len(out), 2)
        self.assertIsNone(out[1]["previous"])
        self.assertIsNone(out[1]["previous_day"])
        self.assertEqual(out[1]["current"], 2)


class BuildDeltasTests(unittest.TestCase):
    def test_each_metric_carries_both_values_and_the_change(self):
        out = build_deltas({"new_leads": 287}, {"new_leads": 190}, ("new_leads",))
        self.assertEqual(out["new_leads"], {"current": 287, "previous": 190, "delta_pct": 51})

    def test_metric_absent_from_a_period_is_treated_as_zero(self):
        out = build_deltas({}, {"new_leads": 10}, ("new_leads",))
        self.assertEqual(out["new_leads"]["current"], 0)
        self.assertEqual(out["new_leads"]["delta_pct"], -100)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_analytics_compare_logic.py -v`
Expected: FAIL — `ImportError: cannot import name 'align_series'`

- [ ] **Step 3: Write the implementation**

Append to `backend/app/services/analytics_compare.py`:

```python
def pct_delta(current: float | None, previous: float | None) -> float | None:
    """Whole-number percentage change, or None when there is no baseline.

    Mirrors the existing `_pct_trend` semantics in routes/analytics.py: a
    prior window of zero is not a "% increase", it is new activity, and
    dividing by it would misrepresent that.
    """
    if current is None or previous is None:
        return None
    if previous <= 0:
        return None
    return round((current - previous) / previous * 100)


def fill_days(
    rows: list[dict],
    start: date,
    end: date,
    keys: tuple[str, ...],
) -> list[dict]:
    """Expand sparse aggregate rows into one entry per calendar day.

    The RPCs only emit days that had activity; charts need every day so the
    x-axis does not silently compress quiet periods.
    """
    by_day = {str(r.get("day")): r for r in rows}
    out: list[dict] = []
    cursor = start
    while cursor <= end:
        iso = cursor.isoformat()
        row = by_day.get(iso) or {}
        entry: dict = {"day": iso}
        for key in keys:
            entry[key] = int(row.get(key) or 0)
        out.append(entry)
        cursor += timedelta(days=1)
    return out


def align_series(current: list[dict], previous: list[dict], key: str) -> list[dict]:
    """Pair two day series by position so periods of different lengths overlay.

    July has 31 days and June has 30 -- plotting by calendar date would make
    them incomparable, so both are plotted against "Day N of the period".
    """
    length = max(len(current), len(previous))
    out: list[dict] = []
    for i in range(length):
        cur = current[i] if i < len(current) else None
        prev = previous[i] if i < len(previous) else None
        out.append({
            "index": i + 1,
            "label": f"Day {i + 1}",
            "current_day": cur["day"] if cur else None,
            "current": cur[key] if cur else None,
            "previous_day": prev["day"] if prev else None,
            "previous": prev[key] if prev else None,
        })
    return out


def build_deltas(
    current: dict,
    previous: dict,
    metrics: tuple[str, ...],
) -> dict[str, dict]:
    """Per-metric {current, previous, delta_pct} for the comparison table."""
    out: dict[str, dict] = {}
    for metric in metrics:
        cur = current.get(metric) or 0
        prev = previous.get(metric) or 0
        out[metric] = {
            "current": cur,
            "previous": prev,
            "delta_pct": pct_delta(cur, prev),
        }
    return out
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_analytics_compare_logic.py -v`
Expected: PASS — 24 tests total.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/analytics_compare.py backend/tests/test_analytics_compare_logic.py
git commit -m "feat(analytics): add delta computation and day-index series alignment"
```

---

### Task 4: Plain-English summary sentence (pure logic)

The layman-clarity requirement. Deliberately **not** an LLM: this must be deterministic, instant, free, and incapable of inventing a number in front of a client.

**Files:**
- Modify: `backend/app/services/analytics_compare.py`
- Test: `backend/tests/test_analytics_compare_logic.py`

**Interfaces:**
- Consumes: `pct_delta` from Task 3.
- Produces: `build_summary(current: dict, previous: dict, start: date, end: date) -> str`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_analytics_compare_logic.py`:

```python
from app.services.analytics_compare import build_summary


class BuildSummaryTests(unittest.TestCase):
    CURRENT = {
        "new_leads": 287, "hot": 38, "messages_in": 1204,
        "messages_out": 1441, "ai_replies": 1437,
    }
    PREVIOUS = {
        "new_leads": 190, "hot": 31, "messages_in": 890,
        "messages_out": 1102, "ai_replies": 1090,
    }

    def test_summary_states_the_headline_count_and_the_change(self):
        text = build_summary(self.CURRENT, self.PREVIOUS, date(2026, 7, 1), date(2026, 7, 30))
        self.assertIn("287 new leads", text)
        self.assertIn("51%", text)
        self.assertIn("more", text)

    def test_summary_mentions_hot_leads_and_automation(self):
        text = build_summary(self.CURRENT, self.PREVIOUS, date(2026, 7, 1), date(2026, 7, 30))
        self.assertIn("38", text)
        self.assertIn("99%", text)

    def test_decline_is_described_as_fewer_not_more(self):
        text = build_summary({"new_leads": 90}, {"new_leads": 180}, date(2026, 7, 1), date(2026, 7, 30))
        self.assertIn("fewer", text)
        self.assertNotIn("more", text)

    def test_no_baseline_avoids_a_percentage_claim(self):
        text = build_summary({"new_leads": 50}, {"new_leads": 0}, date(2026, 7, 1), date(2026, 7, 30))
        self.assertIn("50 new leads", text)
        self.assertNotIn("%", text.split(".")[0])

    def test_empty_period_reads_as_plain_english_not_a_crash(self):
        text = build_summary({}, {}, date(2026, 7, 1), date(2026, 7, 30))
        self.assertIn("0 new leads", text)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_analytics_compare_logic.py::BuildSummaryTests -v`
Expected: FAIL — `ImportError: cannot import name 'build_summary'`

- [ ] **Step 3: Write the implementation**

Append to `backend/app/services/analytics_compare.py`:

```python
def _fmt_range(start: date, end: date) -> str:
    if start.year == end.year and start.month == end.month:
        return f"{start.day}–{end.day} {start.strftime('%b %Y')}"
    return f"{start.strftime('%d %b')} – {end.strftime('%d %b %Y')}"


def build_summary(current: dict, previous: dict, start: date, end: date) -> str:
    """A deterministic plain-English paragraph describing the period.

    Template with number slots -- never an LLM call. This text is shown to
    the tenant's own clients, so it must be reproducible and incapable of
    hallucinating a figure.
    """
    leads = int(current.get("new_leads") or 0)
    hot = int(current.get("hot") or 0)
    out = int(current.get("messages_out") or 0)
    ai = int(current.get("ai_replies") or 0)

    parts = [f"Between {_fmt_range(start, end)} you got {leads:,} new leads"]

    delta = pct_delta(leads, previous.get("new_leads") or 0)
    if delta is None:
        parts.append(".")
    else:
        direction = "more" if delta >= 0 else "fewer"
        parts.append(f", {abs(delta)}% {direction} than the previous period.")

    if hot:
        parts.append(f" {hot:,} of them were hot leads.")

    if out:
        ai_pct = round(ai / out * 100)
        parts.append(
            f" The AI sent {out:,} replies and handled {ai_pct}% of them on its own."
        )

    return "".join(parts)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_analytics_compare_logic.py -v`
Expected: PASS — 29 tests total.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/analytics_compare.py backend/tests/test_analytics_compare_logic.py
git commit -m "feat(analytics): add deterministic plain-English period summary"
```

---

### Task 5: `GET /api/v1/analytics/compare`

Wires the RPCs and the pure logic into one endpoint.

**Files:**
- Modify: `backend/app/routes/analytics.py` (add after the `/overview` handler, around line 1144)
- Test: `backend/tests/test_analytics_compare_routes.py`

**Interfaces:**
- Consumes: all three RPCs from Task 1; `resolve_period`, `previous_period`, `fill_days`, `align_series`, `build_deltas`, `build_summary` from Tasks 2–4.
- Produces: JSON response consumed by Task 9's `api.analytics.compare`:

```json
{
  "preset": "this_month",
  "current":  {"start": "2026-07-01", "end": "2026-07-30", "label": "1–30 Jul 2026", "summary": {...}},
  "previous": {"start": "2026-06-01", "end": "2026-06-30", "label": "1–30 Jun 2026", "summary": {...}},
  "summary_text": "Between 1–30 Jul 2026 you got 291 new leads...",
  "metrics": {"new_leads": {"current": 291, "previous": 0, "delta_pct": null}, "...": {}},
  "series": {
    "leads_inbound":  [{"index": 1, "label": "Day 1", "current_day": "...", "current": 3, "previous_day": "...", "previous": 0}],
    "leads_outbound": [...],
    "messages_in":    [...],
    "messages_out":   [...]
  }
}
```

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_analytics_compare_routes.py`:

```python
"""Tests for GET /api/v1/analytics/compare -- period comparison endpoint."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_and_role


class AnalyticsCompareTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}
        app.dependency_overrides[get_tenant_and_role] = lambda: {
            "tenant_id": "tenant-1", "role": "owner", "permissions": [],
        }

    def tearDown(self):
        app.dependency_overrides.clear()

    def _mock_db(self, mock_get_db, summaries, daily_leads, daily_messages):
        """summaries/daily_* are lists: index 0 = current period, 1 = previous."""
        db = MagicMock()
        calls = {"n": 0}

        def rpc(name, params):
            result = MagicMock()
            if name == "analytics_period_summary":
                result.execute.return_value = MagicMock(data=summaries.pop(0))
            elif name == "analytics_daily_leads":
                result.execute.return_value = MagicMock(data=daily_leads.pop(0))
            elif name == "analytics_daily_messages":
                result.execute.return_value = MagicMock(data=daily_messages.pop(0))
            else:
                raise AssertionError(f"unexpected rpc {name}")
            calls["n"] += 1
            return result

        db.rpc.side_effect = rpc
        mock_get_db.return_value = db
        return db

    @patch("app.routes.analytics.get_supabase")
    def test_compare_returns_both_periods_with_deltas(self, mock_get_db):
        self._mock_db(
            mock_get_db,
            summaries=[
                [{"new_leads": 20, "inbound_leads": 20, "outbound_leads": 0, "hot": 4,
                  "warm": 6, "cold": 9, "disqualified": 1, "avg_score": 6.0,
                  "messages_in": 100, "messages_out": 120, "ai_replies": 118,
                  "human_replies": 2, "converted": 0}],
                [{"new_leads": 10, "inbound_leads": 10, "outbound_leads": 0, "hot": 2,
                  "warm": 3, "cold": 5, "disqualified": 0, "avg_score": 5.0,
                  "messages_in": 50, "messages_out": 60, "ai_replies": 60,
                  "human_replies": 0, "converted": 0}],
            ],
            daily_leads=[[], []],
            daily_messages=[[], []],
        )
        res = self.client.get("/api/v1/analytics/compare?preset=custom"
                              "&start=2026-07-15&end=2026-07-16")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["current"]["start"], "2026-07-15")
        self.assertEqual(body["previous"]["start"], "2026-07-13")
        self.assertEqual(body["metrics"]["new_leads"]["current"], 20)
        self.assertEqual(body["metrics"]["new_leads"]["previous"], 10)
        self.assertEqual(body["metrics"]["new_leads"]["delta_pct"], 100)

    @patch("app.routes.analytics.get_supabase")
    def test_series_is_zero_filled_for_every_day_in_range(self, mock_get_db):
        self._mock_db(
            mock_get_db,
            summaries=[[{}], [{}]],
            daily_leads=[
                [{"day": "2026-07-16", "inbound": 5, "outbound": 0,
                  "hot": 1, "warm": 2, "cold": 2, "disqualified": 0}],
                [],
            ],
            daily_messages=[[], []],
        )
        res = self.client.get("/api/v1/analytics/compare?preset=custom"
                              "&start=2026-07-15&end=2026-07-16")
        series = res.json()["series"]["leads_inbound"]
        self.assertEqual(len(series), 2)
        self.assertEqual(series[0]["current"], 0)
        self.assertEqual(series[1]["current"], 5)

    @patch("app.routes.analytics.get_supabase")
    def test_invalid_custom_range_returns_400(self, mock_get_db):
        mock_get_db.return_value = MagicMock()
        res = self.client.get("/api/v1/analytics/compare?preset=custom"
                              "&start=2026-07-20&end=2026-07-10")
        self.assertEqual(res.status_code, 400)

    @patch("app.routes.analytics.get_supabase")
    def test_unknown_preset_returns_400(self, mock_get_db):
        mock_get_db.return_value = MagicMock()
        res = self.client.get("/api/v1/analytics/compare?preset=forever")
        self.assertEqual(res.status_code, 400)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && python -m pytest tests/test_analytics_compare_routes.py -v`
Expected: FAIL — 404 on `/api/v1/analytics/compare` (route not defined).

- [ ] **Step 3: Write the implementation**

Add to the imports at the top of `backend/app/routes/analytics.py`:

```python
from app.services.analytics_compare import (
    align_series,
    build_deltas,
    build_summary,
    fill_days,
    previous_period,
    resolve_period,
)
```

Then add this handler after the `/overview` route:

```python
SUMMARY_METRICS = (
    "new_leads", "inbound_leads", "outbound_leads",
    "hot", "warm", "cold", "disqualified", "avg_score",
    "messages_in", "messages_out", "ai_replies", "human_replies", "converted",
)

LEAD_SERIES_KEYS = ("inbound", "outbound", "hot", "warm", "cold", "disqualified")
MESSAGE_SERIES_KEYS = ("inbound", "outbound", "ai", "human")


def _ist_bounds(start: date, end: date) -> tuple[str, str]:
    """Inclusive IST dates -> half-open UTC timestamptz bounds for the RPCs."""
    start_utc = datetime.combine(start, datetime.min.time(), timezone.utc) - IST_OFFSET
    end_utc = datetime.combine(end + timedelta(days=1), datetime.min.time(), timezone.utc) - IST_OFFSET
    return start_utc.isoformat(), end_utc.isoformat()


async def _period_payload(db, tenant_id: str, start: date, end: date) -> dict:
    """Fetch summary + both daily series for one period. Three RPCs, concurrent."""
    start_iso, end_iso = _ist_bounds(start, end)
    params = {"p_tenant_id": tenant_id, "p_start": start_iso, "p_end": end_iso}

    summary_res, leads_res, msgs_res = await asyncio.gather(
        asyncio.to_thread(db.rpc("analytics_period_summary", params).execute),
        asyncio.to_thread(db.rpc("analytics_daily_leads", params).execute),
        asyncio.to_thread(db.rpc("analytics_daily_messages", params).execute),
    )

    summary_rows = summary_res.data or []
    summary = summary_rows[0] if summary_rows else {}

    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "summary": summary,
        "daily_leads": fill_days(leads_res.data or [], start, end, LEAD_SERIES_KEYS),
        "daily_messages": fill_days(msgs_res.data or [], start, end, MESSAGE_SERIES_KEYS),
    }


@router.get("/compare")
async def compare_analytics(
    preset: str = Query("last_7d"),
    start: str | None = Query(None),
    end: str | None = Query(None),
    tenant_id: str = Depends(get_dashboard_analytics_tenant_id),
):
    """Compare a period against its natural predecessor.

    Day bucketing and period boundaries are IST -- this is an India-based
    product and a UTC "day" starts at 05:30 local, which shifts 6% of rows
    into the wrong bucket.
    """
    today_ist = (datetime.now(timezone.utc) + IST_OFFSET).date()
    try:
        cur_start, cur_end = resolve_period(preset, start, end, today_ist)
        prev_start, prev_end = previous_period(cur_start, cur_end, preset)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    db = get_supabase()
    current, previous = await asyncio.gather(
        _period_payload(db, tenant_id, cur_start, cur_end),
        _period_payload(db, tenant_id, prev_start, prev_end),
    )

    cur_sum = current["summary"]
    prev_sum = previous["summary"]

    def series_for(source: str, key: str) -> list[dict]:
        return align_series(current[source], previous[source], key)

    return {
        "preset": preset,
        "current": {
            "start": current["start"], "end": current["end"],
            "summary": cur_sum,
        },
        "previous": {
            "start": previous["start"], "end": previous["end"],
            "summary": prev_sum,
        },
        "summary_text": build_summary(cur_sum, prev_sum, cur_start, cur_end),
        "metrics": build_deltas(cur_sum, prev_sum, SUMMARY_METRICS),
        "series": {
            "leads_inbound": series_for("daily_leads", "inbound"),
            "leads_outbound": series_for("daily_leads", "outbound"),
            "messages_in": series_for("daily_messages", "inbound"),
            "messages_out": series_for("daily_messages", "outbound"),
        },
    }
```

Note: `date`, `datetime`, `timedelta`, `timezone`, `asyncio`, `Query`, `Depends`, `HTTPException` are already imported at the top of `analytics.py` — do not re-import them.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && python -m pytest tests/test_analytics_compare_routes.py -v`
Expected: PASS — 4 tests.

- [ ] **Step 5: Run the whole analytics suite for regressions**

Run: `cd backend && python -m pytest tests/test_analytics_overview.py tests/test_analytics_compare_logic.py tests/test_analytics_compare_routes.py -v`
Expected: PASS, no failures.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routes/analytics.py backend/tests/test_analytics_compare_routes.py
git commit -m "feat(analytics): add /compare endpoint for period-over-period reporting"
```

---

### Task 6: CSV export for the comparison

**Files:**
- Modify: `backend/app/routes/analytics.py`
- Modify: `backend/app/services/analytics_compare.py`
- Test: `backend/tests/test_analytics_compare_logic.py`

**Interfaces:**
- Consumes: `align_series` output from Task 3.
- Produces: `compare_csv_rows(series: dict) -> list[dict]`, `CSV_FIELDNAMES: list[str]`, and route `GET /api/v1/analytics/compare/export`.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_analytics_compare_logic.py`:

```python
from app.services.analytics_compare import compare_csv_rows


class CompareCsvRowsTests(unittest.TestCase):
    SERIES = {
        "leads_inbound": [
            {"index": 1, "label": "Day 1", "current_day": "2026-07-01", "current": 5,
             "previous_day": "2026-06-01", "previous": 2},
        ],
        "leads_outbound": [
            {"index": 1, "label": "Day 1", "current_day": "2026-07-01", "current": 0,
             "previous_day": "2026-06-01", "previous": 0},
        ],
        "messages_in": [
            {"index": 1, "label": "Day 1", "current_day": "2026-07-01", "current": 40,
             "previous_day": "2026-06-01", "previous": 20},
        ],
        "messages_out": [
            {"index": 1, "label": "Day 1", "current_day": "2026-07-01", "current": 45,
             "previous_day": "2026-06-01", "previous": 22},
        ],
    }

    def test_one_row_per_day_index_with_both_periods_side_by_side(self):
        rows = compare_csv_rows(self.SERIES)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["day_index"], 1)
        self.assertEqual(rows[0]["current_date"], "2026-07-01")
        self.assertEqual(rows[0]["current_leads_inbound"], 5)
        self.assertEqual(rows[0]["previous_date"], "2026-06-01")
        self.assertEqual(rows[0]["previous_messages_out"], 22)

    def test_missing_previous_day_becomes_blank_not_a_crash(self):
        series = {k: [dict(v[0], previous_day=None, previous=None)]
                  for k, v in self.SERIES.items()}
        rows = compare_csv_rows(series)
        self.assertEqual(rows[0]["previous_date"], "")
        self.assertEqual(rows[0]["previous_leads_inbound"], "")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && python -m pytest tests/test_analytics_compare_logic.py::CompareCsvRowsTests -v`
Expected: FAIL — `ImportError: cannot import name 'compare_csv_rows'`

- [ ] **Step 3: Write the service function**

Append to `backend/app/services/analytics_compare.py`:

```python
CSV_SERIES_KEYS = ("leads_inbound", "leads_outbound", "messages_in", "messages_out")

CSV_FIELDNAMES = (
    ["day_index", "current_date"]
    + [f"current_{k}" for k in CSV_SERIES_KEYS]
    + ["previous_date"]
    + [f"previous_{k}" for k in CSV_SERIES_KEYS]
)


def compare_csv_rows(series: dict) -> list[dict]:
    """Flatten the aligned series into one CSV row per day index.

    Both periods sit on the same row so the file opens in Excel as a
    ready-made side-by-side comparison. Missing days render as blanks
    rather than zeros -- a day that did not exist is not a day with no
    activity.
    """
    length = max((len(series.get(k) or []) for k in CSV_SERIES_KEYS), default=0)
    rows: list[dict] = []
    for i in range(length):
        first = next(
            (series[k][i] for k in CSV_SERIES_KEYS if i < len(series.get(k) or [])),
            {},
        )
        row: dict = {
            "day_index": first.get("index", i + 1),
            "current_date": first.get("current_day") or "",
            "previous_date": first.get("previous_day") or "",
        }
        for key in CSV_SERIES_KEYS:
            points = series.get(key) or []
            point = points[i] if i < len(points) else {}
            cur = point.get("current")
            prev = point.get("previous")
            row[f"current_{key}"] = "" if cur is None else cur
            row[f"previous_{key}"] = "" if prev is None else prev
        rows.append(row)
    return rows
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && python -m pytest tests/test_analytics_compare_logic.py -v`
Expected: PASS — 31 tests total.

- [ ] **Step 5: Add the export route**

Add to `backend/app/routes/analytics.py` after the `/compare` handler. Extend the existing `analytics_compare` import list with `CSV_FIELDNAMES` and `compare_csv_rows`:

```python
@router.get("/compare/export")
async def export_compare(
    preset: str = Query("last_7d"),
    start: str | None = Query(None),
    end: str | None = Query(None),
    tenant_id: str = Depends(get_dashboard_analytics_tenant_id),
):
    """Same data as /compare, as a CSV the client can open in Excel."""
    payload = await compare_analytics(preset=preset, start=start, end=end, tenant_id=tenant_id)
    rows = compare_csv_rows(payload["series"])

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_FIELDNAMES)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)

    filename = f"comparison_{payload['current']['start']}_vs_{payload['previous']['start']}.csv"
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
```

`io`, `csv` and `StreamingResponse` are already imported at the top of `analytics.py`.

- [ ] **Step 6: Add a route test**

Append to `backend/tests/test_analytics_compare_routes.py`, inside `AnalyticsCompareTests`:

```python
    @patch("app.routes.analytics.get_supabase")
    def test_export_returns_csv_with_a_header_row(self, mock_get_db):
        self._mock_db(
            mock_get_db,
            summaries=[[{}], [{}]],
            daily_leads=[[], []],
            daily_messages=[[], []],
        )
        res = self.client.get("/api/v1/analytics/compare/export?preset=custom"
                              "&start=2026-07-15&end=2026-07-16")
        self.assertEqual(res.status_code, 200)
        self.assertIn("text/csv", res.headers["content-type"])
        body = res.content.decode()
        self.assertIn("day_index,current_date,current_leads_inbound", body)
        self.assertEqual(len(body.strip().splitlines()), 3)  # header + 2 days
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_analytics_compare_routes.py tests/test_analytics_compare_logic.py -v`
Expected: PASS — 5 route tests, 31 logic tests.

- [ ] **Step 8: Commit**

```bash
git add backend/app/routes/analytics.py backend/app/services/analytics_compare.py backend/tests/
git commit -m "feat(analytics): add CSV export for period comparison"
```

---

### Task 7: Fix the 1000-row truncation in `/overview` and `/messaging`

The live bug. `/overview` currently under-reports AI replies as 579 when the true figure is 711, and the dashboard-home AI Workload card inherits the same error. Uses the RPC from Task 1.

**Files:**
- Modify: `backend/app/routes/analytics.py:1056-1089` (overview message loop) and `:1161-1219` (messaging)
- Test: `backend/tests/test_analytics_truncation.py`

**Interfaces:**
- Consumes: `analytics_daily_messages` RPC from Task 1.
- Produces: no contract change. `/overview` and `/messaging` response shapes stay byte-identical — only the numbers become correct.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_analytics_truncation.py`:

```python
"""Regression guard: analytics must aggregate in SQL, never by pulling raw
message rows. PostgREST caps result sets at 1000 and returns no error, which
silently truncated the 7-day message chart (1250 rows) and the AI/human
counts (579 reported vs 711 actual)."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_and_role


class OverviewUsesSqlAggregationTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}
        app.dependency_overrides[get_tenant_and_role] = lambda: {
            "tenant_id": "tenant-1", "role": "owner", "permissions": [],
        }

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("app.routes.analytics.get_supabase")
    def test_overview_never_selects_raw_message_rows(self, mock_get_db):
        db = MagicMock()
        tables_touched = []

        def table(name):
            tables_touched.append(name)
            tbl = MagicMock()
            tbl.select.return_value.eq.return_value.is_.return_value.execute.return_value = MagicMock(data=[])
            tbl.select.return_value.eq.return_value.is_.return_value.gte.return_value.lt.return_value.execute.return_value = MagicMock(data=[])
            chain = tbl.select.return_value.eq.return_value.eq.return_value.gte.return_value
            chain.execute.return_value = MagicMock(data=[])
            chain.lt.return_value.execute.return_value = MagicMock(data=[])
            return tbl

        db.table.side_effect = table
        db.rpc.return_value.execute.return_value = MagicMock(data=[])
        mock_get_db.return_value = db

        res = self.client.get("/api/v1/analytics/overview?range=30d")
        self.assertEqual(res.status_code, 200)
        self.assertNotIn(
            "messages", tables_touched,
            "overview must aggregate messages via RPC, not db.table('messages')",
        )

    @patch("app.routes.analytics.get_supabase")
    def test_overview_ai_counts_come_from_the_rpc(self, mock_get_db):
        db = MagicMock()

        def table(name):
            tbl = MagicMock()
            tbl.select.return_value.eq.return_value.is_.return_value.execute.return_value = MagicMock(data=[])
            tbl.select.return_value.eq.return_value.is_.return_value.gte.return_value.lt.return_value.execute.return_value = MagicMock(data=[])
            chain = tbl.select.return_value.eq.return_value.eq.return_value.gte.return_value
            chain.execute.return_value = MagicMock(data=[])
            chain.lt.return_value.execute.return_value = MagicMock(data=[])
            return tbl

        db.table.side_effect = table
        db.rpc.return_value.execute.return_value = MagicMock(data=[
            {"day": "2026-07-29", "inbound": 186, "outbound": 256, "ai": 256, "human": 0},
            {"day": "2026-07-30", "inbound": 21, "outbound": 23, "ai": 23, "human": 0},
        ])
        mock_get_db.return_value = db

        body = self.client.get("/api/v1/analytics/overview?range=7d").json()
        self.assertEqual(body["ai_vs_human"], {"ai": 279, "human": 0})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && python -m pytest tests/test_analytics_truncation.py -v`
Expected: FAIL — `overview must aggregate messages via RPC, not db.table('messages')`

- [ ] **Step 3: Replace the overview message fetch**

In `backend/app/routes/analytics.py`, delete the `msgs_window` fetch and the `for m in msgs_window` loops (lines ~1056-1089) and replace with an RPC call. `unreplied_24h` still needs per-lead message rows, but only for the last 24 hours — a bounded window well under 1000 rows — so it keeps a targeted `db.table("messages")` read with an explicit `.limit(1000)` and an explicit column list:

```python
    daily_msg_rows = (
        await asyncio.to_thread(
            db.rpc("analytics_daily_messages", {
                "p_tenant_id": tenant_id,
                "p_start": window_start_dt.isoformat(),
                "p_end": now.isoformat(),
            }).execute
        )
    ).data or []

    daily_msgs_map = {d: {"inbound": 0, "outbound": 0, "ai": 0, "human": 0} for d in days_iso}
    ai_count = 0
    human_count = 0
    for row in daily_msg_rows:
        day = str(row.get("day") or "")
        if day in daily_msgs_map:
            daily_msgs_map[day] = {
                "inbound": int(row.get("inbound") or 0),
                "outbound": int(row.get("outbound") or 0),
                "ai": int(row.get("ai") or 0),
                "human": int(row.get("human") or 0),
            }
        ai_count += int(row.get("ai") or 0)
        human_count += int(row.get("human") or 0)

    # ai_handled_today: the bucket for today's IST date.
    today_ist_iso = (now + IST_OFFSET).date().isoformat()
    ai_handled_today = next(
        (int(r.get("ai") or 0) for r in daily_msg_rows if str(r.get("day")) == today_ist_iso),
        0,
    )

    # unreplied_24h needs per-lead rows, but only over 24h -- a bounded set.
    recent_msgs = (
        await asyncio.to_thread(
            db.table("messages")
            .select("direction,created_at,lead_id")
            .eq("tenant_id", tenant_id)
            .gte("created_at", (now - timedelta(hours=24)).isoformat())
            .limit(1000)
            .execute
        )
    ).data or []
```

Then replace the `unreplied_24h` block (the `last_inbound`/`last_outbound` loops at lines ~1090-1110) with this. It iterates `recent_msgs` instead of `msgs_window`, and the `if ts < day_ago_iso: continue` guard is gone because the query is already bounded to 24 hours:

```python
    last_inbound: dict[str, str] = {}
    last_outbound: dict[str, str] = {}
    for m in recent_msgs:
        ts = m.get("created_at") or ""
        lid = m.get("lead_id")
        if not lid:
            continue
        if m.get("direction") == "inbound":
            if ts > last_inbound.get(lid, ""):
                last_inbound[lid] = ts
        elif m.get("direction") == "outbound":
            if ts > last_outbound.get(lid, ""):
                last_outbound[lid] = ts

    unreplied_24h = sum(
        1 for lid, ts in last_inbound.items()
        if last_outbound.get(lid, "") < ts
    )
```

The `day_ago_iso` variable is now unused — delete its assignment.

- [ ] **Step 4: Replace the messaging fetch**

In `messaging_analytics`, the `msgs` raw fetch feeds three things: `daily_messages`, `ai_reply_rate`, and `reply_source_breakdown`. The first two come from `analytics_daily_messages`; the third needs the `reply_source` column, so add a fourth RPC to migration 153 rather than pulling rows:

```sql
CREATE OR REPLACE FUNCTION public.analytics_reply_sources(
  p_tenant_id uuid, p_start timestamptz, p_end timestamptz, p_channel text DEFAULT NULL
)
RETURNS TABLE (reply_source text, is_ai_generated boolean, total bigint)
LANGUAGE sql STABLE SET search_path = public AS $$
  SELECT reply_source, is_ai_generated, count(*)
  FROM messages
  WHERE tenant_id = p_tenant_id
    AND direction = 'outbound'
    AND created_at >= p_start AND created_at < p_end
    AND (p_channel IS NULL OR channel = p_channel)
  GROUP BY 1, 2;
$$;

REVOKE EXECUTE ON FUNCTION public.analytics_reply_sources(uuid, timestamptz, timestamptz, text) FROM anon, authenticated;
```

Apply this addition to live Supabase the same way as Task 1 Step 2, then `NOTIFY pgrst, 'reload schema';`.

Now replace the `msgs` fetch and the `for m in msgs` loop in `messaging_analytics` with:

```python
    rpc_params = {
        "p_tenant_id": tenant_id,
        "p_start": window_start_dt.isoformat(),
        "p_end": now.isoformat(),
        "p_channel": None if channel == "all" else channel,
    }
    daily_rows, reply_source_rows = await asyncio.gather(
        asyncio.to_thread(db.rpc("analytics_daily_messages", rpc_params).execute),
        asyncio.to_thread(db.rpc("analytics_reply_sources", rpc_params).execute),
    )
    daily_rows = daily_rows.data or []
    reply_source_rows = reply_source_rows.data or []

    daily_msgs_map = {d: {"inbound": 0, "outbound": 0} for d in days_iso}
    outbound_total = 0
    outbound_ai = 0
    for row in daily_rows:
        day = str(row.get("day") or "")
        if day in daily_msgs_map:
            daily_msgs_map[day] = {
                "inbound": int(row.get("inbound") or 0),
                "outbound": int(row.get("outbound") or 0),
            }
        outbound_total += int(row.get("outbound") or 0)
        outbound_ai += int(row.get("ai") or 0)
```

Then bucket the reply sources, **adding `reengagement` to the known set** — it is currently 365 messages (29% of outbound) matching no branch and being silently discarded:

```python
    reply_source_counts: dict[str, int] = {
        "ai": 0, "knowledge": 0, "reengagement": 0, "manual": 0, "unknown": 0,
    }
    for row in reply_source_rows:
        source = row.get("reply_source")
        count = int(row.get("total") or 0)
        if source in reply_source_counts:
            reply_source_counts[source] += count
        elif source == "automation":
            reply_source_counts["ai"] += count
        elif source is None:
            key = "unknown" if row.get("is_ai_generated") else "manual"
            reply_source_counts[key] += count
        else:
            # Any future reply_source lands here rather than vanishing.
            reply_source_counts["unknown"] += count
```

The frontend bar must show the new bucket too, or the percentages stay wrong. In `frontend/app/dashboard/analytics/page.tsx`, update `ReplySourceBar` (lines ~320-327) — the total currently omits `reengagement`, so every segment is overstated:

```tsx
function ReplySourceBar({ breakdown }: { breakdown: MessagingAnalytics["reply_source_breakdown"] }) {
  const total =
    breakdown.ai + breakdown.knowledge + breakdown.reengagement + breakdown.manual;
  if (total === 0) return <p className="font-label text-xs text-on-surface-muted">No data</p>;

  const segments = [
    { label: "AI", value: breakdown.ai, color: "bg-primary" },
    { label: "Knowledge Base", value: breakdown.knowledge, color: "bg-blue-400" },
    { label: "Re-engagement", value: breakdown.reengagement, color: "bg-amber-400" },
    { label: "Manual", value: breakdown.manual, color: "bg-[#a8a29e]" },
  ];
```

The rest of the component is unchanged. Add `reengagement: number;` to the `reply_source_breakdown` field of `MessagingAnalytics` in `frontend/lib/api.ts`.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_analytics_truncation.py tests/test_analytics_overview.py -v`
Expected: PASS. If `test_analytics_overview.py` fails, its mocks reference the removed `messages` table chain — update those mocks to stub `db.rpc` instead. Do not weaken the assertions.

- [ ] **Step 6: Verify against live data**

Start the backend (`cd backend && uvicorn app.main:app --reload`), hit `/api/v1/analytics/overview?range=7d` with a valid token, and confirm `ai_vs_human.ai` is now about **711** (not 579) and `daily_messages` has non-zero entries for all seven days. Cross-check with:

```sql
SELECT count(*) FILTER (WHERE direction='outbound' AND is_ai_generated IS TRUE) AS ai
FROM messages
WHERE tenant_id='eba3ed94-277c-430f-a992-19bbe855e2f4'
  AND created_at >= now() - interval '7 days';
```

Also confirm the Channels tab renders a Re-engagement segment and that the four percentages sum to 100.

- [ ] **Step 7: Verify the frontend build**

Run: `cd frontend && npm run typecheck && npm run lint`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/routes/analytics.py backend/supabase/migrations/153_analytics_comparison_rpcs.sql backend/tests/test_analytics_truncation.py frontend/app/dashboard/analytics/page.tsx frontend/lib/api.ts
git commit -m "fix(analytics): aggregate messages in SQL and stop dropping reengagement replies"
```

---

### Task 8: RangePicker component

Presets plus a real custom from/to. Uses native `<input type="date">`, matching `MetaAdsAnalyticsTab` — no new dependency.

**Files:**
- Create: `frontend/components/analytics/RangePicker.tsx`

**Interfaces:**
- Consumes: nothing.
- Produces:
  ```ts
  export type Preset = "this_month" | "last_month" | "this_week" | "last_week"
    | "last_7d" | "last_14d" | "last_30d" | "custom";
  export type RangeValue = { preset: Preset; start: string; end: string };
  export function RangePicker(props: {
    value: RangeValue;
    onChange: (v: RangeValue) => void;
  }): JSX.Element;
  ```
  `start`/`end` are `YYYY-MM-DD` and only meaningful when `preset === "custom"`.

- [ ] **Step 1: Write the component**

Create `frontend/components/analytics/RangePicker.tsx`:

```tsx
"use client";

export type Preset =
  | "this_month" | "last_month" | "this_week" | "last_week"
  | "last_7d" | "last_14d" | "last_30d" | "custom";

export type RangeValue = { preset: Preset; start: string; end: string };

const PRESET_OPTIONS: { id: Preset; label: string }[] = [
  { id: "this_month", label: "This Month" },
  { id: "last_month", label: "Last Month" },
  { id: "this_week", label: "This Week" },
  { id: "last_week", label: "Last Week" },
  { id: "last_7d", label: "7 Days" },
  { id: "last_14d", label: "14 Days" },
  { id: "last_30d", label: "30 Days" },
  { id: "custom", label: "Custom" },
];

export function RangePicker({
  value,
  onChange,
}: {
  value: RangeValue;
  onChange: (v: RangeValue) => void;
}) {
  return (
    <div className="flex flex-col gap-3">
      <div className="-mx-1 overflow-x-auto px-1 pb-1">
        <div className="flex w-max gap-1 rounded-xl bg-surface-low p-1 ring-1 ring-[#c4c7c7]/15">
          {PRESET_OPTIONS.map((option) => (
            <button
              key={option.id}
              onClick={() => onChange({ ...value, preset: option.id })}
              className={`shrink-0 rounded-lg px-3 py-2 font-label text-xs font-semibold transition-colors sm:px-4 ${
                value.preset === option.id
                  ? "bg-surface text-primary shadow-card"
                  : "text-on-surface-muted hover:text-on-surface"
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      {value.preset === "custom" && (
        <div className="flex flex-wrap items-end gap-2.5">
          <div className="w-[150px]">
            <label
              htmlFor="range-from"
              className="mb-1 block font-label text-[9px] font-bold uppercase tracking-wider text-on-surface-muted"
            >
              From
            </label>
            <input
              id="range-from"
              type="date"
              value={value.start}
              max={value.end || undefined}
              onChange={(e) => onChange({ ...value, start: e.target.value })}
              className="h-9 w-full rounded-xl border border-surface-mid bg-white px-3 font-body text-xs font-semibold text-on-surface focus:outline-none focus:ring-2 focus:ring-violet-200"
            />
          </div>
          <div className="w-[150px]">
            <label
              htmlFor="range-to"
              className="mb-1 block font-label text-[9px] font-bold uppercase tracking-wider text-on-surface-muted"
            >
              To
            </label>
            <input
              id="range-to"
              type="date"
              value={value.end}
              min={value.start || undefined}
              onChange={(e) => onChange({ ...value, end: e.target.value })}
              className="h-9 w-full rounded-xl border border-surface-mid bg-white px-3 font-body text-xs font-semibold text-on-surface focus:outline-none focus:ring-2 focus:ring-violet-200"
            />
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify it type-checks and lints**

Run: `cd frontend && npm run typecheck && npm run lint`
Expected: PASS, no errors, no unused-variable warnings.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/analytics/RangePicker.tsx
git commit -m "feat(analytics): add range picker with presets and custom dates"
```

---

### Task 9: API client types and methods

**Files:**
- Modify: `frontend/lib/api.ts` (types near the other analytics types; methods inside the `analytics:` object around line 1437)

**Interfaces:**
- Consumes: the `/compare` response shape from Task 5 and the CSV route from Task 6.
- Produces:
  ```ts
  export type ComparePoint = {
    index: number; label: string;
    current_day: string | null; current: number | null;
    previous_day: string | null; previous: number | null;
  };
  export type CompareMetric = { current: number; previous: number; delta_pct: number | null };
  export type ComparePayload = {
    preset: string;
    current: { start: string; end: string; summary: Record<string, number> };
    previous: { start: string; end: string; summary: Record<string, number> };
    summary_text: string;
    metrics: Record<string, CompareMetric>;
    series: Record<string, ComparePoint[]>;
  };
  api.analytics.compare(params: { preset: string; start?: string; end?: string }): Promise<ComparePayload>
  api.analytics.exportCompareCsv(params: { preset: string; start?: string; end?: string }): Promise<void>
  ```

- [ ] **Step 1: Add the types**

Add near the other analytics types in `frontend/lib/api.ts`:

```ts
export type ComparePoint = {
  index: number;
  label: string;
  current_day: string | null;
  current: number | null;
  previous_day: string | null;
  previous: number | null;
};

export type CompareMetric = {
  current: number;
  previous: number;
  delta_pct: number | null;
};

export type ComparePayload = {
  preset: string;
  current: { start: string; end: string; summary: Record<string, number> };
  previous: { start: string; end: string; summary: Record<string, number> };
  summary_text: string;
  metrics: Record<string, CompareMetric>;
  series: Record<string, ComparePoint[]>;
};
```

- [ ] **Step 2: Add the client methods**

Inside the `analytics:` object in `frontend/lib/api.ts`, alongside `exportTelecallingCsv`:

```ts
    compare: (params: { preset: string; start?: string; end?: string }) => {
      const qs = new URLSearchParams({ preset: params.preset });
      if (params.start) qs.set("start", params.start);
      if (params.end) qs.set("end", params.end);
      return apiFetch<ComparePayload>(`/api/v1/analytics/compare?${qs.toString()}`);
    },
    exportCompareCsv: async (params: { preset: string; start?: string; end?: string }) => {
      const headers = await getAuthHeaders();
      const qs = new URLSearchParams({ preset: params.preset });
      if (params.start) qs.set("start", params.start);
      if (params.end) qs.set("end", params.end);
      const res = await fetch(`${API_URL}/api/v1/analytics/compare/export?${qs.toString()}`, { headers });
      if (!res.ok) throw new Error(`Export failed: ${res.status} ${res.statusText}`);
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "period_comparison.csv";
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    },
```

- [ ] **Step 3: Verify it type-checks**

Run: `cd frontend && npm run typecheck`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "feat(analytics): add compare API client types and methods"
```

---

### Task 10: CompareTab — header, overlay chart, table

The approved three-part layout. Sub-components live in this file, matching how `page.tsx` colocates `KpiCard` and `SectionCard`.

**Files:**
- Create: `frontend/app/dashboard/analytics/CompareTab.tsx`

**Interfaces:**
- Consumes: `RangePicker`/`RangeValue`/`Preset` (Task 8), `api.analytics.compare` / `exportCompareCsv` / `ComparePayload` / `ComparePoint` / `CompareMetric` (Task 9).
- Produces: `export function CompareTab(): JSX.Element`

- [ ] **Step 1: Write the component**

Create `frontend/app/dashboard/analytics/CompareTab.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, Legend,
  ResponsiveContainer, CartesianGrid,
} from "recharts";
import { Download } from "lucide-react";
import { api, ComparePayload, ComparePoint, CompareMetric } from "@/lib/api";
import { RangePicker, RangeValue } from "@/components/analytics/RangePicker";

const CURRENT_COLOR = "#5b21b6";
const PREVIOUS_COLOR = "#a8a29e";

const SERIES_OPTIONS: { id: string; label: string }[] = [
  { id: "leads_inbound", label: "Inbound Leads" },
  { id: "leads_outbound", label: "Outbound Leads" },
  { id: "messages_in", label: "Messages Received" },
  { id: "messages_out", label: "Messages Sent" },
];

const TABLE_ROWS: { key: string; label: string }[] = [
  { key: "new_leads", label: "New leads" },
  { key: "inbound_leads", label: "— came to us" },
  { key: "outbound_leads", label: "— we reached out" },
  { key: "hot", label: "Hot leads" },
  { key: "warm", label: "Warm leads" },
  { key: "cold", label: "Cold leads" },
  { key: "disqualified", label: "Disqualified" },
  { key: "avg_score", label: "Average score" },
  { key: "messages_in", label: "Messages received" },
  { key: "messages_out", label: "Messages sent" },
  { key: "ai_replies", label: "— sent by AI" },
  { key: "human_replies", label: "— sent by a human" },
  { key: "converted", label: "Conversions" },
];

function DeltaBadge({ pct }: { pct: number | null }) {
  if (pct === null) {
    return <span className="font-label text-xs text-on-surface-muted">—</span>;
  }
  const up = pct >= 0;
  return (
    <span
      className={`font-label text-xs font-bold ${up ? "text-emerald-600" : "text-red-600"}`}
    >
      {up ? "▲" : "▼"} {up ? "+" : ""}{pct}%
    </span>
  );
}

function ComparisonHeader({ data }: { data: ComparePayload }) {
  return (
    <div className="rounded-card bg-surface p-5 shadow-card ring-1 ring-[#c4c7c7]/15 sm:p-6">
      <p className="font-display text-lg font-bold leading-snug text-on-surface sm:text-xl">
        {data.summary_text}
      </p>
      <p className="mt-2 font-label text-xs text-on-surface-muted">
        {data.current.start} → {data.current.end}
        {"  vs  "}
        {data.previous.start} → {data.previous.end}
      </p>
    </div>
  );
}

function ComparisonChart({
  points,
  currentLabel,
  previousLabel,
}: {
  points: ComparePoint[];
  currentLabel: string;
  previousLabel: string;
}) {
  return (
    <div role="img" aria-label="Period comparison chart">
      <ResponsiveContainer width="100%" height={280}>
        <LineChart data={points} margin={{ top: 8, right: 8, bottom: 0, left: -20 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0ece4" />
          <XAxis dataKey="label" tick={{ fontSize: 10, fill: "#a8a29e" }} />
          <YAxis allowDecimals={false} tick={{ fontSize: 10, fill: "#a8a29e" }} />
          <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e8e3db" }} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Line
            type="monotone" dataKey="current" name={currentLabel}
            stroke={CURRENT_COLOR} strokeWidth={2.5} dot={false} connectNulls
          />
          <Line
            type="monotone" dataKey="previous" name={previousLabel}
            stroke={PREVIOUS_COLOR} strokeWidth={2} strokeDasharray="5 4" dot={false} connectNulls
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function ComparisonTable({ metrics }: { metrics: Record<string, CompareMetric> }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left">
        <thead>
          <tr className="border-b border-surface-mid">
            {["Metric", "This period", "Previous", "Change"].map((h) => (
              <th
                key={h}
                className="pb-3 pr-4 font-label text-xs font-semibold uppercase tracking-wider text-on-surface-muted"
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {TABLE_ROWS.map((row) => {
            const metric = metrics[row.key];
            if (!metric) return null;
            return (
              <tr key={row.key} className="border-b border-surface-mid/50">
                <td className="py-3 pr-4 font-body text-sm text-on-surface">{row.label}</td>
                <td className="py-3 pr-4 font-display text-sm font-bold text-on-surface">
                  {metric.current.toLocaleString()}
                </td>
                <td className="py-3 pr-4 font-label text-sm text-on-surface-muted">
                  {metric.previous.toLocaleString()}
                </td>
                <td className="py-3 pr-4">
                  <DeltaBadge pct={metric.delta_pct} />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function CompareTab() {
  const [range, setRange] = useState<RangeValue>({
    preset: "last_14d", start: "", end: "",
  });
  const [seriesId, setSeriesId] = useState<string>("leads_inbound");
  const [data, setData] = useState<ComparePayload | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const isIncompleteCustom =
    range.preset === "custom" && (!range.start || !range.end);

  useEffect(() => {
    if (isIncompleteCustom) return;
    let isCurrent = true;
    setData(null);
    setErr(null);
    api.analytics
      .compare({ preset: range.preset, start: range.start, end: range.end })
      .then((d) => { if (isCurrent) setData(d); })
      .catch((e: unknown) => {
        if (isCurrent) setErr(e instanceof Error ? e.message : "Failed to load");
      });
    return () => { isCurrent = false; };
  }, [range.preset, range.start, range.end, isIncompleteCustom]);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <RangePicker value={range} onChange={setRange} />
        <button
          onClick={() =>
            api.analytics.exportCompareCsv({
              preset: range.preset, start: range.start, end: range.end,
            })
          }
          disabled={!data}
          className="flex h-9 shrink-0 items-center gap-1.5 rounded-xl bg-primary px-4 font-label text-xs font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-40"
        >
          <Download size={14} />
          Export CSV
        </button>
      </div>

      {isIncompleteCustom && (
        <p className="font-label text-sm text-on-surface-muted">
          Pick a start and end date to compare.
        </p>
      )}

      {err && (
        <div className="rounded-xl bg-red-50 p-4 font-label text-sm text-red-700 ring-1 ring-red-200">
          {err}
        </div>
      )}

      {!data && !err && !isIncompleteCustom && (
        <div className="h-36 animate-pulse rounded-card bg-surface-mid" />
      )}

      {data && (
        <>
          <ComparisonHeader data={data} />

          <div className="min-w-0 rounded-card bg-surface p-4 shadow-card ring-1 ring-[#c4c7c7]/15 sm:p-6">
            <div className="mb-4 flex flex-wrap gap-2">
              {SERIES_OPTIONS.map((option) => (
                <button
                  key={option.id}
                  onClick={() => setSeriesId(option.id)}
                  className={`rounded-lg px-3 py-1.5 font-label text-xs font-semibold ring-1 transition-colors ${
                    seriesId === option.id
                      ? "bg-primary-light text-primary ring-primary-muted"
                      : "bg-surface text-on-surface-muted ring-[#c4c7c7]/15 hover:text-on-surface"
                  }`}
                >
                  {option.label}
                </button>
              ))}
            </div>
            <ComparisonChart
              points={data.series[seriesId] ?? []}
              currentLabel={`${data.current.start} → ${data.current.end}`}
              previousLabel={`${data.previous.start} → ${data.previous.end}`}
            />
          </div>

          <div className="min-w-0 rounded-card bg-surface p-4 shadow-card ring-1 ring-[#c4c7c7]/15 sm:p-6">
            <h2 className="mb-4 font-display text-base font-bold text-primary">
              Every number, side by side
            </h2>
            <ComparisonTable metrics={data.metrics} />
          </div>
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify it type-checks and lints**

Run: `cd frontend && npm run typecheck && npm run lint`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/dashboard/analytics/CompareTab.tsx
git commit -m "feat(analytics): add compare tab with header, overlay chart and table"
```

---

### Task 11: Wire the tab into the analytics page

**Files:**
- Modify: `frontend/app/dashboard/analytics/page.tsx:33` (Tab type), `:629-634` (TABS), `:670-685` (range pills), `:687-692` (tab content)

**Interfaces:**
- Consumes: `CompareTab` from Task 10.
- Produces: nothing downstream.

- [ ] **Step 1: Add the import and the tab entry**

At the top of `frontend/app/dashboard/analytics/page.tsx`, add:

```tsx
import { CompareTab } from "./CompareTab";
```

Change the `Tab` type on line 33:

```tsx
type Tab = "overview" | "channels" | "templates" | "inbound" | "compare";
```

Add to the `TABS` array:

```tsx
const TABS: { id: Tab; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "compare", label: "Compare" },
  { id: "channels", label: "Channels" },
  { id: "inbound", label: "Inbound" },
  { id: "templates", label: "Templates" },
];
```

- [ ] **Step 2: Render the tab and hide the old range pills on it**

The Compare tab owns its own range control, so the page-level pills must not show while it is active. Wrap the date-range pill block:

```tsx
        {activeTab !== "compare" && (
          <div className="grid grid-cols-3 gap-1 rounded-xl bg-surface-low p-1 ring-1 ring-[#c4c7c7]/15 sm:flex sm:w-fit">
            {RANGES.map((r) => (
              <button
                key={r.id}
                onClick={() => setRange(r.id)}
                className={`rounded-lg px-3 py-2 font-label text-xs font-semibold transition-colors sm:px-4 sm:text-sm ${
                  range === r.id
                    ? "bg-surface text-primary shadow-card"
                    : "text-on-surface-muted hover:text-on-surface"
                }`}
              >
                {r.label}
              </button>
            ))}
          </div>
        )}
```

Add the tab content line alongside the others:

```tsx
      {activeTab === "compare" && <CompareTab />}
```

- [ ] **Step 3: Verify the build is clean**

Run: `cd frontend && npm run typecheck && npm run lint && npm run build`
Expected: PASS on all three. A failing `npm run build` blocks deploy — do not proceed until green.

- [ ] **Step 4: Verify in the browser and LOOK at it**

Start both servers (`cd backend && uvicorn app.main:app --reload`, `cd frontend && npm run dev`), open `/dashboard/analytics`, click **Compare**, and confirm by screenshot:

1. Default `14 Days` loads and the plain-English sentence names real numbers.
2. Switching to **Custom** reveals two date inputs; picking 2026-07-01 → 2026-07-15 reloads the data.
3. The overlay chart shows a solid violet line and a dashed grey line.
4. Switching the series buttons changes the chart. **Outbound Leads is legitimately flat zero** — all 290 leads are `source = whatsapp`.
5. The table renders every row with a green ▲ or red ▼ or an em-dash.
6. **Export CSV** downloads a file that opens with both periods side by side.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/dashboard/analytics/page.tsx
git commit -m "feat(analytics): wire compare tab into the analytics page"
```

---

## Out of Scope (proposed, awaiting approval — a separate plan)

These were discussed and are **not** built here. Each is a follow-on plan:

- Lead quality mix over time (% hot/warm/cold per day)
- First-response time p50/p90 (verified computable: 10.8s / 26.9s)
- Engagement rate (% of leads who actually replied)
- **The money view** — spend → cost per lead → cost per hot lead (verified: ₹46.03 / ₹352.51 in July)
- **AI value story** — segment movement from `lead_stage_events` (verified: 169 C→B, 66 promoted to hot)
- Hot-lead staleness action list
- IST hour × weekday inbound heatmap
- Making the *existing* Overview/Channels/Inbound tabs accept custom ranges (this plan gives them the RPC foundation but leaves their `range` pills alone)

## Blocker to raise with the user, not solvable in code

**No lead has ever been marked converted** (0 of 291). The conversion endpoints exist ([leads.py:711](../../../backend/app/routes/leads.py), [calls.py:1161](../../../backend/app/routes/calls.py)) but are unused, so the `converted` row in the comparison table will read 0/0 forever and ROI is uncomputable. This is a process decision — who marks a lead converted, and when — not a bug.
