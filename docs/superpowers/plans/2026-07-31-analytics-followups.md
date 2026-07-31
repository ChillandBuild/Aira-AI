# Analytics Follow-Ups Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the remaining gaps on `/dashboard/analytics` identified after the period-comparison feature shipped: fix the last latent silent-truncation bug, add engagement/lead-quality/timing insight, surface a stale-hot-leads action list, and add a date-range filter to the leads API for future drill-down — with zero leftover files, routes, or uncommitted state at any point.

**Architecture:** Same pattern as the existing Compare tab work: aggregate in Postgres (`SECURITY INVOKER` SQL functions, `REVOKE`d from `anon`/`authenticated`, tenant-scoped) rather than pulling raw rows into Python wherever a result set could exceed PostgREST's silent 1000-row cap. New endpoints and RPCs extend `backend/app/routes/analytics.py` and the existing `/compare` machinery in `backend/app/services/analytics_compare.py`; new UI lives in `CompareTab.tsx` and the Overview tab of `frontend/app/dashboard/analytics/page.tsx`.

**Tech Stack:** FastAPI + Supabase Python client (backend), Next.js 14 App Router + TypeScript + Recharts 3.8 (frontend), Postgres/PostgreSQL via Supabase (project `ayftynkgmfkaqmmnlmoc`).

## Global Constraints

- **Migration numbers are not fixed.** The plan text below writes new migrations as `159`, `160`, `161`. Before creating ANY migration file, run `ls backend/supabase/migrations/ | tail -5` and use the true next number. Migration numbering has already collided twice with concurrent work on this repo (see `.agents/decisions/log.md`) — trusting a number written in a plan instead of the live directory is exactly how that happened. If the number on disk has moved past what a task expects, renumber that task's file and update every place its filename is referenced (commit message, comments) before committing.
- **Apply migrations with the Supabase MCP tools, exactly:** `mcp__claude_ai_Supabase__apply_migration` with `project_id: "ayftynkgmfkaqmmnlmoc"`, `name: "<snake_case_description>"`, `query: "<the full SQL file contents>"`. Follow every `apply_migration` call with `mcp__claude_ai_Supabase__execute_sql` running `NOTIFY pgrst, 'reload schema';` against the same `project_id`, then a third `execute_sql` call that proves the function exists and returns sane values for a real tenant in this project (e.g. `SELECT * FROM analytics_period_summary(tenant_id, now() - interval '7 days', now()) ...` for a tenant id you find via `SELECT id FROM tenants LIMIT 1`). Paste that query's actual output as evidence before checking off the step — do not claim a migration "applied successfully" from the `apply_migration` call's own return value alone.
- **Every new or replaced SQL function must be tenant-scoped on `p_tenant_id` and immediately followed by `REVOKE EXECUTE ON FUNCTION ... FROM anon, authenticated;`.** This is a Hard Invariant of this codebase (RLS/multi-tenancy) — copy the exact `REVOKE` line pattern already used in migrations 157/158.
- **No temp file, temp route, or throwaway script survives past the task that created it.** If a task needs a Playwright screenshot or a manual-check route to verify UI work, write the script to `/tmp` (never inside `backend/` or `frontend/`) and delete any temporary route/page from the repo in the same task, before that task's commit. Every task's last step before its commit is `git status --short` — paste the output; it must show only the files that task intentionally changed, nothing else untracked or modified.
- **Evidence, not claims.** Every "tests pass" / "build succeeds" / "endpoint returns X" statement must be backed by the actual command output pasted into the step, obtained by running the command this session — never assumed, never carried over from a previous task's run.
- **Do not run `git push`.** Commit after every task as specified, but leave the final push to the human operator reviewing this work. If you are an autonomous agent with no human in the loop for this session, stop after Task 8's commit and report that push is pending.
- **`/overview`'s response shape and UTC-anchored day bucketing are explicitly out of scope for this plan.** That endpoint is read by the dashboard home page (`frontend/hooks/useApi.ts`, `frontend/app/dashboard/page.tsx`) and the operator console, and its "prior window" trend math, `unreplied_24h`, and `converted_today` fields are all anchored to real wall-clock "now" in ways that don't have an unambiguous meaning under an arbitrary historical custom range. Do not add `start`/`end` params to `/overview` or change its day-bucketing timezone in this plan — file a separate plan if that is wanted later.
- **No worktrees.** Implement directly on the current checkout.
- Commit messages: Conventional Commits, scoped `(analytics)`, matching this repo's existing history (`feat(analytics): ...`, `fix(analytics): ...`).

---

### Task 1: Fix the latent unbounded `leads` table reads (same bug class as the already-fixed messages truncation)

`backend/app/routes/analytics.py` still pulls raw `leads` rows with no pagination in three places: `/funnel` (line ~843, no date filter at all — pulls every lead the tenant has ever had), `/overview` (lines ~955–975, two separate unbounded/partially-bounded fetches), and `/inbound` (line ~1455, bounded below but not paginated). PostgREST silently caps any single `.execute()` at 1000 rows with no error — this is the exact bug already fixed for `messages` in migration 157. The tenant currently has 294 leads, so nothing is truncating today, but the very next lead past 1000 disappears from `/funnel`'s segment/source/score breakdown and `/overview`'s totals with no error anywhere.

The existing Python aggregation logic on top of these fetches (per-lead segment/source/score bucketing, hot-lead aging, per-day counts) is already correct and unit-tested by its callers — the fix is at the fetch layer only: page through with `.range()` until a page comes back short, never rewrite the aggregation logic itself.

**Files:**
- Create: `backend/app/services/pagination.py`
- Create: `backend/tests/test_pagination.py`
- Modify: `backend/app/routes/analytics.py:843-848` (`/funnel`), `:955-975` (`/overview`), `:1453-1462` (`/inbound`)
- Modify: `backend/tests/test_analytics_truncation.py` (`_stub_table` chain must add `.range()`)

**Interfaces:**
- Produces: `async def fetch_all_rows(build_query: Callable[[], Any], page_size: int = 1000) -> list[dict]` in `app.services.pagination` — `build_query` is a zero-arg callable returning a fresh, unexecuted Supabase query builder (already has `.select()`/`.eq()`/etc. chained; must NOT already have `.range()` or `.execute()` called on it). Consumed by every unbounded `leads` fetch in `analytics.py`.

- [ ] **Step 1: Write the failing test for the pagination helper**

Create `backend/tests/test_pagination.py`:

```python
"""Regression guard for the generic Supabase pagination helper: PostgREST
caps any single .execute() at 1000 rows with no error, so any fetch that
could return more than that must page through with .range()."""
import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.pagination import fetch_all_rows


class FakeQueryBuilder:
    """Simulates a Supabase query builder: .range(start, end) returns an
    object whose .execute() yields the next page in sequence."""

    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def range(self, start, end):
        idx = len(self.calls)
        self.calls.append((start, end))
        data = self.pages[idx] if idx < len(self.pages) else []
        result = MagicMock()
        result.execute.return_value = MagicMock(data=data)
        return result


class FetchAllRowsTests(unittest.TestCase):
    def test_stops_after_a_short_page(self):
        pages = [[{"id": i} for i in range(1000)], [{"id": i} for i in range(50)]]
        query = FakeQueryBuilder(pages)

        rows = asyncio.run(fetch_all_rows(lambda: query, page_size=1000))

        self.assertEqual(len(rows), 1050)
        self.assertEqual(query.calls, [(0, 999), (1000, 1999)])

    def test_empty_result_returns_empty_list(self):
        query = FakeQueryBuilder([[]])

        rows = asyncio.run(fetch_all_rows(lambda: query, page_size=1000))

        self.assertEqual(rows, [])
        self.assertEqual(query.calls, [(0, 999)])

    def test_exact_multiple_of_page_size_fetches_one_more_empty_page(self):
        """A tenant with exactly 1000 rows must not be mistaken for having
        more -- the loop must fetch page 2, see it's empty, and stop."""
        pages = [[{"id": i} for i in range(1000)], []]
        query = FakeQueryBuilder(pages)

        rows = asyncio.run(fetch_all_rows(lambda: query, page_size=1000))

        self.assertEqual(len(rows), 1000)
        self.assertEqual(len(query.calls), 2)

    def test_none_data_is_treated_as_an_empty_page(self):
        query = FakeQueryBuilder([None])

        rows = asyncio.run(fetch_all_rows(lambda: query, page_size=1000))

        self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && pytest tests/test_pagination.py -v`
Expected: FAIL / collection error — `app.services.pagination` does not exist yet.

- [ ] **Step 3: Write the pagination helper**

Create `backend/app/services/pagination.py`:

