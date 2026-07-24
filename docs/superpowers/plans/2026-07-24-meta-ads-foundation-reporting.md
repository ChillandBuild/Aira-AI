# Meta Ads Manager — Plan 1: Foundation + Reporting — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new **Meta Ads** dashboard page with a full-account **Ad Performance** table and an **Analytics** tab (KPI cards + charts), all driven by widening the existing read-only Meta Insights sync — no ad-creation and no new Meta permission.

**Architecture:** Extends the existing Ad-Creative Attribution system (migration 147, `meta_ads_insights_sync.py`, `ad_performance.py`). A schema migration widens `ad_insights_daily` (impressions/reach/actions) and `ad_campaigns` (objective/status/budget). The sync job gains a campaign-level fetch and stores the wider metrics. A new aggregation service rolls insights up to campaign/ad-set/ad level and computes analytics series. A new `meta_ads` FastAPI router exposes `/performance` and `/analytics`. A new Next.js `/dashboard/meta-ads` route hosts a two-tab client (Ad Performance table + Analytics charts via Recharts).

**Tech Stack:** FastAPI (`backend/app/`), Next.js 14 App Router (`frontend/app/dashboard/`), Supabase (Postgres, service-role writes bypass RLS), SWR, Recharts 3.

## Global Constraints

- **Scope is read-only reporting.** `ads_read` only — no `ads_management`, no write calls to Meta. Ad creation and status/budget writes are Plan 2, out of scope here.
- **Frontend CI gate is `next lint` AND `tsc`, not tsc alone.** Unused imports/vars and `any` FAIL CI (`@typescript-eslint/no-unused-vars`, `no-explicit-any` are errors) even though they pass `tsc --noEmit`. Run `cd frontend && npm run lint && npm run typecheck` before every frontend commit.
- **Backend tests:** `cd backend && pytest`. New tests go under `backend/tests/`. Each test file must start with `import sys` + `sys.path.insert(0, str(Path(__file__).resolve().parents[1]))` if it imports `app.*` and doesn't rely on PYTHONPATH.
- **Migration numbering:** next unused prefix is `148` (latest applied/created is `147_ad_creative_attribution.sql`).
- **DB writes in sync/aggregation are service-role** (bypass RLS); RLS on new columns is inherited from the existing tables' policies (admin-all + tenant-read) — no new policies needed since we only ADD columns to existing tables.
- **Brand colors:** primary violet `#5b21b6` (interactive/identity), chart accent `#6366f1`, positive/emerald `#059669`, status-red `#e5484d`. Never use emerald for a generic series — it means "positive/approved" in this app.
- **Money is INR**, formatted `₹` + `Math.round(n).toLocaleString("en-IN")`.
- **Routes are tenant-scoped via `Depends(get_tenant_id)`**, registered with the shared `_auth` dependency in `main.py` (same as the `inbound_leads` router). No new granular RBAC permission in this plan; sidebar visibility reuses `inbound_leads.view` + inbound feature flag.

---

### Task 1: Schema migration 148 — widen insights & campaign columns

**Files:**
- Create: `backend/supabase/migrations/148_meta_ads_reporting_columns.sql`

**Interfaces:**
- Produces: columns `ad_insights_daily.impressions bigint`, `ad_insights_daily.reach bigint`, `ad_insights_daily.actions jsonb`; columns `ad_campaigns.objective text`, `ad_campaigns.effective_status text`, `ad_campaigns.daily_budget numeric(14,2)`, `ad_campaigns.lifetime_budget numeric(14,2)`, `ad_campaigns.bid_strategy text`. All later tasks read/write these.

- [ ] **Step 1: Write the migration**

```sql
-- 148: Widen ad reporting for the Meta Ads dashboard (Plan 1, read-only).
-- Adds full-funnel Meta metrics to daily insights (impressions/reach/actions)
-- and campaign-level status/objective/budget to ad_campaigns, populated by the
-- widened services/meta_ads_insights_sync.py. Columns only — no new RLS needed
-- (existing admin-all + tenant-read policies on both tables already apply).

ALTER TABLE public.ad_insights_daily
  ADD COLUMN IF NOT EXISTS impressions bigint NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS reach bigint NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS actions jsonb NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE public.ad_campaigns
  ADD COLUMN IF NOT EXISTS objective text,
  ADD COLUMN IF NOT EXISTS effective_status text,
  ADD COLUMN IF NOT EXISTS daily_budget numeric(14,2),
  ADD COLUMN IF NOT EXISTS lifetime_budget numeric(14,2),
  ADD COLUMN IF NOT EXISTS bid_strategy text;
```

- [ ] **Step 2: Apply to live Supabase and verify**

Use the Supabase MCP `apply_migration` tool with name `148_meta_ads_reporting_columns` and the SQL above. Then verify with `execute_sql`:

```sql
SELECT column_name FROM information_schema.columns
WHERE table_name = 'ad_insights_daily' AND column_name IN ('impressions','reach','actions')
UNION ALL
SELECT column_name FROM information_schema.columns
WHERE table_name = 'ad_campaigns' AND column_name IN ('objective','effective_status','daily_budget','lifetime_budget','bid_strategy');
```

Expected: 8 rows returned.

- [ ] **Step 3: Commit**

```bash
git add backend/supabase/migrations/148_meta_ads_reporting_columns.sql
git commit -m "feat(meta-ads): migration 148 — widen insights & campaign reporting columns"
```

---

### Task 2: Widen the Meta Insights sync (metrics + campaign-level fetch)

**Files:**
- Modify: `backend/app/services/meta_ads_insights_sync.py`
- Test: `backend/tests/test_meta_ads_sync_transform.py`

**Interfaces:**
- Consumes: migration 148 columns.
- Produces:
  - `sum_actions(actions: list[dict], action_types: set[str]) -> int` — sums `value` across matching `action_type` entries in Meta's `actions` array.
  - `extract_result_metric(row: dict) -> tuple[str, int]` — returns `(result_label, result_count)` for an ad row given its objective/optimization goal (messaging→"Messaging conversations", app→"App installs", link_clicks→"Link clicks", else "Results" + inline_link_clicks).
  - Sync now also writes `impressions`/`reach`/`actions` into `ad_insights_daily` and upserts campaign-level `objective`/`effective_status`/`daily_budget`/`lifetime_budget`/`bid_strategy` into `ad_campaigns`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_meta_ads_sync_transform.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.meta_ads_insights_sync import sum_actions, extract_result_metric


def test_sum_actions_matches_types():
    actions = [
        {"action_type": "onsite_conversion.total_messaging_connection", "value": "12"},
        {"action_type": "link_click", "value": "40"},
        {"action_type": "post_engagement", "value": "99"},
    ]
    assert sum_actions(actions, {"onsite_conversion.total_messaging_connection"}) == 12
    assert sum_actions(actions, {"link_click"}) == 40
    assert sum_actions(actions, {"nonexistent"}) == 0


def test_sum_actions_handles_empty():
    assert sum_actions([], {"link_click"}) == 0
    assert sum_actions(None, {"link_click"}) == 0


def test_extract_result_metric_messaging():
    row = {
        "optimization_goal": "CONVERSATIONS",
        "actions": [{"action_type": "onsite_conversion.total_messaging_connection", "value": "7"}],
        "inline_link_clicks": "50",
    }
    label, count = extract_result_metric(row)
    assert label == "Messaging conversations"
    assert count == 7


def test_extract_result_metric_app_installs():
    row = {
        "optimization_goal": "APP_INSTALLS",
        "actions": [{"action_type": "mobile_app_install", "value": "5"}],
        "inline_link_clicks": "50",
    }
    label, count = extract_result_metric(row)
    assert label == "App installs"
    assert count == 5


def test_extract_result_metric_defaults_to_link_clicks():
    row = {"optimization_goal": "LINK_CLICKS", "actions": [], "inline_link_clicks": "40"}
    label, count = extract_result_metric(row)
    assert label == "Link clicks"
    assert count == 40
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_meta_ads_sync_transform.py -v`
Expected: FAIL with `ImportError: cannot import name 'sum_actions'`

- [ ] **Step 3: Add the transform helpers and widen the fetch/write**

In `backend/app/services/meta_ads_insights_sync.py`, update the insight fields constant and add helpers + campaign fetch. Change `_INSIGHT_FIELDS` to include the new fields:

```python
_INSIGHT_FIELDS = (
    "ad_id,ad_name,adset_id,adset_name,campaign_id,campaign_name,"
    "optimization_goal,inline_link_clicks,clicks,spend,impressions,reach,actions"
)

