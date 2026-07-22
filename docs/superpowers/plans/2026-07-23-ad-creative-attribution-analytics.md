# Ad-Creative Attribution & Analytics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-creative (per-ad) attribution and an "Ad Performance" analytics tab inside the Inbound Leads page, so a tenant can see clicks, messages, clicked-no-message, funnel, spend and cost metrics broken down by campaign → ad set → creative.

**Architecture:** A scheduled backend job pulls Meta Ads Insights (`level=ad`) per tenant, auto-imports each ad as an `ad_creatives` row, and stores daily `clicks`/`inline_link_clicks`/`spend` in `ad_insights_daily`. The existing WhatsApp webhook is extended to also stamp `leads.attributed_ad_creative_id` from the CTWA referral `ad_id`. A new aggregation function joins creatives × insights × leads; new endpoints in `inbound_leads.py` serve the per-creative table, the cascading filter tree, and a CSV export. The frontend adds a two-tab switch (Leads / Ad Performance) and a new `AdPerformanceTab` component.

**Tech Stack:** FastAPI (Python 3.11, Pydantic v2), Supabase (Postgres) via `db.table(...)`, APScheduler (`AsyncIOScheduler`), Next.js 14 App Router, SWR, Tailwind, lucide-react, `httpx` for Graph API calls, `pytest` for backend tests.

## Global Constraints

- Every new table has `tenant_id uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE` and `ENABLE ROW LEVEL SECURITY` with the same two-policy pattern as `tenant_token_usage` (admin-all + tenant-read). Backend writes run under the service role (bypasses RLS).
- Meta Graph API version: `v21.0` (matches `_GRAPH_BASE` in `services/meta_cloud.py`). Base: `https://graph.facebook.com/v21.0`.
- "Clicks" everywhere = Meta `inline_link_clicks` (NOT `clicks`). CPC = `spend ÷ inline_link_clicks`.
- Per-tenant Meta Ads credentials live in `app_settings` (key/value, plaintext `value` column): keys `meta_ads_access_token` and `meta_ads_account_id`. Account id is normalized to `act_<digits>` form.
- Attribution never clobbers a prior attribution — only set `attributed_ad_creative_id` when currently NULL (mirrors the existing Google-ads guard at `webhook.py:485`).
- Frontend: CI runs `npm run lint` AND `npm run typecheck` — both must pass (no unused imports, no `any`). All new buttons/controls reuse existing polished styles (`rounded-xl`/`rounded-full`, `shadow-sm`, violet hover, lucide icons) — no plain buttons.
- Migration file number: `147` (144 already collided; latest is 146).

---

## File Structure

**Backend**
- Create `backend/supabase/migrations/147_ad_creative_attribution.sql` — the two new tables + `leads.attributed_ad_creative_id`.
- Create `backend/app/services/meta_ads_insights_sync.py` — Graph client, credential read, creative upsert, daily-insight write, per-tenant + all-tenant sync entrypoints.
- Create `backend/app/services/ad_performance.py` — pure cost-metric computation + the per-creative aggregation (kept out of the already-large `growth.py`; imported where needed).
- Modify `backend/app/routes/webhook.py:437-459` — stamp `attributed_ad_creative_id` on CTWA match.
- Modify `backend/app/routes/inbound_leads.py` — add `/ad-filters`, `/ad-performance`, `/ad-performance/export`.
- Modify `backend/app/main.py:~387` — register the sync scheduler job.
- Create `backend/tests/test_ad_performance.py` and `backend/tests/test_meta_ads_insights_sync.py`.

**Frontend**
- Modify `frontend/lib/api.ts` — add `inboundLeads.adFilters`, `inboundLeads.adPerformance`, `inboundLeads.adPerformanceExportCsv`, and the `AdPerformanceRow`/`AdFilterTree` types.
- Modify `frontend/hooks/useApi.ts` — add `useAdFilters`, `useAdPerformance`.
- Create `frontend/app/dashboard/inbound-leads/AdPerformanceTab.tsx` — the new tab UI.
- Modify `frontend/app/dashboard/inbound-leads/InboundLeadsClient.tsx` — wrap existing body in a tab shell; render `AdPerformanceTab` for the second tab.

---

## Task 1: Schema migration

**Files:**
- Create: `backend/supabase/migrations/147_ad_creative_attribution.sql`

**Interfaces:**
- Produces tables `ad_creatives`, `ad_insights_daily` and column `leads.attributed_ad_creative_id` used by every later task.

- [ ] **Step 1: Write the migration SQL**

Create `backend/supabase/migrations/147_ad_creative_attribution.sql`:

```sql
-- 147: Per-creative (per-ad) attribution + daily Meta Ads insights.
-- ad_creatives is auto-imported by services/meta_ads_insights_sync.py from
-- Meta's level=ad Insights response; the WhatsApp webhook stamps
-- leads.attributed_ad_creative_id from the CTWA referral ad_id. All writes are
-- service-role; RLS mirrors the tenant_token_usage pattern (admin-all + tenant-read).

CREATE TABLE public.ad_creatives (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
  campaign_id uuid REFERENCES public.ad_campaigns(id) ON DELETE SET NULL,
  meta_ad_id text NOT NULL,
  meta_adset_id text,
  meta_adset_name text,
  meta_campaign_id text,
  creative_label text NOT NULL,
  label_edited boolean NOT NULL DEFAULT false,
  prefilled_message_code text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, meta_ad_id)
);

CREATE INDEX idx_ad_creatives_tenant ON public.ad_creatives (tenant_id);
CREATE INDEX idx_ad_creatives_campaign ON public.ad_creatives (campaign_id);

CREATE TABLE public.ad_insights_daily (
  tenant_id uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
  ad_creative_id uuid NOT NULL REFERENCES public.ad_creatives(id) ON DELETE CASCADE,
  insight_date date NOT NULL,
  clicks bigint NOT NULL DEFAULT 0,
  inline_link_clicks bigint NOT NULL DEFAULT 0,
  spend numeric(14,2) NOT NULL DEFAULT 0,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, ad_creative_id, insight_date)
);

CREATE INDEX idx_ad_insights_daily_date ON public.ad_insights_daily (tenant_id, insight_date);

ALTER TABLE public.leads
  ADD COLUMN IF NOT EXISTS attributed_ad_creative_id uuid
  REFERENCES public.ad_creatives(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_leads_attributed_creative
  ON public.leads (attributed_ad_creative_id)
  WHERE attributed_ad_creative_id IS NOT NULL;

-- RLS: admin-all + tenant-read (same shape as tenant_token_usage)
ALTER TABLE public.ad_creatives ENABLE ROW LEVEL SECURITY;
CREATE POLICY ad_creatives_admin_all ON public.ad_creatives
  USING (EXISTS (SELECT 1 FROM system_admins WHERE system_admins.user_id = auth.uid()));
CREATE POLICY ad_creatives_tenant_read ON public.ad_creatives
  FOR SELECT
  USING (EXISTS (SELECT 1 FROM tenant_users tu
                 WHERE tu.tenant_id = ad_creatives.tenant_id AND tu.user_id = auth.uid()));

ALTER TABLE public.ad_insights_daily ENABLE ROW LEVEL SECURITY;
CREATE POLICY ad_insights_daily_admin_all ON public.ad_insights_daily
  USING (EXISTS (SELECT 1 FROM system_admins WHERE system_admins.user_id = auth.uid()));
CREATE POLICY ad_insights_daily_tenant_read ON public.ad_insights_daily
  FOR SELECT
  USING (EXISTS (SELECT 1 FROM tenant_users tu
                 WHERE tu.tenant_id = ad_insights_daily.tenant_id AND tu.user_id = auth.uid()));
```