```python
"""Generic Supabase/PostgREST pagination helper.

PostgREST caps result sets at 1000 rows and returns no error or truncation
flag -- silently dropping data past the cap. Any fetch that could return
more than 1000 rows must page through with .range() instead of a single
.execute() call. See migration 157 for the same problem solved via SQL
aggregation instead; use this helper only where the raw rows are genuinely
needed in Python (the aggregation logic already exists and is correct, and
rewriting it into SQL would be the riskier change).
"""
import asyncio
from typing import Any, Callable


async def fetch_all_rows(
    build_query: Callable[[], Any], page_size: int = 1000
) -> list[dict]:
    rows: list[dict] = []
    offset = 0
    while True:
        page = (
            await asyncio.to_thread(
                lambda: build_query().range(offset, offset + page_size - 1).execute()
            )
        ).data or []
        rows.extend(page)
        if len(page) < page_size:
            break
        offset += page_size
    return rows
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && pytest tests/test_pagination.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Wire `fetch_all_rows` into `/funnel`**

In `backend/app/routes/analytics.py`, add the import near the top (alongside the other `app.services` imports at line 18-19):

```python
from app.services.pagination import fetch_all_rows
```

Replace the `/funnel` leads fetch (currently lines 841-848):

```python
    leads_all = (
        await asyncio.to_thread(
            db.table("leads")
            .select("id,segment,source,score,created_at")
            .eq("tenant_id", tenant_id)
            .execute
        )
    ).data or []
```

with:

```python
    leads_all = await fetch_all_rows(
        lambda: db.table("leads")
        .select("id,segment,source,score,created_at")
        .eq("tenant_id", tenant_id)
    )
```

- [ ] **Step 6: Wire `fetch_all_rows` into `/overview`**

Replace the two `/overview` leads fetches (currently lines 955-975):

```python
    leads_rows = (
        await asyncio.to_thread(
            db.table("leads")
            .select("id,phone,segment,score,source,created_at,converted_at,ai_enabled,deleted_at,ad_campaign_id")
            .eq("tenant_id", tenant_id)
            .is_("deleted_at", "null")
            .execute
        )
    ).data or []

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

with:

```python
    leads_rows = await fetch_all_rows(
        lambda: db.table("leads")
        .select("id,phone,segment,score,source,created_at,converted_at,ai_enabled,deleted_at,ad_campaign_id")
        .eq("tenant_id", tenant_id)
        .is_("deleted_at", "null")
    )

    prior_leads_rows = await fetch_all_rows(
        lambda: db.table("leads")
        .select("id,created_at,converted_at")
        .eq("tenant_id", tenant_id)
        .is_("deleted_at", "null")
        .gte("created_at", prior_window_start_dt.isoformat())
        .lt("created_at", window_start_dt.isoformat())
    )
```

- [ ] **Step 7: Wire `fetch_all_rows` into `/inbound`**

Replace the `/inbound` leads fetch (currently lines 1453-1463):

```python
    try:
        rows = await asyncio.to_thread(
            db.table("leads")
            .select("id,source,ad_campaign_id,segment,created_at")
            .eq("tenant_id", tenant_id)
            .in_("source", list(INBOUND_SOURCES))
            .is_("deleted_at", "null")
            .gte("created_at", start_dt.isoformat())
            .execute
        )
        leads = rows.data or []
    except Exception as e:
        logger.error(f"inbound analytics error: {e}")
        leads = []
```

with:

```python
    try:
        leads = await fetch_all_rows(
            lambda: db.table("leads")
            .select("id,source,ad_campaign_id,segment,created_at")
            .eq("tenant_id", tenant_id)
            .in_("source", list(INBOUND_SOURCES))
            .is_("deleted_at", "null")
            .gte("created_at", start_dt.isoformat())
        )
    except Exception as e:
        logger.error(f"inbound analytics error: {e}")
        leads = []
```

- [ ] **Step 8: Fix the existing truncation-regression test's mock chain**

`backend/tests/test_analytics_truncation.py`'s `_stub_table` builds mock chains ending in `.execute` directly; after Step 6, `/overview`'s leads reads go through `.range().execute()`. Update `_stub_table` (currently lines 18-28):

```python
def _stub_table(name):
    """A table mock that answers every chain shape /overview uses."""
    tbl = MagicMock()
    tbl.select.return_value.eq.return_value.is_.return_value.range.return_value.execute.return_value = MagicMock(data=[])
    tbl.select.return_value.eq.return_value.is_.return_value.gte.return_value.lt.return_value.range.return_value.execute.return_value = MagicMock(data=[])
    chain = tbl.select.return_value.eq.return_value.eq.return_value.gte.return_value
    chain.execute.return_value = MagicMock(data=[])
    chain.lt.return_value.execute.return_value = MagicMock(data=[])
    # 24h unreplied window: select -> eq -> gte -> limit -> execute
    tbl.select.return_value.eq.return_value.gte.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
    return tbl
```

- [ ] **Step 9: Run the full backend test suite**

Run: `cd backend && pytest -q`
Expected: PASS, no failures (paste the final summary line — e.g. "705 passed" — as evidence; this repo had 705 passing tests before this task).

- [ ] **Step 10: Verify live against Supabase that pagination doesn't change current totals**

Run `mcp__claude_ai_Supabase__execute_sql` with `project_id: "ayftynkgmfkaqmmnlmoc"` and `query: "SELECT count(*) FROM leads WHERE deleted_at IS NULL;"`. This tenant has well under 1000 leads, so this task cannot be verified end-to-end against a >1000-row tenant — that's expected; the point of this step is only to confirm the refactor didn't change today's numbers. Start the backend (`cd backend && uvicorn app.main:app --reload`) and frontend (`cd frontend && npm run dev`) dev servers, log in as this tenant in a browser (or via Playwright with a real login flow, matching how other tasks in this plan verify UI), and open `/dashboard/analytics` Overview tab. Read "Total Leads" off the KPI card and compare it to the SQL count above — they must match exactly. Paste both numbers.

- [ ] **Step 11: Commit**

```bash
git add backend/app/services/pagination.py backend/tests/test_pagination.py backend/app/routes/analytics.py backend/tests/test_analytics_truncation.py
git status --short
git commit -m "fix(analytics): paginate leads reads in funnel/overview/inbound past the 1000-row PostgREST cap"
```

---

### Task 2: Custom date ranges for `/messaging` and `/inbound`

The Compare tab already supports arbitrary date ranges; the Channels tab (`/messaging`) and the inbound-leads breakdown (`/inbound`) only support the `today`/`7d`/`30d` presets. Add optional `start`/`end` (YYYY-MM-DD) query params to both, additive and backward compatible — omitting them keeps today's exact behavior. `/overview` is explicitly excluded (see Global Constraints).

**Files:**
- Modify: `backend/app/routes/analytics.py` (add `_resolve_window` near `_range_params`; modify `/messaging` and `/inbound` handlers)
- Create: `backend/tests/test_analytics_custom_range.py`