_CAMPAIGN_FIELDS = "id,name,objective,effective_status,daily_budget,lifetime_budget,bid_strategy"

# Meta action_type sets mapped to a human "Results" label, checked in order.
_RESULT_RULES: list[tuple[str, str, set[str]]] = [
    ("CONVERSATIONS", "Messaging conversations", {"onsite_conversion.total_messaging_connection"}),
    ("APP_INSTALLS", "App installs", {"mobile_app_install"}),
    ("LINK_CLICKS", "Link clicks", set()),  # falls through to inline_link_clicks
]


def sum_actions(actions, action_types: set[str]) -> int:
    """Sum the integer `value` across entries whose action_type is in the set."""
    total = 0
    for a in (actions or []):
        if a.get("action_type") in action_types:
            try:
                total += int(float(a.get("value", 0) or 0))
            except (TypeError, ValueError):
                continue
    return total


def extract_result_metric(row: dict) -> tuple[str, int]:
    """Return (result_label, result_count) for an ad row based on its optimization goal."""
    goal = (row.get("optimization_goal") or "").upper()
    actions = row.get("actions")
    for goal_key, label, types in _RESULT_RULES:
        if goal == goal_key:
            if not types:  # LINK_CLICKS → inline_link_clicks
                return label, int(float(row.get("inline_link_clicks", 0) or 0))
            return label, sum_actions(actions, types)
    return "Results", int(float(row.get("inline_link_clicks", 0) or 0))
```

Update `_write_insight_row` to persist the new columns:

```python
def _write_insight_row(db, tenant_id: str, creative_id: str, row: dict) -> None:
    insight_date = row.get("date_start")
    if not insight_date:
        raise ValueError(f"insight row for ad_id={row.get('ad_id')} has no date_start")
    db.table("ad_insights_daily").upsert({
        "tenant_id": tenant_id,
        "ad_creative_id": creative_id,
        "insight_date": insight_date,
        "clicks": int(float(row.get("clicks", 0) or 0)),
        "inline_link_clicks": int(float(row.get("inline_link_clicks", 0) or 0)),
        "spend": float(row.get("spend", 0) or 0),
        "impressions": int(float(row.get("impressions", 0) or 0)),
        "reach": int(float(row.get("reach", 0) or 0)),
        "actions": row.get("actions") or [],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }, on_conflict="tenant_id,ad_creative_id,insight_date").execute()
```

Add a campaign-level fetch + upsert, called once per sync run after the ad-level loop. Add this function and call it from both `sync_tenant_ad_insights` and `sync_tenant_ad_insights_verbose` (after the row loop, best-effort):

```python
def _fetch_campaigns(token: str, account: str, date_preset: str) -> list[dict]:
    url = f"{_GRAPH_BASE}/{account}/campaigns"
    params = {"fields": _CAMPAIGN_FIELDS, "limit": "200", "access_token": token}
    out: list[dict] = []
    with httpx.Client(timeout=30) as client:
        next_url, next_params = url, params
        for _ in range(20):
            resp = client.get(next_url, params=next_params)
            resp.raise_for_status()
            body = resp.json()
            out.extend(body.get("data", []))
            nxt = (body.get("paging") or {}).get("next")
            if not nxt:
                break
            next_url, next_params = nxt, None
    return out


def sync_campaign_meta(db, tenant_id: str, token: str, account: str) -> int:
    """Update ad_campaigns rows with objective/status/budget from Meta. Matches on
    external_campaign_id (Meta campaign id). Best-effort; returns count updated."""
    try:
        campaigns = _fetch_campaigns(token, account, "last_30d")
    except Exception as e:
        logger.warning(f"campaign meta fetch failed (tenant {tenant_id}): {e}")
        return 0
    updated = 0
    for c in campaigns:
        cid = (c.get("id") or "").strip()
        if not cid:
            continue
        daily = c.get("daily_budget")
        lifetime = c.get("lifetime_budget")
        payload = {
            "objective": c.get("objective"),
            "effective_status": c.get("effective_status"),
            # Meta returns budgets in minor units (paise) as strings.
            "daily_budget": (float(daily) / 100.0) if daily else None,
            "lifetime_budget": (float(lifetime) / 100.0) if lifetime else None,
            "bid_strategy": c.get("bid_strategy"),
        }
        res = (
            db.table("ad_campaigns").update(payload)
            .eq("external_campaign_id", cid).eq("tenant_id", tenant_id).execute()
        )
        if res.data:
            updated += 1
    return updated
```

In `sync_tenant_ad_insights`, after the `for row in rows:` loop and before the return, add:

```python
    try:
        sync_campaign_meta(db, tenant_id, token, account)
    except Exception as e:
        logger.warning(f"campaign meta sync failed (tenant {tenant_id}): {e}")
```

In `sync_tenant_ad_insights_verbose`, after its row loop and before building the return dict, add the same call wrapped in try/except (append any error to `row_errors`).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_meta_ads_sync_transform.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/meta_ads_insights_sync.py backend/tests/test_meta_ads_sync_transform.py
git commit -m "feat(meta-ads): widen insights sync with impressions/reach/actions + campaign meta"
```

---

### Task 3: Full-account performance rollup service

**Files:**
- Create: `backend/app/services/meta_ads_reporting.py`
- Test: `backend/tests/test_meta_ads_reporting.py`

**Interfaces:**
- Consumes: `ad_creatives`, `ad_insights_daily` (with new columns), `ad_campaigns` (with new columns), `leads` (existing funnel join, mirrors `ad_performance.build_creative_performance`).
- Produces:
  - `roll_up_rows(level: str, rows: list[dict]) -> list[dict]` — pure aggregator: groups per-creative metric dicts by `campaign`/`adset`/`ad` and sums numeric metrics. Testable without a DB.
  - `build_account_performance(db, tenant_id, *, level="campaign", date_from=None, date_to=None) -> list[dict]` — DB-backed; one row per campaign (or ad-set/ad), each with `name, status, budget_label, spend, impressions, reach, results, result_label, cost_per_result, clicks, messages, clicked_no_message, qualified, hot`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_meta_ads_reporting.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.meta_ads_reporting import roll_up_rows


def _row(group_id, group_name, **m):
    base = {"group_id": group_id, "group_name": group_name,
            "spend": 0, "impressions": 0, "reach": 0, "results": 0,
            "clicks": 0, "messages": 0, "qualified": 0, "hot": 0,
            "result_label": "Messaging conversations"}
    base.update(m)
    return base


def test_rollup_sums_numeric_within_group():
    rows = [
        _row("c1", "Astro", spend=100.0, clicks=50, messages=10, results=8),
        _row("c1", "Astro", spend=50.0, clicks=25, messages=5, results=4),
        _row("c2", "Diwali", spend=200.0, clicks=80, messages=20, results=15),
    ]
    out = roll_up_rows("campaign", rows)
    astro = next(r for r in out if r["group_id"] == "c1")
    assert astro["spend"] == 150.0
    assert astro["clicks"] == 75
    assert astro["messages"] == 15
    assert astro["results"] == 12
    assert astro["name"] == "Astro"


def test_rollup_computes_cost_per_result_and_no_message():
    rows = [_row("c1", "Astro", spend=120.0, clicks=100, messages=40, results=8)]
    out = roll_up_rows("campaign", rows)
    r = out[0]
    assert r["cost_per_result"] == 15.0          # 120 / 8
    assert r["clicked_no_message"] == 60         # 100 - 40


def test_rollup_cost_per_result_none_when_zero_results():
    rows = [_row("c1", "Astro", spend=120.0, clicks=100, messages=0, results=0)]
    out = roll_up_rows("campaign", rows)
    assert out[0]["cost_per_result"] is None