- [ ] **Step 2: Apply the migration via Supabase MCP**

Apply the file with the Supabase MCP `apply_migration` tool (name `147_ad_creative_attribution`), or in a local stack `supabase db push`. Then verify with the Supabase MCP `list_tables` that `ad_creatives` and `ad_insights_daily` exist and `leads.attributed_ad_creative_id` is present.

Expected: both tables listed; `leads` shows the new nullable column.

- [ ] **Step 3: Commit**

```bash
git add backend/supabase/migrations/147_ad_creative_attribution.sql
git commit -m "feat: schema for ad-creative attribution + daily insights"
```

---

## Task 2: Meta Ads Insights sync service

**Files:**
- Create: `backend/app/services/meta_ads_insights_sync.py`
- Test: `backend/tests/test_meta_ads_insights_sync.py`

**Interfaces:**
- Consumes: `ad_creatives`, `ad_insights_daily` (Task 1); `get_or_create_campaign` from `app.services.growth`.
- Produces:
  - `normalize_account_id(raw: str) -> str` → returns `act_<digits>`.
  - `upsert_creative_from_insight(db, tenant_id: str, row: dict) -> str | None` → returns `ad_creatives.id`.
  - `sync_tenant_ad_insights(db, tenant_id: str, *, date_preset: str = "last_30d") -> int` → rows written.
  - `sync_all_tenants_ad_insights() -> None` → scheduler entrypoint.

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_meta_ads_insights_sync.py`:

```python
from app.services.meta_ads_insights_sync import (
    normalize_account_id,
    upsert_creative_from_insight,
)


def test_normalize_account_id_adds_prefix():
    assert normalize_account_id("1910086849857231") == "act_1910086849857231"


def test_normalize_account_id_keeps_prefix():
    assert normalize_account_id("act_1910086849857231") == "act_1910086849857231"


def test_normalize_account_id_strips_whitespace():
    assert normalize_account_id("  act_123 ") == "act_123"


class FakeTable:
    def __init__(self, store, name):
        self.store, self.name, self._filters, self._payload = store, name, {}, None
        self._op = None

    def select(self, *a): self._op = "select"; return self
    def eq(self, k, v): self._filters[k] = v; return self
    def limit(self, n): return self
    def maybe_single(self): return self

    def insert(self, payload):
        self._op, self._payload = "insert", payload; return self

    def update(self, payload):
        self._op, self._payload = "update", payload; return self

    def execute(self):
        rows = self.store.setdefault(self.name, [])
        if self._op == "select":
            match = [r for r in rows if all(r.get(k) == v for k, v in self._filters.items())]
            class R: data = match[0] if match else None
            return R()
        if self._op == "insert":
            row = dict(self._payload); row.setdefault("id", f"cr-{len(rows)+1}")
            rows.append(row)
            class R: data = [row]
            return R()
        if self._op == "update":
            for r in rows:
                if all(r.get(k) == v for k, v in self._filters.items()):
                    r.update(self._payload)
            class R: data = []
            return R()
        class R: data = []
        return R()


class FakeDB:
    def __init__(self): self.store = {}
    def table(self, name): return FakeTable(self.store, name)


def test_upsert_creative_inserts_then_reuses(monkeypatch):
    import app.services.meta_ads_insights_sync as mod
    monkeypatch.setattr(mod, "get_or_create_campaign", lambda **k: {"id": "camp-1"})
    db = FakeDB()
    row = {
        "ad_id": "23857950447780795", "ad_name": "Clarity",
        "adset_id": "as1", "adset_name": "Astro Video",
        "campaign_id": "c1", "campaign_name": "Astro Video",
    }
    first = upsert_creative_from_insight(db, "t1", row)
    second = upsert_creative_from_insight(db, "t1", row)
    assert first == second
    assert len(db.store["ad_creatives"]) == 1
    assert db.store["ad_creatives"][0]["creative_label"] == "Clarity"
    assert db.store["ad_creatives"][0]["campaign_id"] == "camp-1"


def test_upsert_creative_does_not_overwrite_edited_label(monkeypatch):
    import app.services.meta_ads_insights_sync as mod
    monkeypatch.setattr(mod, "get_or_create_campaign", lambda **k: {"id": "camp-1"})
    db = FakeDB()
    db.store["ad_creatives"] = [{
        "id": "cr-1", "tenant_id": "t1", "meta_ad_id": "A1",
        "creative_label": "My Renamed", "label_edited": True,
    }]
    upsert_creative_from_insight(db, "t1", {
        "ad_id": "A1", "ad_name": "Original Meta Name",
        "adset_id": "as1", "adset_name": "Set", "campaign_id": "c1", "campaign_name": "Camp",
    })
    assert db.store["ad_creatives"][0]["creative_label"] == "My Renamed"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_meta_ads_insights_sync.py -v`
Expected: FAIL with `ModuleNotFoundError: app.services.meta_ads_insights_sync`.

- [ ] **Step 3: Write the sync service**

Create `backend/app/services/meta_ads_insights_sync.py`:

```python
"""Pull Meta Ads Insights (level=ad) per tenant, auto-import creatives, and
store daily clicks/spend. Credentials come from app_settings
(meta_ads_access_token / meta_ads_account_id, plaintext). Read-only against
Meta (ads_read). Service-role DB writes bypass RLS.
"""
import logging
from datetime import datetime, timezone

import httpx

from app.db.supabase import get_supabase
from app.services.growth import get_or_create_campaign

logger = logging.getLogger(__name__)

_GRAPH_BASE = "https://graph.facebook.com/v21.0"
_INSIGHT_FIELDS = (
    "ad_id,ad_name,adset_id,adset_name,campaign_id,campaign_name,"
    "inline_link_clicks,clicks,spend"
)


def normalize_account_id(raw: str) -> str:
    """Return the ad account id in act_<digits> form."""
    v = (raw or "").strip()
    return v if v.startswith("act_") else f"act_{v}"


def _get_ads_credentials(db, tenant_id: str) -> tuple[str, str] | None:
    """(access_token, act_account_id) from app_settings, or None if unset."""
    rows = (
        db.table("app_settings").select("key,value")
        .eq("tenant_id", tenant_id)
        .in_("key", ["meta_ads_access_token", "meta_ads_account_id"])
        .execute()
    )
    kv = {r["key"]: r["value"] for r in (rows.data or []) if r.get("value")}
    token = kv.get("meta_ads_access_token")
    account = kv.get("meta_ads_account_id")
    if not token or not account:
        return None
    return token, normalize_account_id(account)