**Interfaces:**
- Consumes: `fetch_all_rows` from Task 1 (used by the updated `/inbound` handler).
- Produces: `def _resolve_window(range_str: str, start: str | None, end: str | None) -> tuple[datetime, datetime, list[str]]` in `app.routes.analytics` — returns `(window_start_utc, window_end_utc, day_iso_list)`. Strict superset of `_range_params`: when `start`/`end` are both absent it returns `_range_params(range_str)`'s start plus `datetime.now(timezone.utc)` as the end, so every existing caller of `_range_params` keeps behaving identically. Raises `ValueError` on a malformed or inverted custom range (caller must convert to `HTTPException(400, ...)`).

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_analytics_custom_range.py`:

```python
"""Tests for optional start/end custom ranges on /messaging and /inbound.
/overview is deliberately excluded -- see the plan's Global Constraints."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_and_role
from app.routes.analytics import _resolve_window


class ResolveWindowTests(unittest.TestCase):
    def test_custom_start_end_builds_a_half_open_utc_window(self):
        start_dt, end_dt, days = _resolve_window("7d", "2026-07-10", "2026-07-12")
        self.assertEqual(start_dt.isoformat(), "2026-07-10T00:00:00+00:00")
        self.assertEqual(end_dt.isoformat(), "2026-07-13T00:00:00+00:00")
        self.assertEqual(days, ["2026-07-10", "2026-07-11", "2026-07-12"])

    def test_end_before_start_raises(self):
        with self.assertRaises(ValueError):
            _resolve_window("7d", "2026-07-12", "2026-07-10")

    def test_malformed_date_raises(self):
        with self.assertRaises(ValueError):
            _resolve_window("7d", "not-a-date", "2026-07-12")

    def test_missing_start_end_falls_back_to_the_preset(self):
        start_dt, end_dt, days = _resolve_window("today", None, None)
        self.assertEqual(len(days), 1)
        self.assertIsNotNone(end_dt)


class MessagingCustomRangeTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}
        app.dependency_overrides[get_tenant_and_role] = lambda: {
            "tenant_id": "tenant-1", "role": "owner", "permissions": [],
        }

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("app.routes.analytics.get_supabase")
    def test_custom_range_passes_exact_bounds_to_the_rpc(self, mock_get_db):
        db = MagicMock()
        db.rpc.return_value.execute.return_value = MagicMock(data=[])
        db.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.return_value = MagicMock(data=[])
        mock_get_db.return_value = db

        res = self.client.get("/api/v1/analytics/messaging?start=2026-07-10&end=2026-07-11")

        self.assertEqual(res.status_code, 200)
        first_call_params = db.rpc.call_args_list[0].args[1]
        self.assertEqual(first_call_params["p_start"], "2026-07-10T00:00:00+00:00")
        self.assertEqual(first_call_params["p_end"], "2026-07-12T00:00:00+00:00")

    @patch("app.routes.analytics.get_supabase")
    def test_invalid_custom_range_returns_400(self, mock_get_db):
        mock_get_db.return_value = MagicMock()
        res = self.client.get("/api/v1/analytics/messaging?start=2026-07-20&end=2026-07-10")
        self.assertEqual(res.status_code, 400)


class InboundCustomRangeTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}
        app.dependency_overrides[get_tenant_and_role] = lambda: {
            "tenant_id": "tenant-1", "role": "owner", "permissions": [],
        }

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("app.routes.analytics.get_supabase")
    def test_custom_range_bounds_the_leads_query_on_both_ends(self, mock_get_db):
        db = MagicMock()
        gte_mock = db.table.return_value.select.return_value.eq.return_value.in_.return_value.is_.return_value.gte
        gte_mock.return_value.lt.return_value.range.return_value.execute.return_value = MagicMock(data=[])
        mock_get_db.return_value = db

        res = self.client.get("/api/v1/analytics/inbound?start=2026-07-10&end=2026-07-11")

        self.assertEqual(res.status_code, 200)
        gte_mock.assert_called_with("created_at", "2026-07-10T00:00:00+00:00")
        gte_mock.return_value.lt.assert_called_with("created_at", "2026-07-12T00:00:00+00:00")

    @patch("app.routes.analytics.get_supabase")
    def test_invalid_custom_range_returns_400(self, mock_get_db):
        mock_get_db.return_value = MagicMock()
        res = self.client.get("/api/v1/analytics/inbound?start=2026-07-20&end=2026-07-10")
        self.assertEqual(res.status_code, 400)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && pytest tests/test_analytics_custom_range.py -v`
Expected: FAIL — `_resolve_window` does not exist yet, and neither endpoint accepts `start`/`end`.

- [ ] **Step 3: Add `_resolve_window`**

In `backend/app/routes/analytics.py`, add immediately after `_range_params` (after line 81):

```python
def _resolve_window(
    range_str: str, start: str | None, end: str | None
) -> tuple[datetime, datetime, list[str]]:
    """Return (window_start_utc, window_end_utc, day_iso_list).

    With both `start` and `end` (YYYY-MM-DD, UTC calendar dates): an
    explicit half-open window, end inclusive of that whole day. Without
    them: falls back to `_range_params`, ending at "now" exactly as before
    -- this is a strict superset, not a replacement, so every existing
    caller's behaviour is unchanged when it doesn't pass start/end.
    """
    if start and end:
        try:
            start_date = date.fromisoformat(start)
            end_date = date.fromisoformat(end)
        except ValueError as exc:
            raise ValueError("start and end must be YYYY-MM-DD") from exc
        if end_date < start_date:
            raise ValueError("end must not be earlier than start")
        window_start_dt = datetime.combine(start_date, datetime.min.time(), timezone.utc)
        window_end_dt = datetime.combine(end_date + timedelta(days=1), datetime.min.time(), timezone.utc)
        days_iso = []
        cursor = start_date
        while cursor <= end_date:
            days_iso.append(cursor.isoformat())
            cursor += timedelta(days=1)
        return window_start_dt, window_end_dt, days_iso

    window_start_dt, days_iso = _range_params(range_str)
    return window_start_dt, datetime.now(timezone.utc), days_iso
```

- [ ] **Step 4: Wire `_resolve_window` into `/messaging`**

Replace the `/messaging` handler signature and window resolution (currently lines 1343-1354, 1358-1363):

```python
@router.get("/messaging")
async def messaging_analytics(
    tenant_id: str = Depends(get_analytics_tenant_id),
    channel: str = Query("all"),
    range: str = Query("7d"),
):
    """Messaging analytics with optional channel filter and date range."""
    db = get_supabase()
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    window_start_dt, days_iso = _range_params(range)

    # Aggregate in SQL -- a raw window fetch hits PostgREST's silent 1000-row
    # cap (1250 rows in 7 days, 2143 in 30).
    rpc_params = {
        "p_tenant_id": tenant_id,
        "p_start": window_start_dt.isoformat(),
        "p_end": now.isoformat(),
        "p_channel": None if channel == "all" else channel,
    }
```

with:

```python
@router.get("/messaging")
async def messaging_analytics(
    tenant_id: str = Depends(get_analytics_tenant_id),
    channel: str = Query("all"),
    range: str = Query("7d"),
    start: str | None = Query(None),
    end: str | None = Query(None),
):
    """Messaging analytics with optional channel filter and date range.

    `start`/`end` (YYYY-MM-DD) override `range` when both are given.
    sent_today/received_today always reflect the real current day regardless
    of range or custom dates -- that is existing, documented behaviour.
    """
    db = get_supabase()
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    try:
        window_start_dt, window_end_dt, days_iso = _resolve_window(range, start, end)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Aggregate in SQL -- a raw window fetch hits PostgREST's silent 1000-row
    # cap (1250 rows in 7 days, 2143 in 30).
    rpc_params = {
        "p_tenant_id": tenant_id,
        "p_start": window_start_dt.isoformat(),
        "p_end": window_end_dt.isoformat(),
        "p_channel": None if channel == "all" else channel,
    }
```

- [ ] **Step 5: Wire `_resolve_window` into `/inbound`**

Replace the `/inbound` handler (currently lines 1443-1467, already updated by Task 1 to use `fetch_all_rows`):

```python
@router.get("/inbound")
async def inbound_analytics(
    range: str = Query("7d"),
    tenant_id: str = Depends(get_analytics_tenant_id),
):
    """New inbound leads acquired, split organic vs ad. Range: today|7d|30d."""
    db = get_supabase()
    start_dt, days_iso = _range_params(range)
    today_iso = datetime.now(timezone.utc).date().isoformat()

    try:
        leads = await fetch_all_rows(
            lambda: db.table("leads")
            .select("id,source,ad_campaign_id,segment,created_at")
            .eq("tenant_id", tenant_id)
            .in_("source", list(INBOUND_SOURCES))
            .is_("deleted_at", "null")
            .gte("created_at", start_dt.isoformat())
        )
    except Exception as e:
        logger.error(f"inbound analytics error: {e}")
        leads = []
    return aggregate_inbound(leads, days_iso, today_iso)
```

with:

```python
@router.get("/inbound")
async def inbound_analytics(
    range: str = Query("7d"),
    start: str | None = Query(None),
    end: str | None = Query(None),
    tenant_id: str = Depends(get_analytics_tenant_id),
):
    """New inbound leads acquired, split organic vs ad. Range: today|7d|30d,
    or pass start/end (YYYY-MM-DD) for an arbitrary window."""
    db = get_supabase()
    try:
        start_dt, end_dt, days_iso = _resolve_window(range, start, end)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    today_iso = datetime.now(timezone.utc).date().isoformat()

    try:
        leads = await fetch_all_rows(
            lambda: db.table("leads")
            .select("id,source,ad_campaign_id,segment,created_at")
            .eq("tenant_id", tenant_id)
            .in_("source", list(INBOUND_SOURCES))
            .is_("deleted_at", "null")
            .gte("created_at", start_dt.isoformat())
            .lt("created_at", end_dt.isoformat())
        )
    except Exception as e:
        logger.error(f"inbound analytics error: {e}")
        leads = []
    return aggregate_inbound(leads, days_iso, today_iso)
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd backend && pytest tests/test_analytics_custom_range.py -v`
Expected: PASS (6 tests)

- [ ] **Step 7: Run the full backend test suite**

Run: `cd backend && pytest -q`
Expected: PASS, no failures (paste the final summary line).

- [ ] **Step 8: Commit**

```bash
git add backend/app/routes/analytics.py backend/tests/test_analytics_custom_range.py
git status --short
git commit -m "feat(analytics): support custom start/end date ranges on messaging and inbound endpoints"
```

---

### Task 3: Engagement rate metric

Add "what fraction of new leads did we actually reply to" to the Compare tab. Fully computed in SQL — no Python logic changes beyond one tuple entry, since `analytics_period_summary` already flows generically through `build_deltas`/`SUMMARY_METRICS`.

**Files:**
- Create: `backend/supabase/migrations/159_analytics_engagement_rate.sql` (verify the number first — see Global Constraints)
- Modify: `backend/app/routes/analytics.py` (`SUMMARY_METRICS` tuple, around line 1198-1202)
- Modify: `backend/tests/test_analytics_compare_routes.py` (new test)
- Modify: `frontend/app/dashboard/analytics/CompareTab.tsx` (`TABLE_ROWS`, around line 24-38)

**Interfaces:**
- Produces: `analytics_period_summary(...)` RPC gains a 14th output column `engagement_rate numeric` (0-100, or `NULL` when `new_leads = 0`). Consumed automatically by `build_deltas` once added to `SUMMARY_METRICS`.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_analytics_compare_routes.py`, as a new test method inside `AnalyticsCompareTests`:

```python
    @patch("app.routes.analytics.get_supabase")
    def test_engagement_rate_flows_through_to_the_metrics_block(self, mock_get_db):
        self._mock_db(
            mock_get_db,
            summaries=[
                [{"new_leads": 20, "engagement_rate": 65}],
                [{"new_leads": 10, "engagement_rate": 50}],
            ],
            daily_leads=[[], []],
            daily_messages=[[], []],
        )
        body = self.client.get(
            "/api/v1/analytics/compare?preset=custom&start=2026-07-15&end=2026-07-16"
        ).json()
        self.assertEqual(body["metrics"]["engagement_rate"]["current"], 65)
        self.assertEqual(body["metrics"]["engagement_rate"]["previous"], 50)
        self.assertEqual(body["metrics"]["engagement_rate"]["delta_pct"], 30)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && pytest tests/test_analytics_compare_routes.py -v -k engagement_rate`
Expected: FAIL — `KeyError: 'engagement_rate'` (not yet in `SUMMARY_METRICS`, so `build_deltas` never emits it).

- [ ] **Step 3: Verify the current migration number, then create the migration**

Run: `ls backend/supabase/migrations/ | tail -5` — confirm the next free number (written below as 159; renumber if the directory has moved past 158).

Create `backend/supabase/migrations/159_analytics_engagement_rate.sql`:

```sql
-- 159: adds engagement_rate to analytics_period_summary -- the fraction of
-- leads created in the period that received at least one outbound reply.
-- Postgres does not allow CREATE OR REPLACE to change a function's return
-- type, so the old signature must be dropped first; this is the same
-- function body as migration 157 plus one new CTE and one new output column.
DROP FUNCTION IF EXISTS public.analytics_period_summary(uuid, timestamptz, timestamptz);

CREATE FUNCTION public.analytics_period_summary(
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
  converted bigint,
  engagement_rate numeric
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
  ),
  e AS (
    -- Leads created in the period that got at least one outbound reply.
    -- Uses idx_messages_lead_outbound_created (migration 158), which already
    -- covers (lead_id, created_at) WHERE direction = 'outbound'.
    SELECT count(*) AS engaged_leads
    FROM leads lead2
    WHERE lead2.tenant_id = p_tenant_id
      AND lead2.deleted_at IS NULL
      AND lead2.created_at >= p_start
      AND lead2.created_at <  p_end
      AND EXISTS (
        SELECT 1 FROM messages msg
        WHERE msg.lead_id = lead2.id AND msg.direction = 'outbound'
      )
  )
  SELECT
    l.new_leads, l.inbound_leads, l.outbound_leads,
    l.hot, l.warm, l.cold, l.disqualified, l.avg_score,
    m.messages_in, m.messages_out, m.ai_replies, m.human_replies,
    c.converted,
    round(e.engaged_leads::numeric / NULLIF(l.new_leads, 0) * 100) AS engagement_rate
  FROM l, m, c, e;
$$;

REVOKE EXECUTE ON FUNCTION public.analytics_period_summary(uuid, timestamptz, timestamptz) FROM anon, authenticated;
```

- [ ] **Step 4: Apply the migration and verify live**

Call `mcp__claude_ai_Supabase__apply_migration` with `project_id: "ayftynkgmfkaqmmnlmoc"`, `name: "analytics_engagement_rate"`, `query: <the full SQL above>`.

Then `mcp__claude_ai_Supabase__execute_sql` with `project_id: "ayftynkgmfkaqmmnlmoc"`, `query: "NOTIFY pgrst, 'reload schema';"`.

Then verify with `mcp__claude_ai_Supabase__execute_sql`, `project_id: "ayftynkgmfkaqmmnlmoc"`, `query: "SELECT id FROM tenants LIMIT 1;"` to get a real tenant id, then `query: "SELECT * FROM analytics_period_summary('<that tenant id>', now() - interval '30 days', now());"`. Paste the row returned — `engagement_rate` must be a number between 0 and 100 (or null if `new_leads` was 0 for that tenant in that window).

- [ ] **Step 5: Add `engagement_rate` to `SUMMARY_METRICS`**

In `backend/app/routes/analytics.py`, modify (currently lines 1198-1202):

```python
SUMMARY_METRICS = (
    "new_leads", "inbound_leads", "outbound_leads",
    "hot", "warm", "cold", "disqualified", "avg_score",
    "messages_in", "messages_out", "ai_replies", "human_replies", "converted",
)
```

to:

```python
SUMMARY_METRICS = (
    "new_leads", "inbound_leads", "outbound_leads",
    "hot", "warm", "cold", "disqualified", "avg_score",
    "messages_in", "messages_out", "ai_replies", "human_replies", "converted",
    "engagement_rate",
)
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `cd backend && pytest tests/test_analytics_compare_routes.py -v`
Expected: PASS (all tests in the file, including the new one).

- [ ] **Step 7: Add the row to the Compare tab's table**

In `frontend/app/dashboard/analytics/CompareTab.tsx`, modify `TABLE_ROWS` (currently lines 24-38) — insert after the `converted` row:

```tsx
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
  { key: "engagement_rate", label: "Engagement rate (% of leads replied to)" },
];
```

- [ ] **Step 8: Run the full backend suite, then typecheck the frontend**

Run: `cd backend && pytest -q`
Expected: PASS, no failures (paste the summary line).

Run: `cd frontend && npm run typecheck`
Expected: no errors.

- [ ] **Step 9: Commit**

```bash
git add backend/supabase/migrations/159_analytics_engagement_rate.sql backend/app/routes/analytics.py backend/tests/test_analytics_compare_routes.py frontend/app/dashboard/analytics/CompareTab.tsx
git status --short
git commit -m "feat(analytics): add engagement rate to the period-comparison metrics"
```

---

### Task 4: Lead quality mix over time (Compare tab)

`analytics_daily_leads` already computes hot/warm/cold/disqualified per day for the current period (via `fill_days` in `_period_payload`) — it's just never returned from `/compare`. Expose it and render a stacked bar chart.

**Files:**
- Modify: `backend/app/routes/analytics.py` (`compare_analytics`, around line 1284-1292)
- Modify: `backend/tests/test_analytics_compare_routes.py` (new test)
- Modify: `frontend/lib/api.ts` (`ComparePeriod` interface, around line 737-744)
- Modify: `frontend/app/dashboard/analytics/CompareTab.tsx` (new `SegmentMixChart` component + render block)

**Interfaces:**
- Consumes: `current["daily_leads"]` (already produced by `_period_payload`, one entry per day with `hot`/`warm`/`cold`/`disqualified` keys — unchanged by this task).
- Produces: `ComparePayload.current.daily_segment_mix: { day: string; hot: number; warm: number; cold: number; disqualified: number }[]`.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_analytics_compare_routes.py`, new test method inside `AnalyticsCompareTests`:

```python
    @patch("app.routes.analytics.get_supabase")
    def test_daily_segment_mix_is_returned_for_the_current_period(self, mock_get_db):
        self._mock_db(
            mock_get_db,
            summaries=[[{}], [{}]],
            daily_leads=[
                [{"day": "2026-07-16", "inbound": 3, "outbound": 0,
                  "hot": 1, "warm": 1, "cold": 1, "disqualified": 0}],
                [],
            ],
            daily_messages=[[], []],
        )
        body = self.client.get(
            "/api/v1/analytics/compare?preset=custom&start=2026-07-15&end=2026-07-16"
        ).json()
        mix = body["current"]["daily_segment_mix"]
        self.assertEqual(len(mix), 2)
        self.assertEqual(mix[1], {"day": "2026-07-16", "hot": 1, "warm": 1, "cold": 1, "disqualified": 0})
        self.assertEqual(mix[0], {"day": "2026-07-15", "hot": 0, "warm": 0, "cold": 0, "disqualified": 0})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && pytest tests/test_analytics_compare_routes.py -v -k daily_segment_mix`
Expected: FAIL — `KeyError: 'daily_segment_mix'`.

- [ ] **Step 3: Add `daily_segment_mix` to the `/compare` response**

In `backend/app/routes/analytics.py`, modify `compare_analytics`'s return statement (currently lines 1284-1315) — add the new key inside `"current"`:

```python
    return {
        "preset": preset,
        "current": {
            "start": current["start"], "end": current["end"],
            "summary": cur_sum,
            "money": current["money"],
            "response": current["response"],
            "movement": current["movement"],
            "daily_segment_mix": [
                {
                    "day": d["day"], "hot": d["hot"], "warm": d["warm"],
                    "cold": d["cold"], "disqualified": d["disqualified"],
                }
                for d in current["daily_leads"]
            ],
        },
        "previous": {
            "start": previous["start"], "end": previous["end"],
            "summary": prev_sum,
            "money": previous["money"],
            "response": previous["response"],
            "movement": previous["movement"],
        },
        "summary_text": build_summary(cur_sum, prev_sum, cur_start, cur_end),
        "metrics": build_deltas(cur_sum, prev_sum, SUMMARY_METRICS),
        "money_metrics": build_deltas(current["money"], previous["money"], MONEY_METRICS),
        "response_metrics": build_deltas(
            current["response"], previous["response"], RESPONSE_METRICS
        ),
        "movement_metrics": build_deltas(
            current["movement"], previous["movement"], MOVEMENT_METRICS
        ),
        "series": {
            "leads_inbound": series_for("daily_leads", "inbound"),
            "leads_outbound": series_for("daily_leads", "outbound"),
            "messages_in": series_for("daily_messages", "inbound"),
            "messages_out": series_for("daily_messages", "outbound"),
        },
    }
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && pytest tests/test_analytics_compare_routes.py -v`
Expected: PASS (all tests in the file).

- [ ] **Step 5: Add the type**

In `frontend/lib/api.ts`, modify `ComparePeriod` (currently lines 737-744):

```typescript
export interface ComparePeriod {
  start: string;
  end: string;
  summary: Record<string, number>;
  money: CompareMoney;
  response: CompareResponseTimes;
  movement: CompareMovement;
  /** Only populated on `current` -- per-day segment counts for the mix chart. */
  daily_segment_mix?: { day: string; hot: number; warm: number; cold: number; disqualified: number }[];
}
```

- [ ] **Step 6: Add the chart component and render block**

In `frontend/app/dashboard/analytics/CompareTab.tsx`, add to the recharts import (currently line 4-7):

```tsx
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, Tooltip, Legend,
  ResponsiveContainer, CartesianGrid,
} from "recharts";
```

Add a new component, after `MovementFlows` (after line 159, before `ComparisonHeader`):

```tsx
const SEGMENT_MIX_COLORS = {
  hot: "#10b981", warm: "#3b82f6", cold: "#f59e0b", disqualified: "#f87171",
} as const;

function SegmentMixChart({
  points,
}: {
  points: ComparePeriod["daily_segment_mix"];
}) {
  if (!points || points.length === 0) {
    return (
      <p className="font-label text-sm text-on-surface-muted">
        No lead activity in this period.
      </p>
    );
  }
  return (
    <div role="img" aria-label="Lead quality mix per day">
      <ResponsiveContainer width="100%" height={240}>
        <BarChart data={points} margin={{ top: 8, right: 8, bottom: 0, left: -20 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0ece4" />
          <XAxis dataKey="day" tick={{ fontSize: 10, fill: "#a8a29e" }} />
          <YAxis allowDecimals={false} tick={{ fontSize: 10, fill: "#a8a29e" }} />
          <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e8e3db" }} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Bar dataKey="hot" stackId="mix" fill={SEGMENT_MIX_COLORS.hot} name="Hot" />
          <Bar dataKey="warm" stackId="mix" fill={SEGMENT_MIX_COLORS.warm} name="Warm" />
          <Bar dataKey="cold" stackId="mix" fill={SEGMENT_MIX_COLORS.cold} name="Cold" />
          <Bar dataKey="disqualified" stackId="mix" fill={SEGMENT_MIX_COLORS.disqualified} name="Disqualified" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
```

Add the import for `ComparePeriod` to the existing `@/lib/api` import (currently lines 9-11):

```tsx
import {
  api, ComparePayload, ComparePeriod, ComparePoint, CompareMetric, CompareMovement,
} from "@/lib/api";
```

Add the render block in the `CompareTab` component, after the "What the AI did with your leads" card (after line 398, before the series-toggle chart card at line 400):

```tsx
          <div className="min-w-0 rounded-card bg-surface p-4 shadow-card ring-1 ring-[#c4c7c7]/15 sm:p-6">
            <h2 className="font-display text-base font-bold text-primary">
              Lead quality mix, day by day
            </h2>
            <p className="mb-4 mt-1 font-label text-xs text-on-surface-muted">
              How many leads landed in each segment on the day they arrived.
            </p>
            <SegmentMixChart points={data.current.daily_segment_mix} />
          </div>
```

- [ ] **Step 7: Verify in the browser**

Start the backend (`cd backend && uvicorn app.main:app --reload`) and frontend (`cd frontend && npm run dev`) dev servers if not already running. Log in and open `/dashboard/analytics`, switch to the Compare tab, pick a preset with lead activity (e.g. "Last 30 days"). Confirm the new "Lead quality mix, day by day" stacked bar chart renders below the movement card with no console errors. Take a screenshot with Playwright saved to `/tmp/compare-segment-mix.png` (NOT inside the repo) and view it to confirm the chart is visually correct before moving on — do not claim this step passed without having looked at the screenshot.

- [ ] **Step 8: Run typecheck, lint, and the backend suite**

Run: `cd frontend && npm run typecheck && npm run lint`
Expected: no errors.

Run: `cd backend && pytest -q`
Expected: PASS, no failures (paste the summary line).

- [ ] **Step 9: Commit**

```bash
git add backend/app/routes/analytics.py backend/tests/test_analytics_compare_routes.py frontend/lib/api.ts frontend/app/dashboard/analytics/CompareTab.tsx
git status --short
git commit -m "feat(analytics): show lead quality mix per day on the Compare tab"
```

---

### Task 5: IST hour × weekday lead-arrival heatmap (Compare tab)

Mirrors the existing `_build_heatmap` pattern in `backend/app/services/meta_ads_analytics.py` (dow × hour grid), applied to inbound lead arrivals for the currently-selected Compare period, in IST.

**Files:**
- Create: `backend/supabase/migrations/160_analytics_lead_arrival_heatmap.sql` (verify the number first)
- Modify: `backend/app/routes/analytics.py` (`_period_payload` and `compare_analytics`)
- Modify: `backend/tests/test_analytics_compare_routes.py` (`_mock_db` helper + new test)
- Modify: `frontend/lib/api.ts` (`ComparePeriod` interface)
- Modify: `frontend/app/dashboard/analytics/CompareTab.tsx` (new `LeadHeatmap` component + render block)

**Interfaces:**
- Produces: `analytics_lead_arrival_heatmap(p_tenant_id uuid, p_start timestamptz, p_end timestamptz) RETURNS TABLE(dow int, hour int, total bigint)` — `dow` is 0=Monday..6=Sunday (IST calendar day), matching the convention in `meta_ads_analytics.py`'s `_build_heatmap`.
- Produces: `ComparePayload.current.heatmap: { dow: number; hour: number; total: number }[]`.

- [ ] **Step 1: Write the failing test**

`_mock_db` in `backend/tests/test_analytics_compare_routes.py` raises `AssertionError` for any RPC name it doesn't recognize — this task adds a 7th RPC call, so every existing `/compare` test will break once the route calls it unless the helper is updated first. Modify `_mock_db` (currently lines 26-52):

```python
    def _mock_db(self, mock_get_db, summaries, daily_leads, daily_messages,
                 money=None, movement=None, response=None, heatmap=None):
        """Each list is per-period: index 0 = current, 1 = previous."""
        money = money if money is not None else [[], []]
        movement = movement if movement is not None else [[], []]
        response = response if response is not None else [[], []]
        heatmap = heatmap if heatmap is not None else [[], []]
        db = MagicMock()

        queues = {
            "analytics_period_summary": summaries,
            "analytics_daily_leads": daily_leads,
            "analytics_daily_messages": daily_messages,
            "analytics_period_money": money,
            "analytics_segment_movement": movement,
            "analytics_response_times": response,
            "analytics_lead_arrival_heatmap": heatmap,
        }

        def rpc(name, params):
            if name not in queues:
                raise AssertionError(f"unexpected rpc {name}")
            result = MagicMock()
            result.execute.return_value = MagicMock(data=queues[name].pop(0))
            return result

        db.rpc.side_effect = rpc
        mock_get_db.return_value = db
        return db
```

Then add a new test method inside `AnalyticsCompareTests`:

```python
    @patch("app.routes.analytics.get_supabase")
    def test_heatmap_is_returned_for_the_current_period(self, mock_get_db):
        self._mock_db(
            mock_get_db,
            summaries=[[{}], [{}]],
            daily_leads=[[], []],
            daily_messages=[[], []],
            heatmap=[
                [{"dow": 1, "hour": 10, "total": 4}],
                [],
            ],
        )
        body = self.client.get(
            "/api/v1/analytics/compare?preset=custom&start=2026-07-15&end=2026-07-16"
        ).json()
        self.assertEqual(body["current"]["heatmap"], [{"dow": 1, "hour": 10, "total": 4}])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && pytest tests/test_analytics_compare_routes.py -v`
Expected: every test using `_mock_db` still passes at this point (the helper change alone is backward compatible — `heatmap` defaults to `[[], []]`), but the new `test_heatmap_is_returned_for_the_current_period` FAILS with `KeyError: 'heatmap'` since the route doesn't call the RPC or return it yet.

- [ ] **Step 3: Verify the current migration number, then create the migration**

Run: `ls backend/supabase/migrations/ | tail -5` — confirm the next free number (written below as 160; renumber if needed, and if Task 3 used a different number than 159, this must be the number immediately after that one).

Create `backend/supabase/migrations/160_analytics_lead_arrival_heatmap.sql`:

```sql
-- 160: inbound-lead arrival heatmap for the Compare tab -- when leads
-- actually reach out, by IST day-of-week x hour. Same shape and dow
-- convention (0=Monday) as meta_ads_analytics.py's _build_heatmap, so the
-- two heatmaps read the same way if a user has seen both.
CREATE OR REPLACE FUNCTION public.analytics_lead_arrival_heatmap(
  p_tenant_id uuid,
  p_start timestamptz,
  p_end timestamptz
)
RETURNS TABLE (
  dow int,
  hour int,
  total bigint
)
LANGUAGE sql
STABLE
SET search_path = public
AS $$
  SELECT
    (extract(isodow FROM (created_at AT TIME ZONE 'Asia/Kolkata'))::int - 1) AS dow,
    extract(hour FROM (created_at AT TIME ZONE 'Asia/Kolkata'))::int        AS hour,
    count(*)                                                                AS total
  FROM leads
  WHERE tenant_id = p_tenant_id
    AND deleted_at IS NULL
    AND source IN ('whatsapp','instagram','facebook','telegram')
    AND created_at >= p_start
    AND created_at <  p_end
  GROUP BY 1, 2
  ORDER BY 1, 2;
$$;

REVOKE EXECUTE ON FUNCTION public.analytics_lead_arrival_heatmap(uuid, timestamptz, timestamptz) FROM anon, authenticated;
```

- [ ] **Step 4: Apply the migration and verify live**

Call `mcp__claude_ai_Supabase__apply_migration` with `project_id: "ayftynkgmfkaqmmnlmoc"`, `name: "analytics_lead_arrival_heatmap"`, `query: <the full SQL above>`.

Then `mcp__claude_ai_Supabase__execute_sql` with `project_id: "ayftynkgmfkaqmmnlmoc"`, `query: "NOTIFY pgrst, 'reload schema';"`.

Then verify with `mcp__claude_ai_Supabase__execute_sql`, `project_id: "ayftynkgmfkaqmmnlmoc"`, using the tenant id found in Task 3 Step 4: `query: "SELECT * FROM analytics_lead_arrival_heatmap('<tenant id>', now() - interval '30 days', now()) ORDER BY total DESC LIMIT 5;"`. Paste the rows returned.

- [ ] **Step 5: Wire the RPC into `_period_payload` and the `/compare` response**

In `backend/app/routes/analytics.py`, replace `_period_payload` (currently lines 1222-1249):

```python
async def _period_payload(db, tenant_id: str, start: date, end: date) -> dict:
    """Fetch summary + both daily series for one period. Three RPCs, concurrent."""
    start_iso, end_iso = _ist_bounds(start, end)
    params = {"p_tenant_id": tenant_id, "p_start": start_iso, "p_end": end_iso}

    summary_res, leads_res, msgs_res, money_res, movement_res, response_res = await asyncio.gather(
        asyncio.to_thread(db.rpc("analytics_period_summary", params).execute),
        asyncio.to_thread(db.rpc("analytics_daily_leads", params).execute),
        asyncio.to_thread(db.rpc("analytics_daily_messages", params).execute),
        asyncio.to_thread(db.rpc("analytics_period_money", params).execute),
        asyncio.to_thread(db.rpc("analytics_segment_movement", params).execute),
        asyncio.to_thread(db.rpc("analytics_response_times", params).execute),
    )

    def first_row(res) -> dict:
        rows = res.data or []
        return rows[0] if rows else {}

    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "summary": first_row(summary_res),
        "money": first_row(money_res),
        "response": first_row(response_res),
        "movement": summarise_movement(movement_res.data or []),
        "daily_leads": fill_days(leads_res.data or [], start, end, LEAD_SERIES_KEYS),
        "daily_messages": fill_days(msgs_res.data or [], start, end, MESSAGE_SERIES_KEYS),
    }
```

with:

```python
async def _period_payload(db, tenant_id: str, start: date, end: date) -> dict:
    """Fetch summary + both daily series for one period. RPCs run concurrently."""
    start_iso, end_iso = _ist_bounds(start, end)
    params = {"p_tenant_id": tenant_id, "p_start": start_iso, "p_end": end_iso}

    (
        summary_res, leads_res, msgs_res, money_res,
        movement_res, response_res, heatmap_res,
    ) = await asyncio.gather(
        asyncio.to_thread(db.rpc("analytics_period_summary", params).execute),
        asyncio.to_thread(db.rpc("analytics_daily_leads", params).execute),
        asyncio.to_thread(db.rpc("analytics_daily_messages", params).execute),
        asyncio.to_thread(db.rpc("analytics_period_money", params).execute),
        asyncio.to_thread(db.rpc("analytics_segment_movement", params).execute),
        asyncio.to_thread(db.rpc("analytics_response_times", params).execute),
        asyncio.to_thread(db.rpc("analytics_lead_arrival_heatmap", params).execute),
    )

    def first_row(res) -> dict:
        rows = res.data or []
        return rows[0] if rows else {}

    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "summary": first_row(summary_res),
        "money": first_row(money_res),
        "response": first_row(response_res),
        "movement": summarise_movement(movement_res.data or []),
        "daily_leads": fill_days(leads_res.data or [], start, end, LEAD_SERIES_KEYS),
        "daily_messages": fill_days(msgs_res.data or [], start, end, MESSAGE_SERIES_KEYS),
        "heatmap": heatmap_res.data or [],
    }
```

Then, in `compare_analytics`'s return statement (the `"current"` dict, as left by Task 4), add `"heatmap": current["heatmap"],` immediately after `"daily_segment_mix": [...]`:

```python
        "current": {
            "start": current["start"], "end": current["end"],
            "summary": cur_sum,
            "money": current["money"],
            "response": current["response"],
            "movement": current["movement"],
            "daily_segment_mix": [
                {
                    "day": d["day"], "hot": d["hot"], "warm": d["warm"],
                    "cold": d["cold"], "disqualified": d["disqualified"],
                }
                for d in current["daily_leads"]
            ],
            "heatmap": current["heatmap"],
        },
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd backend && pytest tests/test_analytics_compare_routes.py -v`
Expected: PASS (all tests in the file).

- [ ] **Step 7: Add the type**

In `frontend/lib/api.ts`, modify `ComparePeriod` (as left by Task 4) to add:

```typescript
  /** Only populated on `current`. */
  heatmap?: { dow: number; hour: number; total: number }[];
```

- [ ] **Step 8: Add the heatmap component and render block**

In `frontend/app/dashboard/analytics/CompareTab.tsx`, add `useMemo` to the React import (currently line 3):

```tsx
import { useEffect, useMemo, useState } from "react";
```

Add a new component, after `SegmentMixChart`:

```tsx
const DOW_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function LeadHeatmap({ points }: { points: ComparePeriod["heatmap"] }) {
  const lookup = useMemo(() => {
    const m: Record<string, number> = {};
    for (const p of points ?? []) m[`${p.dow}-${p.hour}`] = p.total;
    return m;
  }, [points]);
  const max = Math.max(1, ...(points ?? []).map((p) => p.total));

  if (!points || points.length === 0) {
    return (
      <p className="font-label text-sm text-on-surface-muted">
        No inbound leads in this period.
      </p>
    );
  }

  return (
    <div className="overflow-x-auto">
      <div className="inline-grid gap-0.5" style={{ gridTemplateColumns: "40px repeat(24, 20px)" }}>
        <div />
        {Array.from({ length: 24 }, (_, h) => (
          <div key={h} className="text-center font-label text-[9px] text-on-surface-muted">
            {h % 3 === 0 ? h : ""}
          </div>
        ))}
        {DOW_LABELS.map((label, dow) => (
          <div key={label} className="contents">
            <div className="flex items-center font-label text-[9px] text-on-surface-muted">{label}</div>
            {Array.from({ length: 24 }, (_, hour) => {
              const count = lookup[`${dow}-${hour}`] ?? 0;
              const intensity = count === 0 ? 0 : 0.15 + 0.85 * (count / max);
              return (
                <div
                  key={hour}
                  title={`${label} ${hour}:00 — ${count} lead${count === 1 ? "" : "s"}`}
                  className="h-5 w-5 rounded-sm"
                  style={{ backgroundColor: `rgba(91, 33, 182, ${intensity})` }}
                />
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}
```

Add the render block after the segment-mix card added in Task 4:

```tsx
          <div className="min-w-0 rounded-card bg-surface p-4 shadow-card ring-1 ring-[#c4c7c7]/15 sm:p-6">
            <h2 className="font-display text-base font-bold text-primary">
              When leads reach out (IST)
            </h2>
            <p className="mb-4 mt-1 font-label text-xs text-on-surface-muted">
              Inbound leads by day of week and hour.
            </p>
            <LeadHeatmap points={data.current.heatmap} />
          </div>
```

- [ ] **Step 9: Verify in the browser**

With both dev servers running, open `/dashboard/analytics`, Compare tab, a preset with inbound lead activity. Confirm the "When leads reach out (IST)" grid renders with no console errors and cells with more leads are visibly more saturated violet. Screenshot to `/tmp/compare-heatmap.png` (outside the repo) and look at it before checking this off.

- [ ] **Step 10: Run typecheck, lint, and the backend suite**

Run: `cd frontend && npm run typecheck && npm run lint`
Expected: no errors.

Run: `cd backend && pytest -q`
Expected: PASS, no failures (paste the summary line).

- [ ] **Step 11: Commit**

```bash
git add backend/supabase/migrations/160_analytics_lead_arrival_heatmap.sql backend/app/routes/analytics.py backend/tests/test_analytics_compare_routes.py frontend/lib/api.ts frontend/app/dashboard/analytics/CompareTab.tsx
git status --short
git commit -m "feat(analytics): add IST hour-by-weekday lead arrival heatmap to the Compare tab"
```

---

### Task 6: Stale hot-leads action list (Overview tab)

`/funnel` already computes a hot-lead-aging *histogram* (counts per age bucket) but never lists which leads those are. Add a bounded endpoint returning the actual stalest hot (segment A) leads so an owner has something to act on, and a card on the Overview tab linking into the existing `/dashboard/leads?segment=A` view.

**Files:**
- Create: `backend/supabase/migrations/161_analytics_stale_hot_leads.sql` (verify the number first)
- Modify: `backend/app/routes/analytics.py` (new `/hot-leads-stale` route)
- Create: `backend/tests/test_analytics_hot_leads_stale.py`
- Modify: `frontend/lib/api.ts` (new `StaleHotLead` type + `staleHotLeads` client method)
- Modify: `frontend/app/dashboard/analytics/page.tsx` (`OverviewTab` — fetch + render)

**Interfaces:**
- Produces: `GET /api/v1/analytics/hot-leads-stale?min_hours=24&limit=10` → `{ leads: StaleHotLead[] }`, ordered stalest-first (never-contacted leads first, then oldest last-reply first).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_analytics_hot_leads_stale.py`:

```python
"""Tests for GET /api/v1/analytics/hot-leads-stale."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_and_role


class HotLeadsStaleTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}
        app.dependency_overrides[get_tenant_and_role] = lambda: {
            "tenant_id": "tenant-1", "role": "owner", "permissions": [],
        }

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("app.routes.analytics.get_supabase")
    def test_returns_the_rpc_rows_under_a_leads_key(self, mock_get_db):
        db = MagicMock()
        db.rpc.return_value.execute.return_value = MagicMock(data=[
            {"id": "lead-1", "name": "Asha", "phone": "+91900000001", "score": 8,
             "created_at": "2026-07-20T10:00:00+00:00", "last_outbound_at": None},
        ])
        mock_get_db.return_value = db

        res = self.client.get("/api/v1/analytics/hot-leads-stale")

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(len(body["leads"]), 1)
        self.assertEqual(body["leads"][0]["name"], "Asha")

    @patch("app.routes.analytics.get_supabase")
    def test_passes_min_hours_and_limit_to_the_rpc(self, mock_get_db):
        db = MagicMock()
        db.rpc.return_value.execute.return_value = MagicMock(data=[])
        mock_get_db.return_value = db

        res = self.client.get("/api/v1/analytics/hot-leads-stale?min_hours=48&limit=5")

        self.assertEqual(res.status_code, 200)
        db.rpc.assert_called_with("analytics_stale_hot_leads", {
            "p_tenant_id": "tenant-1", "p_min_hours": 48, "p_limit": 5,
        })

    @patch("app.routes.analytics.get_supabase")
    def test_limit_over_50_is_rejected(self, mock_get_db):
        mock_get_db.return_value = MagicMock()
        res = self.client.get("/api/v1/analytics/hot-leads-stale?limit=999")
        self.assertEqual(res.status_code, 422)

    @patch("app.routes.analytics.get_supabase")
    def test_min_hours_under_1_is_rejected(self, mock_get_db):
        mock_get_db.return_value = MagicMock()
        res = self.client.get("/api/v1/analytics/hot-leads-stale?min_hours=0")
        self.assertEqual(res.status_code, 422)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && pytest tests/test_analytics_hot_leads_stale.py -v`
Expected: FAIL — 404, the route doesn't exist yet.

- [ ] **Step 3: Verify the current migration number, then create the migration**

Run: `ls backend/supabase/migrations/ | tail -5` — confirm the next free number (written below as 161; renumber if needed).

Create `backend/supabase/migrations/161_analytics_stale_hot_leads.sql`:

```sql
-- 161: the stalest segment-A (hot) leads, for an actionable "reply to these
-- now" list on the Overview tab. A lead with no outbound message at all
-- (o.last_outbound_at IS NULL) is treated as maximally stale and sorts
-- first via NULLS FIRST.
CREATE OR REPLACE FUNCTION public.analytics_stale_hot_leads(
  p_tenant_id uuid,
  p_min_hours int,
  p_limit int DEFAULT 20
)
RETURNS TABLE (
  id uuid,
  name text,
  phone text,
  score numeric,
  created_at timestamptz,
  last_outbound_at timestamptz
)
LANGUAGE sql
STABLE
SET search_path = public
AS $$
  SELECT l.id, l.name, l.phone, l.score, l.created_at, o.last_outbound_at
  FROM leads l
  LEFT JOIN LATERAL (
    SELECT max(m.created_at) AS last_outbound_at
    FROM messages m
    WHERE m.lead_id = l.id AND m.direction = 'outbound'
  ) o ON true
  WHERE l.tenant_id = p_tenant_id
    AND l.deleted_at IS NULL
    AND l.segment = 'A'
    AND (o.last_outbound_at IS NULL OR o.last_outbound_at < now() - make_interval(hours => p_min_hours))
  ORDER BY o.last_outbound_at ASC NULLS FIRST
  LIMIT p_limit;