def test_rollup_sorts_by_spend_desc():
    rows = [
        _row("c1", "Small", spend=10.0),
        _row("c2", "Big", spend=500.0),
    ]
    out = roll_up_rows("campaign", rows)
    assert [r["name"] for r in out] == ["Big", "Small"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_meta_ads_reporting.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.meta_ads_reporting'`

- [ ] **Step 3: Implement the service**

```python
# backend/app/services/meta_ads_reporting.py
"""Full-account Meta Ads performance rollup for the Meta Ads dashboard.
Reads the same tables as services/ad_performance.py but rolls up to
campaign / ad-set / ad level and includes impressions/reach/results.
Pure read; no Meta calls (the sync job already populated the DB).
"""
import logging

logger = logging.getLogger(__name__)


def _safe_div(n: float, d: float):
    return (n / d) if d else None


def roll_up_rows(level: str, rows: list[dict]) -> list[dict]:
    """Group per-creative metric dicts by group_id, sum numeric fields, derive
    cost_per_result and clicked_no_message. `level` is metadata only. Sorted by
    spend desc."""
    groups: dict[str, dict] = {}
    for r in rows:
        gid = r.get("group_id") or ""
        g = groups.get(gid)
        if not g:
            g = {
                "group_id": gid, "name": r.get("group_name") or "—",
                "status": r.get("status"), "budget_label": r.get("budget_label"),
                "result_label": r.get("result_label") or "Results",
                "spend": 0.0, "impressions": 0, "reach": 0, "results": 0,
                "clicks": 0, "messages": 0, "qualified": 0, "hot": 0,
            }
            groups[gid] = g
        g["spend"] += float(r.get("spend", 0) or 0)
        g["impressions"] += int(r.get("impressions", 0) or 0)
        g["reach"] += int(r.get("reach", 0) or 0)
        g["results"] += int(r.get("results", 0) or 0)
        g["clicks"] += int(r.get("clicks", 0) or 0)
        g["messages"] += int(r.get("messages", 0) or 0)
        g["qualified"] += int(r.get("qualified", 0) or 0)
        g["hot"] += int(r.get("hot", 0) or 0)

    out = []
    for g in groups.values():
        g["spend"] = round(g["spend"], 2)
        g["cost_per_result"] = _safe_div(g["spend"], g["results"])
        g["clicked_no_message"] = max(g["clicks"] - g["messages"], 0)
        out.append(g)
    out.sort(key=lambda x: x["spend"], reverse=True)
    return out


def build_account_performance(db, tenant_id: str, *, level: str = "campaign",
                              date_from: str | None = None, date_to: str | None = None) -> list[dict]:
    """One row per campaign/adset/ad with Meta metrics + Aira funnel counts."""
    from app.services.meta_ads_insights_sync import extract_result_metric

    creatives = (
        db.table("ad_creatives").select(
            "id,creative_label,meta_ad_id,meta_adset_id,meta_adset_name,meta_campaign_id,campaign_id"
        ).eq("tenant_id", tenant_id).execute().data
    ) or []
    if not creatives:
        return []
    creative_ids = [c["id"] for c in creatives]

    # Campaign meta (status/budget/name) by ad_campaigns.id
    camp_ids = sorted({c["campaign_id"] for c in creatives if c.get("campaign_id")})
    camps = {}
    if camp_ids:
        for c in (db.table("ad_campaigns").select(
                "id,campaign_name,effective_status,daily_budget,lifetime_budget"
            ).eq("tenant_id", tenant_id).in_("id", camp_ids).execute().data or []):
            camps[c["id"]] = c

    # Insights summed per creative
    ins_q = db.table("ad_insights_daily").select(
        "ad_creative_id,inline_link_clicks,spend,impressions,reach,actions"
    ).eq("tenant_id", tenant_id).in_("ad_creative_id", creative_ids)
    if date_from:
        ins_q = ins_q.gte("insight_date", date_from)
    if date_to:
        ins_q = ins_q.lte("insight_date", date_to)
    ins_by_creative: dict[str, dict] = {}
    for r in (ins_q.execute().data or []):
        acc = ins_by_creative.setdefault(r["ad_creative_id"],
            {"clicks": 0, "spend": 0.0, "impressions": 0, "reach": 0, "actions": []})
        acc["clicks"] += int(r.get("inline_link_clicks", 0) or 0)
        acc["spend"] += float(r.get("spend", 0) or 0)
        acc["impressions"] += int(r.get("impressions", 0) or 0)
        acc["reach"] += int(r.get("reach", 0) or 0)
        acc["actions"].extend(r.get("actions") or [])

    # Funnel counts (messages/qualified/hot) per creative — mirrors ad_performance.py
    lead_q = db.table("leads").select("segment,attributed_ad_creative_id,created_at").eq(
        "tenant_id", tenant_id).in_("attributed_ad_creative_id", creative_ids).is_("deleted_at", "null")
    if date_from:
        lead_q = lead_q.gte("created_at", date_from)
    if date_to:
        lead_q = lead_q.lte("created_at", date_to + "T23:59:59")
    funnel: dict[str, dict] = {}
    for lead in (lead_q.execute().data or []):
        cid = lead.get("attributed_ad_creative_id")
        if not cid:
            continue
        f = funnel.setdefault(cid, {"messages": 0, "qualified": 0, "hot": 0})
        f["messages"] += 1
        if lead.get("segment") in ("A", "B"):
            f["qualified"] += 1
        if lead.get("segment") == "A":
            f["hot"] += 1

    # Build per-creative metric rows keyed to the requested grouping level.
    per_creative = []
    for c in creatives:
        ins = ins_by_creative.get(c["id"], {"clicks": 0, "spend": 0.0, "impressions": 0, "reach": 0, "actions": []})
        fn = funnel.get(c["id"], {"messages": 0, "qualified": 0, "hot": 0})
        camp = camps.get(c.get("campaign_id"), {})
        result_label, results = extract_result_metric({
            "optimization_goal": camp.get("objective"),
            "actions": ins["actions"],
            "inline_link_clicks": ins["clicks"],
        })
        if level == "campaign":
            gid, gname = c.get("campaign_id") or "none", camp.get("campaign_name") or "Unknown Campaign"
            status = camp.get("effective_status")
            budget_label = _budget_label(camp)
        elif level == "adset":
            gid, gname = c.get("meta_adset_id") or "none", c.get("meta_adset_name") or "—"
            status, budget_label = None, None
        else:  # ad
            gid, gname = c["id"], c["creative_label"]
            status, budget_label = None, None
        per_creative.append({
            "group_id": gid, "group_name": gname, "status": status, "budget_label": budget_label,
            "result_label": result_label, "results": results,
            "spend": ins["spend"], "impressions": ins["impressions"], "reach": ins["reach"],
            "clicks": ins["clicks"], "messages": fn["messages"],
            "qualified": fn["qualified"], "hot": fn["hot"],
        })

    return roll_up_rows(level, per_creative)


def _budget_label(camp: dict) -> str | None:
    if camp.get("daily_budget"):
        return f"₹{camp['daily_budget']:.0f}/day"
    if camp.get("lifetime_budget"):
        return f"₹{camp['lifetime_budget']:.0f} total"
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_meta_ads_reporting.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/meta_ads_reporting.py backend/tests/test_meta_ads_reporting.py
git commit -m "feat(meta-ads): full-account performance rollup service"
```

---

### Task 4: Analytics aggregation service

**Files:**
- Create: `backend/app/services/meta_ads_analytics.py`
- Test: `backend/tests/test_meta_ads_analytics.py`

**Interfaces:**
- Consumes: the per-creative rows produced inside `build_account_performance` (reuses its DB reads via a shared internal helper) and daily insight/lead rows.
- Produces `build_analytics(db, tenant_id, *, date_from=None, date_to=None) -> dict` with keys:
  - `kpis`: `{spend, messages, qualified, hot, cost_per_hot}` (+ `roas: None`, `revenue_available: False`)
  - `funnel`: `[{stage, count}]` for Clicked/Messaged/Qualified/Hot
  - `leaderboard`: `[{name, cost_per_hot, hot, spend}]` sorted worst→best cost_per_hot (None costs last)
  - `trend`: `[{date, spend, qualified}]`
  - `heatmap`: `[{dow, hour, qualified}]` (0–6 × 0–23)
  - `quadrant`: `[{name, spend, cost_per_hot, hot}]`
  - `spend_distribution`: `[{name, spend}]`
- Pure helpers (tested directly): `funnel_stages(clicks, messages, qualified, hot)`, `leaderboard_sort(rows)`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_meta_ads_analytics.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.meta_ads_analytics import funnel_stages, leaderboard_sort


def test_funnel_stages_shape():
    out = funnel_stages(clicks=2180, messages=1240, qualified=412, hot=178)
    assert out == [
        {"stage": "Clicked", "count": 2180},
        {"stage": "Messaged", "count": 1240},
        {"stage": "Qualified", "count": 412},
        {"stage": "Hot", "count": 178},
    ]


def test_leaderboard_sort_worst_cost_first_none_last():
    rows = [
        {"name": "A", "cost_per_hot": 45.0, "hot": 10, "spend": 450.0},
        {"name": "B", "cost_per_hot": 112.0, "hot": 2, "spend": 224.0},
        {"name": "C", "cost_per_hot": None, "hot": 0, "spend": 100.0},
    ]
    out = leaderboard_sort(rows)
    assert [r["name"] for r in out] == ["B", "A", "C"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_meta_ads_analytics.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement the service**

```python
# backend/app/services/meta_ads_analytics.py
"""Analytics series for the Meta Ads dashboard Analytics tab. Builds funnel,
leaderboard, trend, heatmap, quadrant and spend-distribution from the same
tables as meta_ads_reporting. Revenue/ROAS deliberately absent — no conversion
value source exists yet (see spec)."""
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

_IST = timezone(timedelta(hours=5, minutes=30))


def funnel_stages(clicks: int, messages: int, qualified: int, hot: int) -> list[dict]:
    return [
        {"stage": "Clicked", "count": int(clicks)},
        {"stage": "Messaged", "count": int(messages)},
        {"stage": "Qualified", "count": int(qualified)},
        {"stage": "Hot", "count": int(hot)},
    ]


def leaderboard_sort(rows: list[dict]) -> list[dict]:
    """Worst (highest) cost_per_hot first; None costs sorted last."""
    return sorted(rows, key=lambda r: (r["cost_per_hot"] is None, -(r["cost_per_hot"] or 0)))


def build_analytics(db, tenant_id: str, *, date_from: str | None = None,
                    date_to: str | None = None) -> dict:
    from app.services.meta_ads_reporting import build_account_performance

    per_creative = build_account_performance(db, tenant_id, level="ad",
                                             date_from=date_from, date_to=date_to)

    tot_clicks = sum(r["clicks"] for r in per_creative)
    tot_msgs = sum(r["messages"] for r in per_creative)
    tot_qual = sum(r["qualified"] for r in per_creative)
    tot_hot = sum(r["hot"] for r in per_creative)
    tot_spend = round(sum(r["spend"] for r in per_creative), 2)

    leaderboard = leaderboard_sort([
        {"name": r["name"],
         "cost_per_hot": round(r["spend"] / r["hot"], 2) if r["hot"] else None,
         "hot": r["hot"], "spend": r["spend"]}
        for r in per_creative
    ])
    quadrant = [
        {"name": r["name"], "spend": r["spend"],
         "cost_per_hot": round(r["spend"] / r["hot"], 2) if r["hot"] else None, "hot": r["hot"]}
        for r in per_creative if r["spend"] > 0
    ]
    spend_distribution = [{"name": r["name"], "spend": r["spend"]} for r in per_creative if r["spend"] > 0]

    return {
        "kpis": {
            "spend": tot_spend, "messages": tot_msgs, "qualified": tot_qual, "hot": tot_hot,
            "cost_per_hot": round(tot_spend / tot_hot, 2) if tot_hot else None,
            "roas": None, "revenue_available": False,
        },
        "funnel": funnel_stages(tot_clicks, tot_msgs, tot_qual, tot_hot),
        "leaderboard": leaderboard[:12],
        "trend": _build_trend(db, tenant_id, date_from, date_to),
        "heatmap": _build_heatmap(db, tenant_id, date_from, date_to),
        "quadrant": quadrant,
        "spend_distribution": spend_distribution,
    }


def _build_trend(db, tenant_id, date_from, date_to) -> list[dict]:
    """spend/day (from insights) joined with qualified-leads/day (from leads, IST)."""
    ins_q = db.table("ad_insights_daily").select("insight_date,spend").eq("tenant_id", tenant_id)
    if date_from:
        ins_q = ins_q.gte("insight_date", date_from)
    if date_to:
        ins_q = ins_q.lte("insight_date", date_to)
    spend_by_day: dict[str, float] = {}
    for r in (ins_q.execute().data or []):
        spend_by_day[r["insight_date"]] = spend_by_day.get(r["insight_date"], 0.0) + float(r.get("spend", 0) or 0)

    lead_q = db.table("leads").select("segment,created_at").eq("tenant_id", tenant_id).in_(
        "segment", ["A", "B"]).not_.is_("attributed_ad_creative_id", "null").is_("deleted_at", "null")
    if date_from:
        lead_q = lead_q.gte("created_at", date_from)
    if date_to:
        lead_q = lead_q.lte("created_at", date_to + "T23:59:59")
    qual_by_day: dict[str, int] = {}
    for lead in (lead_q.execute().data or []):
        d = _ist_date(lead.get("created_at"))
        if d:
            qual_by_day[d] = qual_by_day.get(d, 0) + 1

    days = sorted(set(spend_by_day) | set(qual_by_day))
    return [{"date": d, "spend": round(spend_by_day.get(d, 0.0), 2),
             "qualified": qual_by_day.get(d, 0)} for d in days]


def _build_heatmap(db, tenant_id, date_from, date_to) -> list[dict]:
    """qualified leads by IST day-of-week (0=Mon) × hour (0-23)."""
    lead_q = db.table("leads").select("segment,created_at").eq("tenant_id", tenant_id).in_(
        "segment", ["A", "B"]).not_.is_("attributed_ad_creative_id", "null").is_("deleted_at", "null")
    if date_from:
        lead_q = lead_q.gte("created_at", date_from)
    if date_to:
        lead_q = lead_q.lte("created_at", date_to + "T23:59:59")
    grid: dict[tuple[int, int], int] = {}
    for lead in (lead_q.execute().data or []):
        dt = _ist_dt(lead.get("created_at"))
        if not dt:
            continue
        key = (dt.weekday(), dt.hour)
        grid[key] = grid.get(key, 0) + 1
    return [{"dow": dow, "hour": hour, "qualified": count} for (dow, hour), count in sorted(grid.items())]


def _ist_dt(iso: str | None):
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(_IST)
    except Exception:
        return None


def _ist_date(iso: str | None):
    dt = _ist_dt(iso)
    return dt.strftime("%Y-%m-%d") if dt else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_meta_ads_analytics.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/meta_ads_analytics.py backend/tests/test_meta_ads_analytics.py
git commit -m "feat(meta-ads): analytics aggregation service (funnel/leaderboard/trend/heatmap/quadrant)"
```

---

### Task 5: Meta Ads router + wiring (backend routes, main.py, api.ts, hooks)

**Files:**
- Create: `backend/app/routes/meta_ads.py`
- Modify: `backend/app/main.py:13` (import) and `:597` area (include_router)
- Modify: `frontend/lib/api.ts` (add `metaAds` client + types)
- Modify: `frontend/hooks/useApi.ts` (add `useMetaAdsPerformance`, `useMetaAdsAnalytics`)
- Test: `backend/tests/test_meta_ads_route_static.py`

**Interfaces:**
- Consumes: `build_account_performance`, `build_analytics`, existing `build_ad_filter_tree`.
- Produces HTTP:
  - `GET /api/v1/meta-ads/performance?level=&date_from=&date_to=` → `{"data": [...]}`
  - `GET /api/v1/meta-ads/analytics?date_from=&date_to=` → `{"data": {...}}`
  - `GET /api/v1/meta-ads/filters` → campaign/adset/creative tree (reuses `build_ad_filter_tree`)
- Produces TS types `MetaAdsPerfRow`, `MetaAdsAnalytics` and client methods `api.metaAds.performance/analytics/filters`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_meta_ads_route_static.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.routes import meta_ads


def test_router_exposes_expected_paths():
    paths = {r.path for r in meta_ads.router.routes}
    assert "/performance" in paths
    assert "/analytics" in paths
    assert "/filters" in paths
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_meta_ads_route_static.py -v`
Expected: FAIL with `ImportError` (module doesn't exist yet)

- [ ] **Step 3: Create the router and wire it**

```python
# backend/app/routes/meta_ads.py
"""Meta Ads dashboard — read-only full-account performance + analytics.
Reporting only (ads_read). Ad creation/management is a separate router (Plan 2)."""
import logging
from fastapi import APIRouter, Depends, Query

from app.db.supabase import get_supabase
from app.dependencies.tenant import get_tenant_id

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/performance")
async def performance(
    level: str = Query("campaign", pattern="^(campaign|adset|ad)$"),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    tenant_id: str = Depends(get_tenant_id),
):
    from app.services.meta_ads_reporting import build_account_performance
    db = get_supabase()
    try:
        rows = build_account_performance(db, tenant_id, level=level,
                                         date_from=date_from, date_to=date_to)
    except Exception as e:
        logger.error(f"meta-ads performance error: {e}")
        rows = []
    return {"data": rows}


@router.get("/analytics")
async def analytics(
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    tenant_id: str = Depends(get_tenant_id),
):
    from app.services.meta_ads_analytics import build_analytics
    db = get_supabase()
    try:
        data = build_analytics(db, tenant_id, date_from=date_from, date_to=date_to)
    except Exception as e:
        logger.error(f"meta-ads analytics error: {e}")
        data = {"kpis": {}, "funnel": [], "leaderboard": [], "trend": [],
                "heatmap": [], "quadrant": [], "spend_distribution": []}
    return {"data": data}


@router.get("/filters")
async def filters(tenant_id: str = Depends(get_tenant_id)):
    from app.services.ad_performance import build_ad_filter_tree
    db = get_supabase()
    return build_ad_filter_tree(db, tenant_id)
```

In `backend/app/main.py` line 13, add `meta_ads` to the `from app.routes import ...` list. Then near line 597 (after the `inbound_leads` include_router line), add:

```python
app.include_router(meta_ads.router, prefix="/api/v1/meta-ads", tags=["meta-ads"], dependencies=_auth)
```

In `frontend/lib/api.ts`, add types near the other Ad types (after `AdPerformanceParams`):

```typescript
export interface MetaAdsPerfRow {
  group_id: string;
  name: string;
  status: string | null;
  budget_label: string | null;
  result_label: string;
  results: number;
  cost_per_result: number | null;
  spend: number;
  impressions: number;
  reach: number;
  clicks: number;
  messages: number;
  clicked_no_message: number;
  qualified: number;
  hot: number;
}

export interface MetaAdsAnalytics {
  kpis: {
    spend: number; messages: number; qualified: number; hot: number;
    cost_per_hot: number | null; roas: number | null; revenue_available: boolean;
  };
  funnel: { stage: string; count: number }[];
  leaderboard: { name: string; cost_per_hot: number | null; hot: number; spend: number }[];
  trend: { date: string; spend: number; qualified: number }[];
  heatmap: { dow: number; hour: number; qualified: number }[];
  quadrant: { name: string; spend: number; cost_per_hot: number | null; hot: number }[];
  spend_distribution: { name: string; spend: number }[];
}
```

Add the client block near `inboundLeads` (top-level in the `api` object):

```typescript
  metaAds: {
    performance: async (params?: { level?: string; date_from?: string; date_to?: string }) => {
      const qs = new URLSearchParams();
      if (params?.level) qs.set("level", params.level);
      if (params?.date_from) qs.set("date_from", params.date_from);
      if (params?.date_to) qs.set("date_to", params.date_to);
      return apiFetch<{ data: MetaAdsPerfRow[] }>(`/api/v1/meta-ads/performance?${qs}`);
    },
    analytics: async (params?: { date_from?: string; date_to?: string }) => {
      const qs = new URLSearchParams();
      if (params?.date_from) qs.set("date_from", params.date_from);
      if (params?.date_to) qs.set("date_to", params.date_to);
      return apiFetch<{ data: MetaAdsAnalytics }>(`/api/v1/meta-ads/analytics?${qs}`);
    },
    filters: async () => apiFetch<AdFilterTree>(`/api/v1/meta-ads/filters`),
  },
```

In `frontend/hooks/useApi.ts`, add imports for `MetaAdsPerfRow, MetaAdsAnalytics` to the existing `@/lib/api` import block, then add:

```typescript
export function useMetaAdsPerformance(
  params: { level?: string; date_from?: string; date_to?: string },
  enabled = true,
) {
  const key = enabled ? `meta-ads/performance:${JSON.stringify(params)}` : null;
  return useSWR<{ data: MetaAdsPerfRow[] }>(
    key,
    () => api.metaAds.performance(params),
    defaultConfig,
  );
}

export function useMetaAdsAnalytics(
  params: { date_from?: string; date_to?: string },
  enabled = true,
) {
  const key = enabled ? `meta-ads/analytics:${JSON.stringify(params)}` : null;
  return useSWR<{ data: MetaAdsAnalytics }>(
    key,
    () => api.metaAds.analytics(params),
    defaultConfig,
  );
}
```

- [ ] **Step 4: Run backend test + frontend typecheck**

Run: `cd backend && pytest tests/test_meta_ads_route_static.py -v`
Expected: PASS (1 passed)

Run: `cd frontend && npm run lint && npm run typecheck`
Expected: no errors

- [ ] **Step 5: Commit**

```bash
git add backend/app/routes/meta_ads.py backend/app/main.py backend/tests/test_meta_ads_route_static.py frontend/lib/api.ts frontend/hooks/useApi.ts
git commit -m "feat(meta-ads): reporting router + api client + swr hooks"
```

---

### Task 6: Meta Ads page shell, route, and sidebar entry

**Files:**
- Create: `frontend/app/dashboard/meta-ads/page.tsx`
- Create: `frontend/app/dashboard/meta-ads/MetaAdsClient.tsx`
- Modify: `frontend/components/sidebar.tsx` (import an icon + add nav item)

**Interfaces:**
- Produces: the `/dashboard/meta-ads` route rendering a two-tab client (`Ad Performance` | `Analytics`) with shared date filters. Tab components are added in Tasks 7–8; this task renders empty placeholders so the shell compiles and the tabs switch.

- [ ] **Step 1: Create the server page**

```tsx
// frontend/app/dashboard/meta-ads/page.tsx
import { MetaAdsClient } from "./MetaAdsClient";

export default function MetaAdsPage() {
  return <MetaAdsClient />;
}
```

- [ ] **Step 2: Create the client shell with tab switcher**

```tsx
// frontend/app/dashboard/meta-ads/MetaAdsClient.tsx
"use client";
import { useState } from "react";
import { cn } from "@/lib/utils";
import { MetaAdsPerformanceTab } from "./MetaAdsPerformanceTab";
import { MetaAdsAnalyticsTab } from "./MetaAdsAnalyticsTab";

type Tab = "performance" | "analytics";

export function MetaAdsClient() {
  const [tab, setTab] = useState<Tab>("performance");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const pill = (t: Tab, label: string) => (
    <button
      onClick={() => setTab(t)}
      className={cn(
        "px-4 py-2 rounded-full font-label text-sm font-bold transition-all",
        tab === t ? "bg-primary text-white shadow-sm" : "text-on-surface-muted hover:bg-surface-low",
      )}
    >
      {label}
    </button>
  );

  return (
    <div className="p-6 md:p-8">
      <header className="mb-6">
        <h1 className="font-display text-2xl font-bold text-on-surface">Meta Ads</h1>
        <p className="font-body text-sm text-on-surface-muted mt-1">
          Full-account ad performance and lead-quality analytics across your Meta campaigns.
        </p>
      </header>

      <div className="mb-5 flex flex-wrap items-center gap-2 rounded-full bg-surface-low/60 p-1 w-fit">
        {pill("performance", "Ad Performance")}
        {pill("analytics", "Analytics")}
      </div>

      {tab === "performance" ? (
        <MetaAdsPerformanceTab dateFrom={dateFrom} dateTo={dateTo}
          setDateFrom={setDateFrom} setDateTo={setDateTo} />
      ) : (
        <MetaAdsAnalyticsTab dateFrom={dateFrom} dateTo={dateTo}
          setDateFrom={setDateFrom} setDateTo={setDateTo} />
      )}
    </div>
  );
}
```

- [ ] **Step 3: Add temporary placeholder tab files (replaced in Tasks 7–8)**

Create `frontend/app/dashboard/meta-ads/MetaAdsPerformanceTab.tsx` and `MetaAdsAnalyticsTab.tsx`, each:

```tsx
"use client";
type Props = {
  dateFrom: string; dateTo: string;
  setDateFrom: (v: string) => void; setDateTo: (v: string) => void;
};
export function MetaAdsPerformanceTab(_props: Props) {
  return <div className="text-sm text-on-surface-muted">Performance tab — built in Task 7.</div>;
}
```

(For the analytics file, name the export `MetaAdsAnalyticsTab` and change the text to "Analytics tab — built in Task 8.")

- [ ] **Step 4: Add the sidebar entry**

In `frontend/components/sidebar.tsx`, add `Megaphone` to the `lucide-react` import (line 8–11 block). Then, immediately after the Inbound Leads `<Link>` block (ends ~line 241), add:

```tsx
        {/* TOP LEVEL: Meta Ads */}
        {isSubscribed && can("inbound_leads.view") && inboundOn && (
          <Link
            href="/dashboard/meta-ads"
            className={cn(
              "flex items-center gap-3 px-3 py-2 rounded-xl text-sm font-semibold transition-all duration-150 group",
              pathname.startsWith("/dashboard/meta-ads")
                ? "bg-[#f5f3ff] text-[#5b21b6]"
                : "text-[#1c1917] hover:bg-[#f0ece4] hover:text-[#1c1917]"
            )}
          >
            <Megaphone size={16} className={pathname.startsWith("/dashboard/meta-ads") ? "text-[#5b21b6]" : "text-[#1c1917] group-hover:text-[#1c1917]"} />
            <span>Meta Ads</span>
          </Link>
        )}
```

- [ ] **Step 5: Verify build + lint**

Run: `cd frontend && npm run lint && npm run typecheck`
Expected: no errors

- [ ] **Step 6: Commit**

```bash
git add frontend/app/dashboard/meta-ads/ frontend/components/sidebar.tsx
git commit -m "feat(meta-ads): page shell, route, tab switcher, sidebar entry"
```

---

### Task 7: Ad Performance tab (full-account table)

**Files:**
- Modify (replace placeholder): `frontend/app/dashboard/meta-ads/MetaAdsPerformanceTab.tsx`

**Interfaces:**
- Consumes: `useMetaAdsPerformance`, `MetaAdsPerfRow`. Props from Task 6 shell.
- Produces: a level switcher (Campaign/Ad set/Ad), date filters, and a table with status badges + budget + Meta metrics + Aira funnel columns.

- [ ] **Step 1: Implement the tab**

```tsx
// frontend/app/dashboard/meta-ads/MetaAdsPerformanceTab.tsx
"use client";
import { useMemo, useState } from "react";
import { MetaAdsPerfRow } from "@/lib/api";
import { useMetaAdsPerformance } from "@/hooks/useApi";
import { RefreshCw, Megaphone } from "lucide-react";
import { cn } from "@/lib/utils";

type Props = {
  dateFrom: string; dateTo: string;
  setDateFrom: (v: string) => void; setDateTo: (v: string) => void;
};

function money(n: number | null | undefined) {
  if (n == null) return "—";
  return "₹" + Math.round(n).toLocaleString("en-IN");
}

function StatusBadge({ status }: { status: string | null }) {
  if (!status) return <span className="text-on-surface-muted">—</span>;
  const s = status.toUpperCase();
  const map: Record<string, { label: string; cls: string }> = {
    ACTIVE: { label: "Active", cls: "bg-emerald-50 text-emerald-700" },
    PAUSED: { label: "Paused", cls: "bg-surface-low text-on-surface-muted" },
    IN_PROCESS: { label: "In review", cls: "bg-amber-50 text-amber-700" },
    PENDING_REVIEW: { label: "In review", cls: "bg-amber-50 text-amber-700" },
    DISAPPROVED: { label: "Rejected", cls: "bg-red-50 text-red-600" },
    WITH_ISSUES: { label: "Issues", cls: "bg-red-50 text-red-600" },
  };
  const m = map[s] ?? { label: status, cls: "bg-surface-low text-on-surface-muted" };
  return <span className={cn("px-2 py-0.5 rounded-full text-[11px] font-bold", m.cls)}>{m.label}</span>;
}

const LEVELS: { key: string; label: string }[] = [
  { key: "campaign", label: "Campaign" },
  { key: "adset", label: "Ad set" },
  { key: "ad", label: "Ad" },
];

export function MetaAdsPerformanceTab({ dateFrom, dateTo, setDateFrom, setDateTo }: Props) {
  const [level, setLevel] = useState("campaign");
  const params = { level, date_from: dateFrom || undefined, date_to: dateTo || undefined };
  const { data, isValidating, mutate } = useMetaAdsPerformance(params);
  const rows: MetaAdsPerfRow[] = useMemo(() => data?.data ?? [], [data]);

  const headers = ["Name", "Status", "Budget", "Spend", "Impr.", "Reach", "Results",
    "Cost/Result", "Clicks", "Messages", "No message", "Qualified", "Hot"];

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-end gap-2.5">
        <div className="flex gap-1 rounded-full bg-surface-low/60 p-1">
          {LEVELS.map((l) => (
            <button key={l.key} onClick={() => setLevel(l.key)}
              className={cn("px-3 py-1.5 rounded-full text-xs font-bold transition-all",
                level === l.key ? "bg-white shadow-sm text-primary" : "text-on-surface-muted")}>
              {l.label}
            </button>
          ))}
        </div>
        <div className="w-[140px]">
          <label className="mb-1 block font-label text-[9px] font-bold uppercase tracking-wider text-on-surface-muted">From</label>
          <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)}
            className="h-9 w-full rounded-xl border border-surface-mid bg-white px-3 font-body text-xs font-semibold text-on-surface focus:outline-none focus:ring-2 focus:ring-violet-200" />
        </div>
        <div className="w-[140px]">
          <label className="mb-1 block font-label text-[9px] font-bold uppercase tracking-wider text-on-surface-muted">To</label>
          <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)}
            className="h-9 w-full rounded-xl border border-surface-mid bg-white px-3 font-body text-xs font-semibold text-on-surface focus:outline-none focus:ring-2 focus:ring-violet-200" />
        </div>
        <button onClick={() => mutate()} disabled={isValidating}
          className="flex items-center justify-center gap-2 px-3 py-2 rounded-xl bg-white border border-[#e8e3db] hover:bg-[#f0ece4] text-[#1c1917] font-label text-xs font-bold transition-all disabled:opacity-40 shadow-sm">
          <RefreshCw size={12} className={isValidating ? "animate-spin" : ""} /> Refresh
        </button>
      </div>

      <div className="card rounded-2xl overflow-hidden">
        {rows.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-center px-4">
            <div className="w-14 h-14 rounded-2xl bg-violet-50 flex items-center justify-center mb-3">
              <Megaphone size={24} className="text-violet-400" />
            </div>
            <h3 className="font-bold text-[#44403c] text-base mb-1">No ad data yet</h3>
            <p className="text-sm text-[#a8a29e] max-w-sm leading-relaxed">
              Once your Meta ads deliver and the daily sync runs, campaigns appear here with
              spend, results and lead-quality breakdown.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[1000px]">
              <thead>
                <tr className="border-b border-surface-mid bg-surface-low/60">
                  {headers.map((h, i) => (
                    <th key={h} className={cn(
                      "px-4 py-3 font-label text-[10px] font-bold text-on-surface-muted uppercase tracking-wider whitespace-nowrap",
                      i === 0 ? "text-left" : i === 1 ? "text-center" : "text-right")}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-mid/50">
                {rows.map((r) => (
                  <tr key={r.group_id} className="hover:bg-surface-low/60 transition-colors">
                    <td className="px-4 py-3"><span className="font-label text-sm font-semibold text-on-surface">{r.name}</span></td>
                    <td className="px-4 py-3 text-center"><StatusBadge status={r.status} /></td>
                    <td className="px-4 py-3 text-right text-xs text-on-surface-muted whitespace-nowrap">{r.budget_label ?? "—"}</td>
                    <td className="px-4 py-3 text-right tabular-nums">{money(r.spend)}</td>
                    <td className="px-4 py-3 text-right tabular-nums text-on-surface-muted">{r.impressions.toLocaleString("en-IN")}</td>
                    <td className="px-4 py-3 text-right tabular-nums text-on-surface-muted">{r.reach.toLocaleString("en-IN")}</td>
                    <td className="px-4 py-3 text-right tabular-nums font-semibold text-on-surface" title={r.result_label}>{r.results.toLocaleString("en-IN")}</td>
                    <td className="px-4 py-3 text-right tabular-nums">{money(r.cost_per_result)}</td>
                    <td className="px-4 py-3 text-right tabular-nums text-violet-700">{r.clicks.toLocaleString("en-IN")}</td>
                    <td className="px-4 py-3 text-right tabular-nums font-bold">{r.messages.toLocaleString("en-IN")}</td>
                    <td className="px-4 py-3 text-right tabular-nums text-on-surface-muted">{r.clicked_no_message.toLocaleString("en-IN")}</td>
                    <td className="px-4 py-3 text-right tabular-nums text-on-surface-muted">{r.qualified}</td>
                    <td className="px-4 py-3 text-right tabular-nums font-semibold text-emerald-700">{r.hot}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify build + lint**

Run: `cd frontend && npm run lint && npm run typecheck`
Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add frontend/app/dashboard/meta-ads/MetaAdsPerformanceTab.tsx
git commit -m "feat(meta-ads): full-account Ad Performance table with status badges"
```

---

### Task 8: Analytics tab (KPI cards + charts)

**Files:**
- Modify (replace placeholder): `frontend/app/dashboard/meta-ads/MetaAdsAnalyticsTab.tsx`

**Interfaces:**
- Consumes: `useMetaAdsAnalytics`, `MetaAdsAnalytics`. Props from Task 6 shell.
- Produces: KPI card row, funnel bars, cost-per-hot leaderboard, spend-vs-qualified trend (single-axis), qualified-lead day×hour heatmap, spend-efficiency quadrant, spend-distribution donut. All Recharts. Follows dataviz rules: one hue for magnitude, status-red reserved for the single worst outlier, one axis on the trend (spend as a faint secondary line indexed via a right-hidden scale is avoided — instead spend is shown as a separate faint area on the same qualified scale is NOT valid; the trend shows qualified-leads as the primary line and spend as a **separate small area chart stacked below**, not a dual axis).

- [ ] **Step 1: Implement the tab**

```tsx
// frontend/app/dashboard/meta-ads/MetaAdsAnalyticsTab.tsx
"use client";
import { useMemo, type ReactNode } from "react";
import { MetaAdsAnalytics } from "@/lib/api";
import { useMetaAdsAnalytics } from "@/hooks/useApi";
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid,
  LineChart, Line, AreaChart, Area, ScatterChart, Scatter, ZAxis, PieChart, Pie, Cell, Legend,
} from "recharts";

type Props = {
  dateFrom: string; dateTo: string;
  setDateFrom: (v: string) => void; setDateTo: (v: string) => void;
};

const VIOLET = "#5b21b6";
const VIOLET_SHADES = ["#5b21b6", "#7c3aed", "#8b5cf6", "#a78bfa", "#c4b5fd", "#ddd6fe"];
const RED = "#e5484d";
const DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function money(n: number | null | undefined) {
  if (n == null) return "—";
  return "₹" + Math.round(n).toLocaleString("en-IN");
}

function Card({ title, children, sub }: { title: string; children: ReactNode; sub?: string }) {
  return (
    <div className="bg-surface rounded-card p-6 shadow-card ring-1 ring-[#c4c7c7]/15">
      <h2 className="font-display text-base font-bold text-primary mb-1">{title}</h2>
      {sub && <p className="font-label text-xs text-on-surface-muted mb-4">{sub}</p>}
      {children}
    </div>
  );
}

export function MetaAdsAnalyticsTab({ dateFrom, dateTo, setDateFrom, setDateTo }: Props) {
  const { data } = useMetaAdsAnalytics({ date_from: dateFrom || undefined, date_to: dateTo || undefined });
  const a: MetaAdsAnalytics | undefined = data?.data;

  // Heatmap max for shading intensity
  const heatMax = useMemo(() => Math.max(1, ...(a?.heatmap ?? []).map((h) => h.qualified)), [a]);
  const heatLookup = useMemo(() => {
    const m: Record<string, number> = {};
    for (const h of a?.heatmap ?? []) m[`${h.dow}-${h.hour}`] = h.qualified;
    return m;
  }, [a]);

  // Leaderboard: worst (first) gets red, rest violet
  const leaderboard = a?.leaderboard ?? [];

  return (
    <div className="space-y-6">
      {/* Date filters */}
      <div className="flex flex-wrap items-end gap-2.5">
        <div className="w-[140px]">
          <label className="mb-1 block font-label text-[9px] font-bold uppercase tracking-wider text-on-surface-muted">From</label>
          <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)}
            className="h-9 w-full rounded-xl border border-surface-mid bg-white px-3 font-body text-xs font-semibold text-on-surface focus:outline-none focus:ring-2 focus:ring-violet-200" />
        </div>
        <div className="w-[140px]">
          <label className="mb-1 block font-label text-[9px] font-bold uppercase tracking-wider text-on-surface-muted">To</label>
          <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)}
            className="h-9 w-full rounded-xl border border-surface-mid bg-white px-3 font-body text-xs font-semibold text-on-surface focus:outline-none focus:ring-2 focus:ring-violet-200" />
        </div>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {([
          { label: "SPEND", value: money(a?.kpis.spend), highlight: false },
          { label: "MESSAGES", value: (a?.kpis.messages ?? 0).toLocaleString("en-IN"), highlight: false },
          { label: "QUALIFIED", value: (a?.kpis.qualified ?? 0).toLocaleString("en-IN"), highlight: false },
          { label: "COST / HOT LEAD", value: money(a?.kpis.cost_per_hot), highlight: true },
        ] as { label: string; value: string; highlight: boolean }[]).map((k) => (
          <div key={k.label} className={cnCard(k.highlight)}>
            <div className="font-label text-[10px] font-bold uppercase tracking-wider text-on-surface-muted">{k.label}</div>
            <div className={`text-xl font-bold mt-1 ${k.highlight ? "text-primary" : "text-on-surface"}`}>{k.value}</div>
          </div>
        ))}
        <div className="rounded-card p-4 bg-surface-low/40 ring-1 ring-[#c4c7c7]/15 opacity-70">
          <div className="font-label text-[10px] font-bold uppercase tracking-wider text-on-surface-muted">ROAS</div>
          <div className="text-xs mt-1 text-on-surface-muted">Needs revenue tracking — not built yet</div>
        </div>
      </div>

      {/* Funnel + Leaderboard */}
      <div className="grid md:grid-cols-2 gap-6">
        <Card title="Lead funnel" sub="Where ad-driven leads drop off">
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={a?.funnel ?? []} layout="vertical" margin={{ left: 20, right: 16 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0ece4" horizontal={false} />
              <XAxis type="number" tick={{ fontSize: 10, fill: "#a8a29e" }} />
              <YAxis type="category" dataKey="stage" tick={{ fontSize: 11, fill: "#78716c" }} width={70} />
              <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e8e3db" }} />
              <Bar dataKey="count" radius={[0, 4, 4, 0]} fill={VIOLET} name="Leads" />
            </BarChart>
          </ResponsiveContainer>
        </Card>

        <Card title="Creative leaderboard" sub="Cost per hot lead — lower is better">
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={leaderboard} layout="vertical" margin={{ left: 20, right: 16 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0ece4" horizontal={false} />
              <XAxis type="number" tick={{ fontSize: 10, fill: "#a8a29e" }} />
              <YAxis type="category" dataKey="name" tick={{ fontSize: 11, fill: "#78716c" }} width={90} />
              <Tooltip formatter={(v: number) => money(v)} contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e8e3db" }} />
              <Bar dataKey="cost_per_hot" radius={[0, 4, 4, 0]} name="Cost/hot">
                {leaderboard.map((_, i) => <Cell key={i} fill={i === 0 ? RED : VIOLET} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Card>
      </div>

      {/* Trend: qualified line (primary) + spend area (separate, same time axis, own scale) */}
      <Card title="Qualified leads per day" sub="Ad-driven qualified leads over time">
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={a?.trend ?? []} margin={{ top: 4, right: 8, bottom: 0, left: -10 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0ece4" />
            <XAxis dataKey="date" tick={{ fontSize: 9, fill: "#a8a29e" }} />
            <YAxis tick={{ fontSize: 10, fill: "#a8a29e" }} allowDecimals={false} />
            <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e8e3db" }} />
            <Line type="monotone" dataKey="qualified" stroke={VIOLET} strokeWidth={2} dot={false} name="Qualified leads" />
          </LineChart>
        </ResponsiveContainer>
        <p className="font-label text-[11px] text-on-surface-muted mt-2 mb-1">Spend per day (₹)</p>
        <ResponsiveContainer width="100%" height={80}>
          <AreaChart data={a?.trend ?? []} margin={{ top: 0, right: 8, bottom: 0, left: -10 }}>
            <XAxis dataKey="date" hide />
            <YAxis tick={{ fontSize: 9, fill: "#a8a29e" }} width={40} />
            <Tooltip formatter={(v: number) => money(v)} contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e8e3db" }} />
            <Area type="monotone" dataKey="spend" stroke="#c4b5fd" fill="#ede9fe" name="Spend" />
          </AreaChart>
        </ResponsiveContainer>
      </Card>

      {/* Heatmap */}
      <Card title="When leads qualify" sub="Qualified leads by day × hour (IST) — darker = more">
        <div className="overflow-x-auto">
          <div className="min-w-[560px]">
            <div className="grid" style={{ gridTemplateColumns: `40px repeat(24, 1fr)`, gap: 2 }}>
              <div />
              {Array.from({ length: 24 }).map((_, h) => (
                <div key={h} className="text-[8px] text-center text-on-surface-muted">{h % 3 === 0 ? h : ""}</div>
              ))}
              {DOW.map((label, dow) => (
                <FragmentRow key={dow} label={label} dow={dow} heatLookup={heatLookup} heatMax={heatMax} />
              ))}
            </div>
          </div>
        </div>
      </Card>

      {/* Quadrant + Donut */}
      <div className="grid md:grid-cols-2 gap-6">
        <Card title="Spend efficiency" sub="Bottom-left = scale up · top-right = cut or fix">
          <ResponsiveContainer width="100%" height={260}>
            <ScatterChart margin={{ top: 10, right: 16, bottom: 10, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0ece4" />
              <XAxis type="number" dataKey="spend" name="Spend" tick={{ fontSize: 10, fill: "#a8a29e" }}
                tickFormatter={(v) => money(v)} />
              <YAxis type="number" dataKey="cost_per_hot" name="Cost/hot" tick={{ fontSize: 10, fill: "#a8a29e" }}
                tickFormatter={(v) => money(v)} />
              <ZAxis type="number" dataKey="hot" range={[60, 400]} name="Hot" />
              <Tooltip cursor={{ strokeDasharray: "3 3" }} formatter={(v: number) => money(v)}
                contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e8e3db" }} />
              <Scatter data={(a?.quadrant ?? []).filter((q) => q.cost_per_hot != null)} fill={VIOLET} fillOpacity={0.7} />
            </ScatterChart>
          </ResponsiveContainer>
        </Card>

        <Card title="Spend distribution" sub="Where budget is going">
          <ResponsiveContainer width="100%" height={260}>
            <PieChart>
              <Pie data={a?.spend_distribution ?? []} dataKey="spend" nameKey="name"
                innerRadius={55} outerRadius={90} paddingAngle={2}>
                {(a?.spend_distribution ?? []).map((_, i) => (
                  <Cell key={i} fill={VIOLET_SHADES[i % VIOLET_SHADES.length]} />
                ))}
              </Pie>
              <Tooltip formatter={(v: number) => money(v)} contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e8e3db" }} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
            </PieChart>
          </ResponsiveContainer>
        </Card>
      </div>
    </div>
  );
}

function cnCard(highlight?: boolean) {
  return `rounded-card p-4 bg-surface ring-1 ${highlight ? "ring-primary/40" : "ring-[#c4c7c7]/15"} shadow-card`;
}

function FragmentRow({ label, dow, heatLookup, heatMax }:
  { label: string; dow: number; heatLookup: Record<string, number>; heatMax: number }) {
  return (
    <>
      <div className="text-[9px] text-on-surface-muted flex items-center">{label}</div>
      {Array.from({ length: 24 }).map((_, hour) => {
        const v = heatLookup[`${dow}-${hour}`] ?? 0;
        const alpha = v === 0 ? 0.04 : 0.15 + 0.85 * (v / heatMax);
        return (
          <div key={hour} title={`${label} ${hour}:00 — ${v} qualified`}
            className="h-4 rounded-sm" style={{ backgroundColor: `rgba(91,33,182,${alpha})` }} />
        );
      })}
    </>
  );
}
```

- [ ] **Step 2: Verify build + lint**

Run: `cd frontend && npm run lint && npm run typecheck`
Expected: no errors (note: `cnCard`/`FragmentRow` are defined and used; no `any`; `Legend`/`ZAxis` imported)

- [ ] **Step 3: Commit**

```bash
git add frontend/app/dashboard/meta-ads/MetaAdsAnalyticsTab.tsx
git commit -m "feat(meta-ads): Analytics tab — KPI cards + funnel/leaderboard/trend/heatmap/quadrant/donut"
```

---

### Task 9: Full verification pass

**Files:** none (verification only)

- [ ] **Step 1: Backend suite**

Run: `cd backend && pytest -q`
Expected: all new tests pass; no new failures beyond the pre-existing env-only ones documented in the backlog.

- [ ] **Step 2: Frontend gates**

Run: `cd frontend && npm run lint && npm run typecheck && npm run build`
Expected: all pass, `/dashboard/meta-ads` compiles as a route.

- [ ] **Step 3: Live smoke test (manual)**

Run backend (`cd backend && uvicorn app.main:app --reload`) + frontend (`cd frontend && npm run dev`). As a tenant with Meta ads credentials configured (`meta_ads_access_token`/`meta_ads_account_id`):
1. Trigger a sync (existing Inbound Leads → Sync Now button) so `ad_insights_daily` has the new columns populated.
2. Open **Meta Ads** in the sidebar. Confirm the Ad Performance table renders campaign rows with status badge + budget + spend + results.
3. Switch level to Ad set and Ad — confirm rollup regroups.
4. Open Analytics — confirm KPI cards, funnel, leaderboard, trend, heatmap, quadrant, donut all render (empty-safe if no data).

- [ ] **Step 4: Commit any fixes found, then finalize**

```bash
git add -A
git commit -m "fix(meta-ads): verification-pass fixes"
```

---

## Self-Review Notes

- **Spec coverage:** Page structure (Meta Ads sidebar page, Performance + Analytics tabs) → Tasks 6–8. Widened Insights fetch (`actions`/impressions/reach + campaign-level status/budget/objective) → Tasks 1–2. Full-account Performance table with status badges + budget → Tasks 3, 5, 7. Analytics chart set (KPI, funnel, leaderboard, trend, heatmap, quadrant, donut; ROAS greyed) → Tasks 4, 8. **Deferred to Plan 2 (correctly out of this plan):** the Create wizard, status/budget *write* actions, the `ad_sets` table and `ad_creatives` create-columns, and the Facebook-Login-for-Business consent flow — all require `ads_management`.
- **Inbound Leads Ad Performance tab** stays untouched (spec's "what stays unchanged") — no task modifies `frontend/app/dashboard/inbound-leads/` or `backend/app/routes/inbound_leads.py`.
- **Dual-axis avoidance:** the trend is split into two stacked single-axis charts (qualified line, spend area) rather than one dual-axis chart, per the dataviz non-negotiable.
- **Status colors reserved:** emerald only for Active/Hot, red only for Rejected and the single worst leaderboard bar — never as a generic series hue.