def upsert_creative_from_insight(db, tenant_id: str, row: dict) -> str | None:
    """Insert-or-reuse an ad_creatives row keyed by (tenant_id, meta_ad_id).
    Links to an ad_campaigns row via get_or_create_campaign. Never overwrites a
    tenant-edited creative_label (label_edited=True). Returns ad_creatives.id.
    """
    ad_id = (row.get("ad_id") or "").strip()
    if not ad_id:
        return None

    campaign = get_or_create_campaign(
        db=db,
        tenant_id=tenant_id,
        platform="whatsapp",
        campaign_name=row.get("campaign_name"),
        external_campaign_id=row.get("campaign_id"),
    )
    campaign_id = campaign["id"] if campaign else None

    existing = (
        db.table("ad_creatives").select("id,label_edited")
        .eq("tenant_id", tenant_id).eq("meta_ad_id", ad_id)
        .limit(1).execute()
    )
    found = (existing.data or [None])[0]
    now_iso = datetime.now(timezone.utc).isoformat()

    if found:
        updates = {
            "meta_adset_id": row.get("adset_id"),
            "meta_adset_name": row.get("adset_name"),
            "meta_campaign_id": row.get("campaign_id"),
            "campaign_id": campaign_id,
            "updated_at": now_iso,
        }
        if not found.get("label_edited"):
            updates["creative_label"] = (row.get("ad_name") or ad_id)
        db.table("ad_creatives").update(updates).eq("id", found["id"]).eq(
            "tenant_id", tenant_id
        ).execute()
        return found["id"]

    inserted = db.table("ad_creatives").insert({
        "tenant_id": tenant_id,
        "campaign_id": campaign_id,
        "meta_ad_id": ad_id,
        "meta_adset_id": row.get("adset_id"),
        "meta_adset_name": row.get("adset_name"),
        "meta_campaign_id": row.get("campaign_id"),
        "creative_label": (row.get("ad_name") or ad_id),
        "created_at": now_iso,
        "updated_at": now_iso,
    }).execute()
    return (inserted.data or [{}])[0].get("id")


def _fetch_insights(token: str, account: str, date_preset: str) -> list[dict]:
    """One page is enough for typical accounts; follow paging.next if present."""
    url = f"{_GRAPH_BASE}/{account}/insights"
    params = {
        "level": "ad",
        "fields": _INSIGHT_FIELDS,
        "date_preset": date_preset,
        "time_increment": "1",   # one row per ad PER DAY
        "limit": "200",
        "access_token": token,
    }
    out: list[dict] = []
    with httpx.Client(timeout=30) as client:
        next_url, next_params = url, params
        for _ in range(20):  # hard cap on pages
            resp = client.get(next_url, params=next_params)
            resp.raise_for_status()
            body = resp.json()
            out.extend(body.get("data", []))
            nxt = (body.get("paging") or {}).get("next")
            if not nxt:
                break
            next_url, next_params = nxt, None  # next already carries all params
    return out


def sync_tenant_ad_insights(db, tenant_id: str, *, date_preset: str = "last_30d") -> int:
    """Pull level=ad daily insights, upsert creatives, write ad_insights_daily.
    Returns number of daily rows written. Best-effort per row.
    """
    creds = _get_ads_credentials(db, tenant_id)
    if not creds:
        return 0
    token, account = creds
    try:
        rows = _fetch_insights(token, account, date_preset)
    except Exception as e:
        logger.warning(f"Ads insights fetch failed for tenant {tenant_id}: {e}")
        return 0

    written = 0
    for row in rows:
        creative_id = upsert_creative_from_insight(db, tenant_id, row)
        if not creative_id:
            continue
        insight_date = row.get("date_start")  # present when time_increment=1
        if not insight_date:
            continue
        try:
            db.table("ad_insights_daily").upsert({
                "tenant_id": tenant_id,
                "ad_creative_id": creative_id,
                "insight_date": insight_date,
                "clicks": int(float(row.get("clicks", 0) or 0)),
                "inline_link_clicks": int(float(row.get("inline_link_clicks", 0) or 0)),
                "spend": float(row.get("spend", 0) or 0),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }, on_conflict="tenant_id,ad_creative_id,insight_date").execute()
            written += 1
        except Exception as e:
            logger.warning(f"insight row write failed (tenant {tenant_id}): {e}")
    logger.info(f"Ads insights sync: tenant {tenant_id} wrote {written} daily rows")
    return written