$$;

REVOKE EXECUTE ON FUNCTION public.analytics_stale_hot_leads(uuid, int, int) FROM anon, authenticated;
```

- [ ] **Step 4: Apply the migration and verify live**

Call `mcp__claude_ai_Supabase__apply_migration` with `project_id: "ayftynkgmfkaqmmnlmoc"`, `name: "analytics_stale_hot_leads"`, `query: <the full SQL above>`.

Then `mcp__claude_ai_Supabase__execute_sql` with `project_id: "ayftynkgmfkaqmmnlmoc"`, `query: "NOTIFY pgrst, 'reload schema';"`.

Then verify with `mcp__claude_ai_Supabase__execute_sql`, `project_id: "ayftynkgmfkaqmmnlmoc"`, using the tenant id found in Task 3 Step 4: `query: "SELECT * FROM analytics_stale_hot_leads('<tenant id>', 24, 10);"`. Paste the rows returned.

- [ ] **Step 5: Add the route**

In `backend/app/routes/analytics.py`, add after the `/inbound` handler:

```python
@router.get("/hot-leads-stale")
async def hot_leads_stale(
    tenant_id: str = Depends(get_dashboard_analytics_tenant_id),
    min_hours: int = Query(24, ge=1, le=720),
    limit: int = Query(10, ge=1, le=50),
):
    """The stalest hot (segment A) leads -- no reply, or no reply in
    min_hours. An actionable list, not just the aging histogram /funnel
    already returns."""
    db = get_supabase()
    rows = (
        await asyncio.to_thread(
            db.rpc("analytics_stale_hot_leads", {
                "p_tenant_id": tenant_id, "p_min_hours": min_hours, "p_limit": limit,
            }).execute
        )
    ).data or []
    return {"leads": rows}
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd backend && pytest tests/test_analytics_hot_leads_stale.py -v`
Expected: PASS (4 tests)

- [ ] **Step 7: Add the frontend type and client method**

In `frontend/lib/api.ts`, add near `FunnelAnalyticsExtended` (after line 689):

```typescript
export interface StaleHotLead {
  id: string;
  name: string | null;
  phone: string;
  score: number | null;
  created_at: string;
  last_outbound_at: string | null;
}
```

In the `analytics` client object (near `funnelExtended`, currently around line 1505-1506), add:

```typescript
    staleHotLeads: (params?: { min_hours?: number; limit?: number }) => {
      const qs = new URLSearchParams();
      if (params?.min_hours) qs.set("min_hours", String(params.min_hours));
      if (params?.limit) qs.set("limit", String(params.limit));
      const s = qs.toString();
      return apiFetch<{ leads: StaleHotLead[] }>(`/api/v1/analytics/hot-leads-stale${s ? `?${s}` : ""}`);
    },
```

- [ ] **Step 8: Render the card on the Overview tab**

In `frontend/app/dashboard/analytics/page.tsx`, add `StaleHotLead` to the `@/lib/api` import at the top of the file, then in `OverviewTab` (currently starting at line 188), add state and a fetch effect alongside the existing `funnel` effect (after line 211):

```tsx
  const [staleLeads, setStaleLeads] = useState<StaleHotLead[] | null>(null);

  useEffect(() => {
    let isCurrent = true;
    api.analytics.staleHotLeads({ min_hours: 24, limit: 10 })
      .then((d) => { if (isCurrent) setStaleLeads(d.leads); })
      .catch(() => {});
    return () => { isCurrent = false; };
  }, [retryKey]);
```

Add the card after the "Hot Leads (Segment A) — time without conversion" section (after line 328, still inside the closing `</div>` of `OverviewTab`'s return):

```tsx
      {staleLeads && staleLeads.length > 0 && (
        <SectionCard title="Hot leads waiting on a reply">
          <div className="space-y-1">
            {staleLeads.map((lead) => (
              <a
                key={lead.id}
                href="/dashboard/leads?segment=A"
                className="flex items-center justify-between rounded-lg px-3 py-2 transition-colors hover:bg-surface-low/60"
              >
                <span className="font-body text-sm text-on-surface">
                  {lead.name || lead.phone}
                </span>
                <span className="font-label text-xs text-on-surface-muted">
                  {lead.last_outbound_at ? "no reply since last message" : "never contacted"}
                </span>
              </a>
            ))}
          </div>
        </SectionCard>
      )}