def sync_all_tenants_ad_insights() -> None:
    """Scheduler entrypoint: sync every tenant that has ads credentials set."""
    db = get_supabase()
    try:
        rows = (
            db.table("app_settings").select("tenant_id")
            .eq("key", "meta_ads_account_id").execute()
        )
        tenant_ids = sorted({r["tenant_id"] for r in (rows.data or []) if r.get("tenant_id")})
    except Exception as e:
        logger.error(f"Ads insights sync: tenant enumeration failed: {e}")
        return
    for tid in tenant_ids:
        try:
            sync_tenant_ad_insights(db, tid)
        except Exception as e:
            logger.warning(f"Ads insights sync failed for tenant {tid}: {e}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_meta_ads_insights_sync.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/meta_ads_insights_sync.py backend/tests/test_meta_ads_insights_sync.py
git commit -m "feat: Meta Ads Insights sync service + creative auto-import"
```

---

## Task 3: Register the sync scheduler job

**Files:**
- Modify: `backend/app/main.py` (the `lifespan` job-registration block, near line 387)

**Interfaces:**
- Consumes: `sync_all_tenants_ad_insights` (Task 2).

- [ ] **Step 1: Add a module-level wrapper near the other scheduler wrappers**

In `backend/app/main.py`, alongside the other `_...` scheduler wrapper functions (the ones referenced by `add_job`, e.g. `_sync_all_number_quality`), add:

```python
async def _sync_ad_insights() -> None:
    try:
        import asyncio
        from app.services.meta_ads_insights_sync import sync_all_tenants_ad_insights
        await asyncio.to_thread(sync_all_tenants_ad_insights)
    except Exception as e:
        logger.error(f"Ad insights scheduler error: {e}")
```

- [ ] **Step 2: Register the job in `lifespan`**

In `backend/app/main.py`, next to the other `_scheduler.add_job(...)` calls (after `number-quality-sync`, around line 386), add:

```python
    _scheduler.add_job(
        _sync_ad_insights,
        trigger="interval",
        hours=6,
        id="ad-insights-sync",
        replace_existing=True,
    )
```

- [ ] **Step 3: Verify the app imports and the job is registered**

Run: `cd backend && python -c "import app.main"`
Expected: no import error.

Run: `cd backend && python -c "from app.services.meta_ads_insights_sync import sync_all_tenants_ad_insights; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 4: Commit**

```bash
git add backend/app/main.py
git commit -m "feat: schedule ad insights sync every 6h"
```

---

## Task 4: Stamp attributed_ad_creative_id on the webhook

**Files:**
- Modify: `backend/app/routes/webhook.py:437-459` (the CTWA referral block)

**Interfaces:**
- Consumes: `ad_creatives` (Task 1). Uses `ad_id` already available as `referral.source_id`.

- [ ] **Step 1: Extend the CTWA block to match a creative and stamp the lead**

In `backend/app/routes/webhook.py`, inside the `if campaign:` branch of the CTWA block (immediately after the existing `db.table("leads").update({"ad_campaign_id": campaign["id"]})...execute()` at line 455), add a creative match. The full branch becomes:

```python
                                if campaign:
                                    db.table("leads").update({"ad_campaign_id": campaign["id"]}).eq("id", lead_id).eq("tenant_id", tenant_id).execute()
                                    ad_attributed = True
                                    logger.info(f"CTWA referral: lead {lead_id} linked to ad campaign {campaign['id']} (ad_id={ad_id})")

                                    # Per-creative attribution: match the referral ad_id to an
                                    # auto-imported ad_creatives row. Only set when currently
                                    # NULL so a repeat contact never re-attributes the lead.
                                    try:
                                        creative = (
                                            db.table("ad_creatives").select("id")
                                            .eq("tenant_id", tenant_id).eq("meta_ad_id", ad_id)
                                            .limit(1).execute()
                                        )
                                        creative_row = (creative.data or [None])[0]
                                        if creative_row:
                                            current = (
                                                db.table("leads").select("attributed_ad_creative_id")
                                                .eq("id", lead_id).eq("tenant_id", tenant_id)
                                                .limit(1).execute()
                                            )
                                            if current.data and not current.data[0].get("attributed_ad_creative_id"):
                                                db.table("leads").update(
                                                    {"attributed_ad_creative_id": creative_row["id"]}
                                                ).eq("id", lead_id).eq("tenant_id", tenant_id).execute()
                                                logger.info(f"CTWA creative: lead {lead_id} -> creative {creative_row['id']} (ad_id={ad_id})")
                                    except Exception as cr_err:
                                        logger.warning(f"Creative attribution failed for lead {lead_id}: {cr_err}")
```

Note: if the creative hasn't been imported yet (ad newly launched, no insight synced), the match simply finds nothing and the lead keeps campaign-level attribution — the next sync + a later message would still be unattributed at creative level. Accepted per spec (creatives appear after first insight sync).

- [ ] **Step 2: Verify the module imports**

Run: `cd backend && python -c "import app.routes.webhook"`
Expected: no import error.

- [ ] **Step 3: Commit**

```bash
git add backend/app/routes/webhook.py
git commit -m "feat: stamp attributed_ad_creative_id from CTWA referral"
```

---

## Task 5: Cost metrics + per-creative aggregation

**Files:**
- Create: `backend/app/services/ad_performance.py`
- Test: `backend/tests/test_ad_performance.py`

**Interfaces:**
- Consumes: `ad_creatives`, `ad_insights_daily`, `leads` (Task 1). Segment→status mapping: qualified = segment in {A,B}; hot = segment A; sale = a lead with `converted_at`/`won` — see note below.
- Produces:
  - `compute_cost_metrics(row: dict) -> dict` → adds `cpc`, `cost_per_message`, `cost_per_qualified`, `cost_per_hot`, `roas`.
  - `build_creative_performance(db, tenant_id, *, campaign_id=None, adset_id=None, ad_creative_id=None, date_from=None, date_to=None) -> list[dict]` → one dict per creative.
  - `build_ad_filter_tree(db, tenant_id) -> dict` → `{campaigns, adsets, creatives}` for cascading dropdowns.

**Status mapping note:** This codebase scores leads into segments A/B/C/D (A=Hot, B=Warm, C=Cold, D=Disqualified) — there is no separate `converted` flag on `leads` in the base schema. For this build: **Qualified** = segment in {A, B}; **Hot** = segment A. **Sales / revenue** require a conversion signal that does not yet exist as a first-class field, so Sales and ROAS are computed from `leads.converted_at` **if that column exists**, else reported as `0`/`null` and surfaced in the UI as "—". Do not invent a revenue field; leave Sales/ROAS at zero until a conversion source is wired (future work). This keeps the build honest rather than fabricating numbers.

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_ad_performance.py`:

```python
from app.services.ad_performance import compute_cost_metrics


def test_cpc_uses_inline_link_clicks():
    row = {"inline_link_clicks": 422, "messages": 38, "qualified": 22,
           "hot": 12, "spend": 3624.79, "revenue": 0}
    out = compute_cost_metrics(row)
    assert round(out["cpc"], 2) == 8.59


def test_cost_per_message_and_hot():
    row = {"inline_link_clicks": 65, "messages": 9, "qualified": 5,
           "hot": 2, "spend": 421.13, "revenue": 0}
    out = compute_cost_metrics(row)
    assert round(out["cost_per_message"], 2) == 46.79
    assert round(out["cost_per_hot"], 2) == 210.57


def test_zero_denominators_do_not_crash():
    row = {"inline_link_clicks": 0, "messages": 0, "qualified": 0,
           "hot": 0, "spend": 0, "revenue": 0}
    out = compute_cost_metrics(row)
    assert out["cpc"] is None
    assert out["cost_per_message"] is None
    assert out["roas"] is None


def test_roas_when_revenue_present():
    row = {"inline_link_clicks": 422, "messages": 38, "qualified": 22,
           "hot": 12, "spend": 4000, "revenue": 10000}
    out = compute_cost_metrics(row)
    assert out["roas"] == 2.5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_ad_performance.py -v`
Expected: FAIL with `ModuleNotFoundError: app.services.ad_performance`.

- [ ] **Step 3: Write the service**

Create `backend/app/services/ad_performance.py`:

```python
"""Per-creative ad performance: join ad_creatives x ad_insights_daily x leads,
compute funnel counts and cost metrics. Pure aggregation; no external calls.
"""
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _safe_div(numer: float, denom: float):
    if not denom:
        return None
    return numer / denom


def compute_cost_metrics(row: dict) -> dict:
    """Add cpc / cost_per_message / cost_per_qualified / cost_per_hot / roas.
    All guard against divide-by-zero (return None). Mutates and returns row.
    CPC uses inline_link_clicks to match the 'Clicks' column shown in the UI.
    """
    spend = float(row.get("spend", 0) or 0)
    clicks = float(row.get("inline_link_clicks", 0) or 0)
    messages = float(row.get("messages", 0) or 0)
    qualified = float(row.get("qualified", 0) or 0)
    hot = float(row.get("hot", 0) or 0)
    revenue = float(row.get("revenue", 0) or 0)

    row["cpc"] = _safe_div(spend, clicks)
    row["cost_per_message"] = _safe_div(spend, messages)
    row["cost_per_qualified"] = _safe_div(spend, qualified)
    row["cost_per_hot"] = _safe_div(spend, hot)
    row["roas"] = _safe_div(revenue, spend)
    return row


def _lead_has_converted_column(db, tenant_id: str) -> bool:
    """Detect whether leads.converted_at exists; if a select on it errors we
    treat sales/revenue as unavailable (0). Cached per process is unnecessary."""
    try:
        db.table("leads").select("converted_at").eq("tenant_id", tenant_id).limit(1).execute()
        return True
    except Exception:
        return False


def build_creative_performance(
    db,
    tenant_id: str,
    *,
    campaign_id: str | None = None,
    adset_id: str | None = None,
    ad_creative_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict]:
    """One row per creative with volume/quality/money metrics.

    Filters:
      campaign_id     -> ad_creatives.campaign_id (Aira ad_campaigns FK)
      adset_id        -> ad_creatives.meta_adset_id
      ad_creative_id  -> ad_creatives.id
      date_from/to    -> bound both ad_insights_daily.insight_date and leads.created_at
    """
    q = db.table("ad_creatives").select(
        "id,creative_label,meta_ad_id,meta_adset_id,meta_adset_name,campaign_id"
    ).eq("tenant_id", tenant_id)
    if campaign_id:
        q = q.eq("campaign_id", campaign_id)
    if adset_id:
        q = q.eq("meta_adset_id", adset_id)
    if ad_creative_id:
        q = q.eq("id", ad_creative_id)
    creatives = (q.execute().data) or []
    if not creatives:
        return []
    creative_ids = [c["id"] for c in creatives]

    # Insights (summed over the date range) per creative.
    ins_q = db.table("ad_insights_daily").select(
        "ad_creative_id,inline_link_clicks,clicks,spend,insight_date"
    ).eq("tenant_id", tenant_id).in_("ad_creative_id", creative_ids)
    if date_from:
        ins_q = ins_q.gte("insight_date", date_from)
    if date_to:
        ins_q = ins_q.lte("insight_date", date_to)
    insights = (ins_q.execute().data) or []

    ins_by_creative: dict[str, dict] = {}
    for r in insights:
        acc = ins_by_creative.setdefault(
            r["ad_creative_id"], {"inline_link_clicks": 0, "clicks": 0, "spend": 0.0}
        )
        acc["inline_link_clicks"] += int(r.get("inline_link_clicks", 0) or 0)
        acc["clicks"] += int(r.get("clicks", 0) or 0)
        acc["spend"] += float(r.get("spend", 0) or 0)

    # Leads attributed to these creatives (funnel counts).
    has_converted = _lead_has_converted_column(db, tenant_id)
    lead_cols = "id,segment,attributed_ad_creative_id,created_at" + (
        ",converted_at" if has_converted else ""
    )
    lead_q = db.table("leads").select(lead_cols).eq("tenant_id", tenant_id).in_(
        "attributed_ad_creative_id", creative_ids
    ).is_("deleted_at", "null")
    if date_from:
        lead_q = lead_q.gte("created_at", date_from)
    if date_to:
        lead_q = lead_q.lte("created_at", date_to + "T23:59:59")
    leads = (lead_q.execute().data) or []

    funnel: dict[str, dict] = {}
    for lead in leads:
        cid = lead.get("attributed_ad_creative_id")
        if not cid:
            continue
        f = funnel.setdefault(cid, {"messages": 0, "qualified": 0, "hot": 0, "sales": 0})
        f["messages"] += 1
        seg = lead.get("segment")
        if seg in ("A", "B"):
            f["qualified"] += 1
        if seg == "A":
            f["hot"] += 1
        if has_converted and lead.get("converted_at"):
            f["sales"] += 1

    out: list[dict] = []
    for c in creatives:
        ins = ins_by_creative.get(c["id"], {"inline_link_clicks": 0, "clicks": 0, "spend": 0.0})
        fn = funnel.get(c["id"], {"messages": 0, "qualified": 0, "hot": 0, "sales": 0})
        clicks = ins["inline_link_clicks"]
        messages = fn["messages"]
        row = {
            "ad_creative_id": c["id"],
            "creative_label": c["creative_label"],
            "meta_ad_id": c["meta_ad_id"],
            "adset_id": c.get("meta_adset_id"),
            "adset_name": c.get("meta_adset_name"),
            "campaign_id": c.get("campaign_id"),
            "inline_link_clicks": clicks,
            "messages": messages,
            "clicked_no_message": max(clicks - messages, 0),
            "qualified": fn["qualified"],
            "hot": fn["hot"],
            "sales": fn["sales"],
            "spend": round(ins["spend"], 2),
            "revenue": 0,  # no revenue source yet; see plan status-mapping note
        }
        compute_cost_metrics(row)
        out.append(row)

    out.sort(key=lambda r: r["inline_link_clicks"], reverse=True)
    return out


def build_ad_filter_tree(db, tenant_id: str) -> dict:
    """Campaign -> adset -> creative option tree for cascading dropdowns."""
    creatives = (
        db.table("ad_creatives").select(
            "id,creative_label,meta_adset_id,meta_adset_name,campaign_id"
        ).eq("tenant_id", tenant_id).execute().data
    ) or []

    campaign_ids = sorted({c["campaign_id"] for c in creatives if c.get("campaign_id")})
    camp_names: dict[str, str] = {}
    if campaign_ids:
        camps = (
            db.table("ad_campaigns").select("id,campaign_name")
            .eq("tenant_id", tenant_id).in_("id", campaign_ids).execute().data
        ) or []
        camp_names = {c["id"]: c["campaign_name"] for c in camps}

    return {
        "campaigns": [{"id": cid, "name": camp_names.get(cid, "—")} for cid in campaign_ids],
        "adsets": [
            {"id": aid, "name": name, "campaign_id": campc}
            for aid, name, campc in sorted({
                (c["meta_adset_id"], c.get("meta_adset_name") or "—", c.get("campaign_id"))
                for c in creatives if c.get("meta_adset_id")
            })
        ],
        "creatives": [
            {"id": c["id"], "name": c["creative_label"],
             "adset_id": c.get("meta_adset_id"), "campaign_id": c.get("campaign_id")}
            for c in creatives
        ],
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_ad_performance.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/ad_performance.py backend/tests/test_ad_performance.py
git commit -m "feat: per-creative performance aggregation + cost metrics"
```

---

## Task 6: Backend endpoints

**Files:**
- Modify: `backend/app/routes/inbound_leads.py`

**Interfaces:**
- Consumes: `build_creative_performance`, `build_ad_filter_tree` (Task 5); `get_tenant_id` dependency (already imported in the file); `csv`/`io`/`StreamingResponse` (already imported).
- Produces HTTP: `GET /api/v1/inbound-leads/ad-filters`, `GET /api/v1/inbound-leads/ad-performance`, `GET /api/v1/inbound-leads/ad-performance/export`.

- [ ] **Step 1: Add the three endpoints**

Append to `backend/app/routes/inbound_leads.py` (the router is `router` and tenant dep is `get_tenant_id`):

```python
@router.get("/ad-filters")
async def ad_filters(tenant_id: str = Depends(get_tenant_id)):
    """Campaign -> adset -> creative option tree for the cascading dropdowns."""
    from app.services.ad_performance import build_ad_filter_tree
    db = get_supabase()
    return build_ad_filter_tree(db, tenant_id)


@router.get("/ad-performance")
async def ad_performance(
    campaign_id: str | None = Query(None),
    adset_id: str | None = Query(None),
    ad_creative_id: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    tenant_id: str = Depends(get_tenant_id),
):
    """Per-creative performance rows for the Ad Performance tab."""
    from app.services.ad_performance import build_creative_performance
    db = get_supabase()
    rows = build_creative_performance(
        db, tenant_id,
        campaign_id=campaign_id, adset_id=adset_id, ad_creative_id=ad_creative_id,
        date_from=date_from, date_to=date_to,
    )
    return {"data": rows}


@router.get("/ad-performance/export")
async def ad_performance_export(
    campaign_id: str | None = Query(None),
    adset_id: str | None = Query(None),
    ad_creative_id: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    tenant_id: str = Depends(get_tenant_id),
):
    """CSV of the per-creative performance table, honoring the same filters."""
    from app.services.ad_performance import build_creative_performance
    db = get_supabase()
    rows = build_creative_performance(
        db, tenant_id,
        campaign_id=campaign_id, adset_id=adset_id, ad_creative_id=ad_creative_id,
        date_from=date_from, date_to=date_to,
    )
    fieldnames = [
        "creative_label", "adset_name", "inline_link_clicks", "messages",
        "clicked_no_message", "qualified", "hot", "sales", "spend",
        "cpc", "cost_per_message", "cost_per_qualified", "cost_per_hot",
        "revenue", "roas",
    ]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        writer.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in fieldnames})
    output.seek(0)
    filename = f"ad_performance_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
```

- [ ] **Step 2: Verify the module imports and routes register**

Run: `cd backend && python -c "import app.main; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 3: Smoke-test the route shapes with a stub tenant (optional if no local DB)**

If a local backend + DB is available, run the server and:
Run: `curl -s "http://localhost:8000/api/v1/inbound-leads/ad-performance" -H "Authorization: Bearer <tenant-jwt>"`
Expected: `{"data": []}` (empty until a sync + attribution have run) — HTTP 200, not 500.

- [ ] **Step 4: Commit**

```bash
git add backend/app/routes/inbound_leads.py
git commit -m "feat: ad-performance + ad-filters + CSV export endpoints"
```

---

## Task 7: Frontend API client, hooks, and types

**Files:**
- Modify: `frontend/lib/api.ts`
- Modify: `frontend/hooks/useApi.ts`

**Interfaces:**
- Consumes: HTTP endpoints (Task 6); existing `apiFetch`, `getAuthHeaders`, `API_URL` in `api.ts`.
- Produces: `api.inboundLeads.adFilters`, `api.inboundLeads.adPerformance`, `api.inboundLeads.adPerformanceExportCsv`; types `AdPerformanceRow`, `AdFilterTree`; hooks `useAdFilters`, `useAdPerformance`.

- [ ] **Step 1: Add types near the other exported interfaces in `api.ts`**