```

- [ ] **Step 9: Verify in the browser**

With both dev servers running, open `/dashboard/analytics` Overview tab for a tenant with hot leads. Confirm "Hot leads waiting on a reply" renders (or is absent if there are none — check both by temporarily testing with `min_hours=1` if needed) and each row links to `/dashboard/leads?segment=A`. Screenshot to `/tmp/overview-stale-leads.png` (outside the repo) and look at it before checking this off.

- [ ] **Step 10: Run typecheck, lint, and the backend suite**

Run: `cd frontend && npm run typecheck && npm run lint`
Expected: no errors.

Run: `cd backend && pytest -q`
Expected: PASS, no failures (paste the summary line).

- [ ] **Step 11: Commit**

```bash
git add backend/supabase/migrations/161_analytics_stale_hot_leads.sql backend/app/routes/analytics.py backend/tests/test_analytics_hot_leads_stale.py frontend/lib/api.ts frontend/app/dashboard/analytics/page.tsx
git status --short
git commit -m "feat(analytics): add a stale hot-leads action list to the Overview tab"
```

---

### Task 7: Date-range filter on `GET /api/v1/leads/` (backend capability for future drill-down)

Enables filtering the leads list by `created_at` date range, following the exact pattern already used for `segment`/`assigned_to`/`source_filter`. This is scoped to the backend only: `LeadsClient.tsx` has its own filter/tab state machine that is out of scope to safely extend inside this plan (it is a large, already-complex component this plan's author has not fully audited) — wiring a UI for this filter is a follow-on, not part of this task.

**Files:**
- Modify: `backend/app/routes/leads.py:5` (import), `:66-79` (`list_leads`)
- Create: `backend/tests/test_leads_date_filter.py`

**Interfaces:**
- Produces: `GET /api/v1/leads/?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD` — both optional, both inclusive of the named dates, additive to the existing `segment`/`assigned_to`/`source_filter`/`broadcast_id`/`ad_campaign_id` filters (all still work unchanged and can combine with these).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_leads_date_filter.py`:

```python
"""Tests for date_from/date_to filtering on GET /api/v1/leads/."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.routes import leads as leads_route


class LeadsDateFilterTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[leads_route.require_leads_view] = lambda: {
            "tenant_id": "tenant-1", "role": "owner", "permissions": [],
        }

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("app.routes.leads.get_supabase")
    def test_date_from_and_date_to_are_applied_to_the_query(self, mock_get_db):
        db = MagicMock()
        base = (
            db.table.return_value.select.return_value.eq.return_value
            .is_.return_value.neq.return_value.neq.return_value
        )
        base.gte.return_value.lt.return_value.order.return_value.range.return_value.execute.return_value = (
            MagicMock(data=[], count=0)
        )
        mock_get_db.return_value = db

        res = self.client.get("/api/v1/leads/?date_from=2026-07-10&date_to=2026-07-11")

        self.assertEqual(res.status_code, 200)
        base.gte.assert_called_with("created_at", "2026-07-10")
        base.gte.return_value.lt.assert_called_with("created_at", "2026-07-12")

    @patch("app.routes.leads.get_supabase")
    def test_malformed_date_from_returns_400(self, mock_get_db):
        mock_get_db.return_value = MagicMock()
        res = self.client.get("/api/v1/leads/?date_from=not-a-date")
        self.assertEqual(res.status_code, 400)

    @patch("app.routes.leads.get_supabase")
    def test_malformed_date_to_returns_400(self, mock_get_db):
        mock_get_db.return_value = MagicMock()
        res = self.client.get("/api/v1/leads/?date_to=not-a-date")
        self.assertEqual(res.status_code, 400)

    @patch("app.routes.leads.get_supabase")
    def test_no_date_params_leaves_existing_behaviour_unchanged(self, mock_get_db):
        db = MagicMock()
        base = (
            db.table.return_value.select.return_value.eq.return_value
            .is_.return_value.neq.return_value.neq.return_value
        )
        base.order.return_value.range.return_value.execute.return_value = MagicMock(data=[], count=0)
        mock_get_db.return_value = db

        res = self.client.get("/api/v1/leads/")

        self.assertEqual(res.status_code, 200)
        base.gte.assert_not_called()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && pytest tests/test_leads_date_filter.py -v`
Expected: FAIL — `date_from`/`date_to` are not accepted params yet, so the first two assertions never see `.gte`/`.lt` called with those values (and the 400 tests get 200 instead, since the params are silently ignored by FastAPI today... actually confirm this by running it — the malformed-date tests may currently return 200 since there's no such param at all yet, which still counts as a failing test against the `400` expectation).

- [ ] **Step 3: Add the import**

In `backend/app/routes/leads.py`, modify the import (currently line 5):

```python
from datetime import datetime, timezone, timedelta
```

to:

```python
from datetime import date, datetime, timezone, timedelta
```

- [ ] **Step 4: Add the filter**

In `backend/app/routes/leads.py`, modify `list_leads`'s signature and query construction (currently lines 66-79):

```python
@router.get("/", response_model=PaginatedResponse)
async def list_leads(
    segment: str | None = Query(None, pattern="^[ABCD]$"),
    assigned_to: str | None = Query(None),
    source_filter: str | None = Query(None),
    broadcast_id: str | None = Query(None),
    ad_campaign_id: str | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    ctx: dict = Depends(require_leads_view),
):
    db = get_supabase()
    tenant_id = ctx["tenant_id"]
    offset = (page - 1) * limit
    query = (db.table("leads").select("*", count="exact")
             .eq("tenant_id", tenant_id)
             .is_("deleted_at", "null")
             .neq("opted_out", True)
             .neq("whatsapp_undeliverable", True))
    if segment:
        query = query.eq("segment", segment)
```

with:

```python
@router.get("/", response_model=PaginatedResponse)
async def list_leads(
    segment: str | None = Query(None, pattern="^[ABCD]$"),
    assigned_to: str | None = Query(None),
    source_filter: str | None = Query(None),
    broadcast_id: str | None = Query(None),
    ad_campaign_id: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    ctx: dict = Depends(require_leads_view),
):
    db = get_supabase()
    tenant_id = ctx["tenant_id"]
    offset = (page - 1) * limit
    query = (db.table("leads").select("*", count="exact")
             .eq("tenant_id", tenant_id)
             .is_("deleted_at", "null")
             .neq("opted_out", True)
             .neq("whatsapp_undeliverable", True))
    if date_from:
        try:
            date.fromisoformat(date_from)
        except ValueError:
            raise HTTPException(status_code=400, detail="date_from must be YYYY-MM-DD")
        query = query.gte("created_at", date_from)
    if date_to:
        try:
            date_to_parsed = date.fromisoformat(date_to)
        except ValueError:
            raise HTTPException(status_code=400, detail="date_to must be YYYY-MM-DD")
        query = query.lt("created_at", (date_to_parsed + timedelta(days=1)).isoformat())
    if segment:
        query = query.eq("segment", segment)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd backend && pytest tests/test_leads_date_filter.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Run the full backend test suite**

Run: `cd backend && pytest -q`
Expected: PASS, no failures (paste the final summary line).

- [ ] **Step 7: Commit**

```bash
git add backend/app/routes/leads.py backend/tests/test_leads_date_filter.py
git status --short
git commit -m "feat(leads): add date_from/date_to filtering to the leads list endpoint"
```

---

### Task 8: Final verification and cleanup pass

Prove the whole plan's worth of work together, end to end, and leave the tree completely clean.

**Files:** none created or modified except possibly fixes surfaced by this task's checks (if any check fails, fix the specific regression it found, re-run that check, and note the fix in the commit message — do not skip a failing check).

- [ ] **Step 1: Full backend test suite**

Run: `cd backend && pytest -q`
Expected: PASS. Paste the final summary line (should be at least 705 + the new tests from Tasks 1, 2, 3, 4, 5, 6, 7 in this plan — roughly 30 new tests).

- [ ] **Step 2: Frontend typecheck, lint, build**

Run: `cd frontend && npm run typecheck`
Expected: no errors.

Run: `cd frontend && npm run lint`
Expected: no errors.

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 3: Live screenshot verification across breakpoints**

Start both dev servers if not already running. Using Playwright, screenshot the Analytics page's Overview tab and Compare tab at 1024 and 1440 px widths (this is an authenticated internal dashboard, not a public landing page, so the 320/768 mobile breakpoints from the standard visual-regression checklist are lower priority — still run them if time allows, but 1024/1440 are mandatory). Confirm in each screenshot:
  - Overview tab: Cost per Lead and Reply Time KPI cards render with real values; "Hot leads waiting on a reply" card renders (or is correctly absent) with no layout break.
  - Compare tab: the engagement-rate row appears in "Every number, side by side"; the "Lead quality mix, day by day" stacked chart renders; the "When leads reach out (IST)" heatmap renders.

  Save all screenshots to `/tmp/` (never inside the repo). Look at each one — do not report this step as passed from the screenshot command's exit code alone.

- [ ] **Step 4: Delete every temporary artifact this plan's verification steps created**

Run: `git status --short`

Expected output: empty (nothing untracked, nothing modified) — every prior task already committed its own changes. If anything appears here, it is a leftover from a verification step (a temp route, a script, a screenshot saved inside the repo instead of `/tmp`) that was not cleaned up in its own task. Delete it now, re-run `git status --short`, and paste the now-empty output as evidence.

- [ ] **Step 5: Confirm no migration numbering drift was left unresolved**

Run: `ls backend/supabase/migrations/ | tail -5` and `git log --oneline -5 -- backend/supabase/migrations/`. Confirm every migration file created by this plan (Tasks 3, 5, 6) has a filename matching what was actually applied via `apply_migration` in that task (i.e., no file was renamed after being applied without re-verifying against the live schema). If a mismatch is found, this is a bug from an earlier task — go back, fix the filename/re-apply as needed, and re-verify against Supabase before continuing.

- [ ] **Step 6: Report status**

Summarize, in your final message to the user: full test counts (before/after), confirmation that typecheck/lint/build are clean, confirmation that `git status --short` is empty, the list of commits made by this plan (`git log --oneline -20`), and explicitly state that no `git push` was run and it is pending human review.