```typescript
export interface AdPerformanceRow {
  ad_creative_id: string;
  creative_label: string;
  meta_ad_id: string;
  adset_id: string | null;
  adset_name: string | null;
  campaign_id: string | null;
  inline_link_clicks: number;
  messages: number;
  clicked_no_message: number;
  qualified: number;
  hot: number;
  sales: number;
  spend: number;
  revenue: number;
  cpc: number | null;
  cost_per_message: number | null;
  cost_per_qualified: number | null;
  cost_per_hot: number | null;
  roas: number | null;
}

export interface AdFilterTree {
  campaigns: { id: string; name: string }[];
  adsets: { id: string; name: string; campaign_id: string | null }[];
  creatives: { id: string; name: string; adset_id: string | null; campaign_id: string | null }[];
}

export interface AdPerformanceParams {
  campaign_id?: string;
  adset_id?: string;
  ad_creative_id?: string;
  date_from?: string;
  date_to?: string;
}
```

- [ ] **Step 2: Add the client methods inside the `inboundLeads: { ... }` object in `api.ts`**

Add after the existing `exportCsv` method (keep the trailing structure intact):

```typescript
    adFilters: async () => apiFetch<AdFilterTree>(`/api/v1/inbound-leads/ad-filters`),
    adPerformance: async (params?: AdPerformanceParams) => {
      const qs = new URLSearchParams();
      if (params?.campaign_id) qs.set("campaign_id", params.campaign_id);
      if (params?.adset_id) qs.set("adset_id", params.adset_id);
      if (params?.ad_creative_id) qs.set("ad_creative_id", params.ad_creative_id);
      if (params?.date_from) qs.set("date_from", params.date_from);
      if (params?.date_to) qs.set("date_to", params.date_to);
      return apiFetch<{ data: AdPerformanceRow[] }>(`/api/v1/inbound-leads/ad-performance?${qs}`);
    },
    adPerformanceExportCsv: async (params?: AdPerformanceParams) => {
      const qs = new URLSearchParams();
      if (params?.campaign_id) qs.set("campaign_id", params.campaign_id);
      if (params?.adset_id) qs.set("adset_id", params.adset_id);
      if (params?.ad_creative_id) qs.set("ad_creative_id", params.ad_creative_id);
      if (params?.date_from) qs.set("date_from", params.date_from);
      if (params?.date_to) qs.set("date_to", params.date_to);
      const headers = await getAuthHeaders();
      const res = await fetch(`${API_URL}/api/v1/inbound-leads/ad-performance/export?${qs}`, { headers });
      if (!res.ok) throw new Error("Export failed");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "ad_performance.csv";
      a.click();
      URL.revokeObjectURL(url);
    },
```

Note: match the exact download idiom already used by the existing `exportCsv` (read its tail at `api.ts:1716+`) if it differs — reuse the same blob/anchor approach for consistency.

- [ ] **Step 3: Add hooks in `useApi.ts` (after `useInboundCampaigns`)**

```typescript
export function useAdFilters(enabled = true, fallbackData?: AdFilterTree) {
  return useSWR<AdFilterTree>(
    enabled ? "inbound-leads/ad-filters" : null,
    () => api.inboundLeads.adFilters(),
    { ...defaultConfig, fallbackData },
  );
}

export function useAdPerformance(
  params: AdPerformanceParams,
  enabled = true,
  fallbackData?: { data: AdPerformanceRow[] },
) {
  const key = enabled ? `ad-performance:${JSON.stringify(params)}` : null;
  return useSWR<{ data: AdPerformanceRow[] }>(
    key,
    () => api.inboundLeads.adPerformance(params),
    { ...defaultConfig, fallbackData },
  );
}
```

Add the imports for `AdFilterTree`, `AdPerformanceRow`, `AdPerformanceParams` to the existing `import { ... } from "@/lib/api"` line in `useApi.ts`.

- [ ] **Step 4: Typecheck**

Run: `cd frontend && npm run typecheck`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/api.ts frontend/hooks/useApi.ts
git commit -m "feat: ad-performance api client + hooks"
```

---

## Task 8: Frontend — tab shell + Ad Performance tab

**Files:**
- Create: `frontend/app/dashboard/inbound-leads/AdPerformanceTab.tsx`
- Modify: `frontend/app/dashboard/inbound-leads/InboundLeadsClient.tsx`

**Interfaces:**
- Consumes: `useAdFilters`, `useAdPerformance` (Task 7); `api.inboundLeads.adPerformanceExportCsv`.

- [ ] **Step 1: Create the Ad Performance tab component**

Create `frontend/app/dashboard/inbound-leads/AdPerformanceTab.tsx`:

```tsx
"use client";
import { useMemo, useState } from "react";
import { api, AdPerformanceRow } from "@/lib/api";
import { useAdFilters, useAdPerformance } from "@/hooks/useApi";
import { Download, RefreshCw, ChevronDown, Megaphone } from "lucide-react";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

function money(n: number | null | undefined) {
  if (n == null) return "—";
  return "₹" + Math.round(n).toLocaleString("en-IN");
}
function ratio(n: number | null | undefined) {
  if (n == null) return "—";
  return `${n.toFixed(2)}×`;
}

export function AdPerformanceTab() {
  const [campaignId, setCampaignId] = useState("");
  const [adsetId, setAdsetId] = useState("");
  const [creativeId, setCreativeId] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [exporting, setExporting] = useState(false);

  const { data: filters } = useAdFilters();
  const params = {
    campaign_id: campaignId || undefined,
    adset_id: adsetId || undefined,
    ad_creative_id: creativeId || undefined,
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
  };
  const { data, isValidating, mutate } = useAdPerformance(params);
  const rows: AdPerformanceRow[] = data?.data ?? [];

  // Cascading option lists
  const adsetOptions = useMemo(
    () => (filters?.adsets ?? []).filter((a) => !campaignId || a.campaign_id === campaignId),
    [filters, campaignId],
  );
  const creativeOptions = useMemo(
    () => (filters?.creatives ?? []).filter(
      (c) => (!campaignId || c.campaign_id === campaignId) && (!adsetId || c.adset_id === adsetId),
    ),
    [filters, campaignId, adsetId],
  );

  const totals = useMemo(() => {
    const t = { clicks: 0, messages: 0, noMsg: 0, spend: 0, revenue: 0 };
    for (const r of rows) {
      t.clicks += r.inline_link_clicks;
      t.messages += r.messages;
      t.noMsg += r.clicked_no_message;
      t.spend += r.spend;
      t.revenue += r.revenue;
    }
    return t;
  }, [rows]);

  async function handleExport() {
    setExporting(true);
    try {
      await api.inboundLeads.adPerformanceExportCsv(params);
      toast.success("Downloaded: ad_performance.csv");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Export failed");
    } finally {
      setExporting(false);
    }
  }

  const selectCls =
    "h-9 w-full cursor-pointer appearance-none rounded-xl border border-surface-mid bg-white px-3 pr-8 font-body text-xs font-semibold text-on-surface shadow-[inset_0_1px_0_rgba(255,255,255,0.8)] transition-colors hover:border-violet-200 focus:outline-none focus:ring-2 focus:ring-violet-200 disabled:opacity-40 disabled:cursor-not-allowed";

  return (
    <div>
      {/* Filters */}
      <div className="mb-4 flex flex-wrap items-end gap-2.5">
        <div className="min-w-[180px] flex-1">
          <label className="mb-1 block font-label text-[9px] font-bold uppercase tracking-wider text-on-surface-muted">Campaign</label>
          <div className="relative">
            <select className={selectCls} value={campaignId}
              onChange={(e) => { setCampaignId(e.target.value); setAdsetId(""); setCreativeId(""); }}>
              <option value="">All Campaigns</option>
              {(filters?.campaigns ?? []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
            <ChevronDown size={13} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[#a8a29e] pointer-events-none" />
          </div>
        </div>
        <div className="min-w-[180px] flex-1">
          <label className="mb-1 block font-label text-[9px] font-bold uppercase tracking-wider text-on-surface-muted">Ad Set</label>
          <div className="relative">
            <select className={selectCls} value={adsetId}
              onChange={(e) => { setAdsetId(e.target.value); setCreativeId(""); }}>
              <option value="">All Ad Sets</option>
              {adsetOptions.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
            <ChevronDown size={13} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[#a8a29e] pointer-events-none" />
          </div>
        </div>
        <div className="min-w-[180px] flex-1">
          <label className="mb-1 block font-label text-[9px] font-bold uppercase tracking-wider text-on-surface-muted">Creative</label>
          <div className="relative">
            <select className={selectCls} value={creativeId} onChange={(e) => setCreativeId(e.target.value)}>
              <option value="">All Creatives</option>
              {creativeOptions.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
            <ChevronDown size={13} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[#a8a29e] pointer-events-none" />
          </div>
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
        <div className="flex gap-2">
          <button onClick={() => mutate()} disabled={isValidating}
            className="flex items-center justify-center gap-2 px-3 py-2 rounded-xl bg-white border border-[#e8e3db] hover:bg-[#f0ece4] text-[#1c1917] font-label text-xs font-bold transition-all disabled:opacity-40 shadow-sm">
            <RefreshCw size={12} className={isValidating ? "animate-spin" : ""} /> Refresh
          </button>
          <button onClick={handleExport} disabled={exporting || rows.length === 0}
            className="flex items-center justify-center gap-2 px-3 py-2 bg-primary text-white rounded-xl font-label text-xs font-bold hover:bg-primary/90 transition-all disabled:opacity-40 shadow-sm">
            <Download size={12} /> {exporting ? "Downloading…" : "Download CSV"}
          </button>
        </div>
      </div>

      {/* Table */}
      <div className="card rounded-2xl overflow-hidden">
        {rows.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-center px-4">
            <div className="w-14 h-14 rounded-2xl bg-violet-50 flex items-center justify-center mb-3">
              <Megaphone size={24} className="text-violet-400" />
            </div>
            <h3 className="font-bold text-[#44403c] text-base mb-1">No creative data yet</h3>
            <p className="text-sm text-[#a8a29e] max-w-sm leading-relaxed">
              Once your Meta ads start delivering and the daily sync runs, each ad appears here
              with its clicks, messages and cost breakdown.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[900px]">
              <thead>
                <tr className="border-b border-surface-mid bg-surface-low/60">
                  {["Creative", "Ad Set", "Clicks", "Messages", "No message", "Qualified", "Hot", "Sales",
                    "Spend", "CPC", "Cost / msg", "Cost / qual", "Cost / hot", "Revenue", "ROAS"].map((h, i) => (
                    <th key={h} className={cn(
                      "px-4 py-3 font-label text-[10px] font-bold text-on-surface-muted uppercase tracking-wider whitespace-nowrap",
                      i <= 1 ? "text-left" : "text-right",
                    )}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-mid/50">
                {rows.map((r) => (
                  <tr key={r.ad_creative_id} className="hover:bg-surface-low/60 transition-colors">
                    <td className="px-4 py-3">
                      <span className="font-label text-sm font-semibold text-on-surface">{r.creative_label}</span>
                    </td>
                    <td className="px-4 py-3 text-xs text-on-surface-muted">{r.adset_name ?? "—"}</td>
                    <td className="px-4 py-3 text-right tabular-nums font-semibold text-violet-700">{r.inline_link_clicks.toLocaleString("en-IN")}</td>
                    <td className="px-4 py-3 text-right tabular-nums font-bold text-on-surface">{r.messages.toLocaleString("en-IN")}</td>
                    <td className="px-4 py-3 text-right tabular-nums text-on-surface-muted">{r.clicked_no_message.toLocaleString("en-IN")}</td>
                    <td className="px-4 py-3 text-right tabular-nums text-on-surface-muted">{r.qualified}</td>
                    <td className="px-4 py-3 text-right tabular-nums text-on-surface-muted">{r.hot}</td>
                    <td className="px-4 py-3 text-right tabular-nums font-semibold text-on-surface">{r.sales}</td>
                    <td className="px-4 py-3 text-right tabular-nums">{money(r.spend)}</td>
                    <td className="px-4 py-3 text-right tabular-nums">{money(r.cpc)}</td>
                    <td className="px-4 py-3 text-right tabular-nums">{money(r.cost_per_message)}</td>
                    <td className="px-4 py-3 text-right tabular-nums">{money(r.cost_per_qualified)}</td>
                    <td className="px-4 py-3 text-right tabular-nums">{money(r.cost_per_hot)}</td>
                    <td className="px-4 py-3 text-right tabular-nums">{money(r.revenue)}</td>
                    <td className="px-4 py-3 text-right tabular-nums font-bold text-emerald-700">{ratio(r.roas)}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="border-t-2 border-surface-mid bg-surface-low/50 font-bold">
                  <td className="px-4 py-3 text-sm">Total</td>
                  <td className="px-4 py-3"></td>
                  <td className="px-4 py-3 text-right tabular-nums">{totals.clicks.toLocaleString("en-IN")}</td>
                  <td className="px-4 py-3 text-right tabular-nums">{totals.messages.toLocaleString("en-IN")}</td>
                  <td className="px-4 py-3 text-right tabular-nums">{totals.noMsg.toLocaleString("en-IN")}</td>
                  <td className="px-4 py-3" colSpan={3}></td>
                  <td className="px-4 py-3 text-right tabular-nums">{money(totals.spend)}</td>
                  <td className="px-4 py-3" colSpan={4}></td>
                  <td className="px-4 py-3 text-right tabular-nums">{money(totals.revenue)}</td>
                  <td className="px-4 py-3 text-right tabular-nums">
                    {totals.spend ? ratio(totals.revenue / totals.spend) : "—"}
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Add the tab switch to `InboundLeadsClient.tsx`**

At the top of the `InboundLeadsClient` component body (inside the function, before the existing `return (`), add tab state and import:

Add to the imports block:
```tsx
import { AdPerformanceTab } from "./AdPerformanceTab";
```

Add state near the other `useState` calls (around line 272):
```tsx
  const [tab, setTab] = useState<"leads" | "performance">("leads");
```

Replace the opening `return (` / `<div>` at line 360-361 with a tab bar, and gate the existing content behind the "leads" tab. Concretely, change:

```tsx
  return (
    <div>
```

to:

```tsx
  return (
    <div>
      {/* Tab switch */}
      <div className="mb-5 inline-flex gap-1 rounded-2xl border border-surface-mid bg-surface-mid/40 p-1">
        <button
          onClick={() => setTab("leads")}
          className={cn(
            "px-4 py-1.5 rounded-xl font-label text-[13px] font-bold transition-all",
            tab === "leads" ? "bg-white text-violet-700 shadow-sm" : "text-on-surface-muted hover:text-on-surface",
          )}
        >
          Leads
        </button>
        <button
          onClick={() => setTab("performance")}
          className={cn(
            "px-4 py-1.5 rounded-xl font-label text-[13px] font-bold transition-all",
            tab === "performance" ? "bg-white text-violet-700 shadow-sm" : "text-on-surface-muted hover:text-on-surface",
          )}
        >
          Ad Performance
        </button>
      </div>

      {tab === "performance" ? (
        <AdPerformanceTab />
      ) : (
      <>
```

Then find the matching close of the outer `<div>` at the very end of the component (the `</div>` immediately before the final `);` at line 704) and insert `</>` and `)` before it so the "leads" branch closes. The final lines become:

```tsx
        )}
      </div>
      </>
      )}
    </div>
  );
}
```

Important: verify brace/tag balance after this edit — the existing leads content (filter panel, stats, table) must all render only in the `leads` branch. Use `npm run typecheck` (next step) to catch any imbalance.

- [ ] **Step 3: Typecheck and lint**

Run: `cd frontend && npm run typecheck`
Expected: no errors.

Run: `cd frontend && npm run lint`
Expected: no errors (no unused imports, no `any`).

- [ ] **Step 4: Build**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/dashboard/inbound-leads/AdPerformanceTab.tsx frontend/app/dashboard/inbound-leads/InboundLeadsClient.tsx
git commit -m "feat: Ad Performance tab in Inbound Leads"
```

---

## Task 9: Settings field for Meta Ads credentials

**Files:**
- Modify: the WhatsApp/Meta settings UI where `meta_access_token` is entered, and its allow-list on the backend.

**Interfaces:**
- Consumes: existing `app_settings` upsert path in `backend/app/routes/app_settings.py`.

**Note:** The sync job reads `meta_ads_access_token` / `meta_ads_account_id` from `app_settings`. Tenants must be able to save them. The base schema stores arbitrary keys, but `app_settings.py` may **allow-list** which keys are writable (see the `wa_keys` set at `app_settings.py:239` and the secret-flag logic at `:605`). This task makes the two new keys writable + marks the token secret.

- [ ] **Step 1: Allow-list the two new keys**

In `backend/app/routes/app_settings.py`, find where writable keys are validated/collected (the settings-save handler that upserts to `app_settings`, near the `wa_keys` set at line 239 and the secret classification at line 605). Add `meta_ads_access_token` and `meta_ads_account_id` to the writable set, and include `meta_ads_access_token` in the secret set so it is stored with `is_secret=true` (mirror the existing `key in {"meta_access_token", "meta_app_secret"}` check at line 605):

```python
    # writable Meta ads keys (read by services/meta_ads_insights_sync.py)
    # add to whichever set/list gates allowed keys in this handler:
    #   "meta_ads_access_token", "meta_ads_account_id"
    # and treat meta_ads_access_token as secret:
    #   is_secret = key in {"meta_access_token", "meta_app_secret", "meta_ads_access_token"}
```

Apply those two concrete edits to the actual allow-list/secret expressions in this file (exact set literals depend on the current code — read lines 205-265 and 595-610 and extend them).

- [ ] **Step 2: Add the input fields to the settings UI**

In the frontend settings page that renders the Meta/WhatsApp token inputs (the same screen with `meta_access_token`), add two text inputs bound to `meta_ads_access_token` (type=password) and `meta_ads_account_id` (placeholder `act_1910086849857231` or just the digits), saved through the same settings-save call the other Meta fields use. Reuse the existing input styling on that page — no new button styles.

- [ ] **Step 3: Verify**

Run: `cd backend && python -c "import app.routes.app_settings; print('ok')"`
Expected: `ok`.

Run: `cd frontend && npm run typecheck`
Expected: no errors.

- [ ] **Step 4: Manual end-to-end check**

1. In the app settings, paste the tenant's `meta_ads_access_token` (System User token with `ads_read`) and `meta_ads_account_id`.
2. Trigger a sync once (either wait for the 6h job, or temporarily call `sync_all_tenants_ad_insights()` from a Python shell: `cd backend && python -c "from app.services.meta_ads_insights_sync import sync_all_tenants_ad_insights as s; s()"`).
3. Open Inbound Leads → Ad Performance. Expect creatives (e.g. "Clarity", "Baby", "Office") to appear with real click/spend numbers.
4. Confirm the campaign→adset→creative dropdowns cascade, and Download CSV produces a file.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routes/app_settings.py frontend
git commit -m "feat: Meta Ads credential settings fields"
```

---

## Self-Review

**Spec coverage:**
- Ad setup unchanged / native CTWA → no code change needed (documented). ✓
- `ad_creatives`, `ad_insights_daily`, `leads.attributed_ad_creative_id` → Task 1. ✓
- Per-tenant `meta_ads_access_token` / `meta_ads_account_id` settings-paste → Task 9. ✓
- Insights sync (`level=ad`, `inline_link_clicks`) + creative auto-import (never overwrite edited label) → Task 2. ✓
- Scheduled sync → Task 3. ✓
- Attribution via referral `ad_id` → creative, no-clobber guard → Task 4. ✓
- Derived clicked-no-message; CPC = spend ÷ inline_link_clicks → Task 5. ✓
- Campaign→adset→creative cascading filter → Tasks 5 (tree), 6 (endpoint), 8 (UI). ✓
- Ad Performance sub-tab, polished controls, CSV export → Tasks 6, 8. ✓
- Meta Conversions API explicitly out of scope → not planned. ✓

**Known honest gap (surfaced, not hidden):** Sales/Revenue/ROAS have no data source in the current schema (leads are segment-scored, no conversion/revenue field). Task 5's status-mapping note computes Qualified (seg A/B) and Hot (seg A) from real data, and leaves Sales/Revenue/ROAS at 0/— until a conversion source is wired. This is called out in the UI ("—") rather than fabricated. If a `converted_at` column exists, sales auto-populate.

**Placeholder scan:** No TBD/TODO left in code steps; Task 9 steps 1-2 describe edits against set literals whose exact current form must be read in-file (allow-list + settings UI) — these are genuinely codebase-dependent and include the exact line numbers and the exact keys to add.

**Type consistency:** `AdPerformanceRow` fields (Task 7) match the dict keys produced by `build_creative_performance` (Task 5) and the CSV `fieldnames` (Task 6). `AdFilterTree` matches `build_ad_filter_tree` output. Hook names `useAdFilters`/`useAdPerformance` used consistently in Task 8.
