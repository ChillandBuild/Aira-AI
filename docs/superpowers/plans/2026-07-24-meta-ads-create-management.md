# Meta Ads Manager — Plan 2: Create + Management — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a **Create** tab (single-scroll Click-to-WhatsApp campaign builder that publishes to Meta) plus live **status-toggle** and **budget-edit** management actions on the Ad Performance table.

**Architecture:** Builds on Plan 1 (the Meta Ads page shell, the `ad_campaigns`/`ad_creatives`/`ad_insights_daily` tables, the reporting router). Adds a new `ad_sets` table + create-columns, a **write-capable** Meta Marketing API service split into pure payload-builders (unit-tested) and thin HTTP wrappers, write endpoints on the `meta-ads` router, a Create tab, and inline management controls.

**Tech Stack:** FastAPI (`backend/app/`), Next.js 14 App Router (`frontend/app/dashboard/meta-ads/`), Supabase, httpx, SWR, Meta Marketing API v21.0.

## Global Constraints

- **`ads_management` is SUBMITTED but PENDING Meta approval.** With Standard Access the write calls work only against ad accounts Aira itself administers — so build and live-test against Aira's own **test ad account**, not a client's. Real-tenant publishing is gated on Advanced Access approval. **Nothing in the code path changes when approval lands** — only which ad accounts are authorized targets. The Create UI must therefore support a `draft_pending_approval` outcome state, not assume every tenant account is reachable.
- **Extra Meta permission:** CTWA ad creation also needs `pages_manage_ads` and a Facebook **Page id** (the ad runs as a Page). Fetch promotable pages via `GET /act_<id>/promote_pages`; store the chosen `page_id` on the campaign.
- **Budget is Campaign Budget Optimization (CBO):** `daily_budget`/`lifetime_budget` + `bid_strategy` go on the **campaign**; ad sets carry NO budget field. Bid strategy is always `LOWEST_COST_WITHOUT_CAP`.
- **Money conversion:** the UI collects INR rupees; Meta expects **minor units (paise) as integers** → multiply by 100 when building payloads (inverse of the `/100` the Plan 1 sync applies when reading).
- **Objective is locked to Click-to-WhatsApp:** campaign `objective = "OUTCOME_ENGAGEMENT"`, ad set `destination_type = "WHATSAPP"`, `optimization_goal = "CONVERSATIONS"`, `billing_event = "IMPRESSIONS"`, creative CTA `type = "WHATSAPP_MESSAGE"`, link `https://api.whatsapp.com/send`.
- **Frontend CI gate is `next lint` AND `tsc`.** Run `cd frontend && npm run lint && npm run typecheck` before every frontend commit. The lint config does NOT ignore `_`-prefixed *named* params (it does ignore `_` array-map value args) — never write `(_props: T)`.
- **Migration numbering:** next unused prefix is `149` (Plan 1 used `148`).
- **Routes are tenant-scoped** via `Depends(get_tenant_id)`, registered under the existing `meta_ads` router. Credentials come from `app_settings` (`meta_ads_access_token`, `meta_ads_account_id`) exactly as the reporting path reads them.

---

### Task 1: Schema migration 149 — ad_sets table + create-columns

**Files:**
- Create: `backend/supabase/migrations/149_meta_ads_create_columns.sql`

**Interfaces:**
- Produces: new table `ad_sets`; `ad_campaigns` columns `special_ad_category text`, `created_via text DEFAULT 'imported'`, `page_id text`; `ad_creatives` columns `created_by_aira boolean DEFAULT false`, `prefilled_greeting text`, `media_asset_ref text`, `cta_type text`.

- [ ] **Step 1: Write the migration**

```sql
-- 149: Meta Ads Create + Management (Plan 2). Adds an ad_sets table (Aira must
-- persist what it wrote to Meta at ad-set level) plus create-provenance columns
-- on ad_campaigns/ad_creatives. Columns are additive; existing admin-all +
-- tenant-read RLS on ad_campaigns/ad_creatives already covers the new columns.

CREATE TABLE public.ad_sets (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
  campaign_id uuid REFERENCES public.ad_campaigns(id) ON DELETE CASCADE,
  meta_adset_id text,
  adset_name text,
  targeting jsonb NOT NULL DEFAULT '{}'::jsonb,
  optimization_goal text,
  effective_status text,
  created_via text NOT NULL DEFAULT 'imported',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, meta_adset_id)
);

CREATE INDEX idx_ad_sets_tenant ON public.ad_sets (tenant_id);
CREATE INDEX idx_ad_sets_campaign ON public.ad_sets (campaign_id);

ALTER TABLE public.ad_campaigns
  ADD COLUMN IF NOT EXISTS special_ad_category text,
  ADD COLUMN IF NOT EXISTS created_via text NOT NULL DEFAULT 'imported',
  ADD COLUMN IF NOT EXISTS page_id text;

ALTER TABLE public.ad_creatives
  ADD COLUMN IF NOT EXISTS created_by_aira boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS prefilled_greeting text,
  ADD COLUMN IF NOT EXISTS media_asset_ref text,
  ADD COLUMN IF NOT EXISTS cta_type text;

-- RLS for the new table: admin-all + tenant-read (mirrors ad_creatives, migration 147)
ALTER TABLE public.ad_sets ENABLE ROW LEVEL SECURITY;
CREATE POLICY ad_sets_admin_all ON public.ad_sets
  USING (EXISTS (SELECT 1 FROM system_admins WHERE system_admins.user_id = auth.uid()));
CREATE POLICY ad_sets_tenant_read ON public.ad_sets
  FOR SELECT
  USING (EXISTS (SELECT 1 FROM tenant_users tu
                 WHERE tu.tenant_id = ad_sets.tenant_id AND tu.user_id = auth.uid()));
```

- [ ] **Step 2: Apply to live Supabase and verify**

Apply via the Supabase MCP `apply_migration` tool (project id `ayftynkgmfkaqmmnlmoc`, name `149_meta_ads_create_columns`, the SQL above). Verify:

```sql
SELECT to_regclass('public.ad_sets') IS NOT NULL AS ad_sets_exists;
SELECT column_name FROM information_schema.columns
WHERE table_name='ad_campaigns' AND column_name IN ('special_ad_category','created_via','page_id')
UNION ALL
SELECT column_name FROM information_schema.columns
WHERE table_name='ad_creatives' AND column_name IN ('created_by_aira','prefilled_greeting','media_asset_ref','cta_type');
```

Expected: `ad_sets_exists = true`, then 7 column rows.

- [ ] **Step 3: Commit**

```bash
git add backend/supabase/migrations/149_meta_ads_create_columns.sql
git commit -m "feat(meta-ads): migration 149 — ad_sets table + create-provenance columns"
```

---

### Task 2: Pure Marketing API payload builders (TDD core)

**Files:**
- Create: `backend/app/services/meta_ads_payloads.py`
- Test: `backend/tests/test_meta_ads_payloads.py`

**Interfaces:**
- Produces (all pure, no I/O):
  - `build_campaign_payload(name, *, daily_budget_inr=None, lifetime_budget_inr=None, special_ad_category=None) -> dict`
  - `build_adset_payload(name, campaign_id, page_id, targeting) -> dict`
  - `build_targeting(location_countries, age_min, age_max, gender) -> dict` (gender: "all"|"male"|"female" → Meta `genders` [] / [1] / [2])
  - `build_creative_payload(name, page_id, message, headline, image_hash, greeting) -> dict`
  - `build_ad_payload(name, adset_id, creative_id) -> dict`
  - Constant `WA_LINK = "https://api.whatsapp.com/send"`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_meta_ads_payloads.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.meta_ads_payloads import (
    build_campaign_payload, build_adset_payload, build_targeting,
    build_creative_payload, build_ad_payload, WA_LINK,
)


def test_campaign_payload_cbo_daily_budget_in_paise():
    p = build_campaign_payload("Diwali", daily_budget_inr=500)
    assert p["objective"] == "OUTCOME_ENGAGEMENT"
    assert p["special_ad_categories"] == []
    assert p["daily_budget"] == 50000          # 500 * 100
    assert p["bid_strategy"] == "LOWEST_COST_WITHOUT_CAP"
    assert "lifetime_budget" not in p


def test_campaign_payload_lifetime_and_special_category():
    p = build_campaign_payload("Jobs", lifetime_budget_inr=1500, special_ad_category="EMPLOYMENT")
    assert p["lifetime_budget"] == 150000
    assert p["special_ad_categories"] == ["EMPLOYMENT"]
    assert "daily_budget" not in p


def test_targeting_maps_gender_and_geo():
    t = build_targeting(["IN"], 18, 65, "female")
    assert t["geo_locations"] == {"countries": ["IN"]}
    assert t["age_min"] == 18 and t["age_max"] == 65
    assert t["genders"] == [2]
    all_t = build_targeting(["IN"], 18, 65, "all")
    assert "genders" not in all_t


def test_adset_payload_is_whatsapp_conversations_no_budget():
    t = build_targeting(["IN"], 18, 65, "all")
    p = build_adset_payload("Set 1", "c123", "page99", t)
    assert p["destination_type"] == "WHATSAPP"
    assert p["optimization_goal"] == "CONVERSATIONS"
    assert p["billing_event"] == "IMPRESSIONS"
    assert p["promoted_object"] == {"page_id": "page99"}
    assert p["campaign_id"] == "c123"
    assert "daily_budget" not in p and "lifetime_budget" not in p


def test_creative_payload_ctwa_shape():
    p = build_creative_payload("Cr1", "page99", "Come visit!", "Diwali Sale", "HASH1", "Hi, interested!")
    link = p["object_story_spec"]["link_data"]
    assert p["object_story_spec"]["page_id"] == "page99"
    assert link["link"] == WA_LINK
    assert link["message"] == "Come visit!"
    assert link["name"] == "Diwali Sale"
    assert link["image_hash"] == "HASH1"
    assert link["call_to_action"]["type"] == "WHATSAPP_MESSAGE"
    assert link["call_to_action"]["value"]["app_destination"] == "WHATSAPP"
    autofill = link["page_welcome_message"]["text_format"]["message"]["autofill_message"]["content"]
    assert autofill == "Hi, interested!"


def test_ad_payload_links_creative():
    p = build_ad_payload("Ad1", "as123", "cr456")
    assert p["adset_id"] == "as123"
    assert p["creative"] == {"creative_id": "cr456"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_meta_ads_payloads.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement the builders**

```python
# backend/app/services/meta_ads_payloads.py
"""Pure Meta Marketing API payload builders for Click-to-WhatsApp ad creation.
No I/O — every function returns a dict ready to POST. Money arrives in INR
rupees and is converted to Meta's minor units (paise) here."""

WA_LINK = "https://api.whatsapp.com/send"
_GENDER_MAP = {"male": [1], "female": [2]}  # "all" → omit the key entirely


def build_campaign_payload(name, *, daily_budget_inr=None, lifetime_budget_inr=None,
                           special_ad_category=None) -> dict:
    """Campaign-level CBO: budget + bid strategy live here, not on the ad set."""
    p = {
        "name": name,
        "objective": "OUTCOME_ENGAGEMENT",
        "special_ad_categories": [special_ad_category] if special_ad_category else [],
        "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
        "status": "ACTIVE",
    }
    if daily_budget_inr:
        p["daily_budget"] = int(round(daily_budget_inr * 100))
    if lifetime_budget_inr:
        p["lifetime_budget"] = int(round(lifetime_budget_inr * 100))
    return p


def build_targeting(location_countries, age_min, age_max, gender) -> dict:
    t = {
        "geo_locations": {"countries": list(location_countries)},
        "age_min": int(age_min),
        "age_max": int(age_max),
    }
    g = _GENDER_MAP.get((gender or "all").lower())
    if g:
        t["genders"] = g
    return t


def build_adset_payload(name, campaign_id, page_id, targeting) -> dict:
    return {
        "name": name,
        "campaign_id": campaign_id,
        "destination_type": "WHATSAPP",
        "billing_event": "IMPRESSIONS",
        "optimization_goal": "CONVERSATIONS",
        "promoted_object": {"page_id": page_id},
        "targeting": targeting,
        "status": "ACTIVE",
    }


def build_creative_payload(name, page_id, message, headline, image_hash, greeting) -> dict:
    return {
        "name": name,
        "object_story_spec": {
            "page_id": page_id,
            "link_data": {
                "name": headline,
                "message": message,
                "image_hash": image_hash,
                "link": WA_LINK,
                "call_to_action": {
                    "type": "WHATSAPP_MESSAGE",
                    "value": {"app_destination": "WHATSAPP"},
                },
                "page_welcome_message": {
                    "type": "VISUAL_EDITOR",
                    "version": 2,
                    "landing_screen_type": "welcome_message",
                    "media_type": "text",
                    "text_format": {
                        "customer_action_type": "autofill_message",
                        "message": {
                            "text": greeting,
                            "autofill_message": {"content": greeting},
                        },
                    },
                },
            },
        },
    }


def build_ad_payload(name, adset_id, creative_id) -> dict:
    return {
        "name": name,
        "adset_id": adset_id,
        "creative": {"creative_id": creative_id},
        "status": "ACTIVE",
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_meta_ads_payloads.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/meta_ads_payloads.py backend/tests/test_meta_ads_payloads.py
git commit -m "feat(meta-ads): pure Marketing API payload builders for CTWA creation"
```

---

### Task 3: Meta write client + create-orchestrator + persistence

**Files:**
- Create: `backend/app/services/meta_ads_manager.py`
- Test: `backend/tests/test_meta_ads_manager.py`

**Interfaces:**
- Consumes: payload builders (Task 2); `app_settings` creds via the existing `_get_ads_credentials` in `meta_ads_insights_sync`.
- Produces:
  - `_post(path, token, payload) -> dict` and `_get(path, token, params) -> dict` — thin httpx wrappers on `graph.facebook.com/v21.0`.
  - `upload_image(token, account, image_bytes, filename) -> str` — POST `/act_<id>/adimages`, returns `image_hash`.
  - `list_pages(token, account) -> list[dict]` — GET `/act_<id>/promote_pages`.
  - `create_full_campaign(db, tenant_id, *, spec: dict) -> dict` — orchestrates campaign→adset→creative→ad, persists rows (`created_via='aira'`), returns `{ok, campaign_id, meta_campaign_id, error}`. `spec` keys: `name, daily_budget_inr|lifetime_budget_inr, special_ad_category, location_countries, age_min, age_max, gender, page_id, message, headline, image_hash, greeting, creative_label`.
  - `set_campaign_status(db, tenant_id, campaign_id, active: bool) -> dict` — flips Meta status + local `effective_status`.
  - `update_campaign_budget(db, tenant_id, campaign_id, *, daily_budget_inr=None, lifetime_budget_inr=None) -> dict`.
  - `persist_created_campaign(db, tenant_id, meta_ids, spec) -> dict` — writes `ad_campaigns`/`ad_sets`/`ad_creatives` rows; returns the `ad_campaigns` row. (Pure-ish; tested with a FakeDB.)

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_meta_ads_manager.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.services.meta_ads_manager as mgr


class FakeTable:
    def __init__(self, store, name):
        self.store, self.name, self._payload, self._op, self._filters = store, name, None, None, {}
    def insert(self, payload): self._op, self._payload = "insert", payload; return self
    def update(self, payload): self._op, self._payload = "update", payload; return self
    def eq(self, k, v): self._filters[k] = v; return self
    def execute(self):
        rows = self.store.setdefault(self.name, [])
        if self._op == "insert":
            row = dict(self._payload); row.setdefault("id", f"{self.name}-{len(rows)+1}")
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


def test_persist_created_campaign_writes_all_three_levels():
    db = FakeDB()
    meta_ids = {"campaign_id": "mc1", "adset_id": "ma1", "ad_id": "mad1", "creative_id": "mcr1"}
    spec = {"name": "Diwali", "creative_label": "Diwali Poster", "greeting": "Hi!",
            "page_id": "p1", "daily_budget_inr": 500, "special_ad_category": None,
            "age_min": 18, "age_max": 65, "gender": "all", "location_countries": ["IN"]}
    camp = mgr.persist_created_campaign(db, "t1", meta_ids, spec)
    assert camp["created_via"] == "aira"
    assert camp["external_campaign_id"] == "mc1"
    assert len(db.store["ad_sets"]) == 1
    assert db.store["ad_sets"][0]["meta_adset_id"] == "ma1"
    cr = db.store["ad_creatives"][0]
    assert cr["created_by_aira"] is True
    assert cr["meta_ad_id"] == "mad1"
    assert cr["prefilled_greeting"] == "Hi!"


def test_create_full_campaign_orchestrates_in_order(monkeypatch):
    calls = []
    monkeypatch.setattr(mgr, "_post", lambda path, token, payload: (
        calls.append(path) or {"id": f"id-{len(calls)}"}))
    monkeypatch.setattr(mgr, "_get_ads_credentials", lambda db, t: ("tok", "act_1"))
    db = FakeDB()
    spec = {"name": "D", "creative_label": "L", "greeting": "Hi", "page_id": "p1",
            "daily_budget_inr": 500, "special_ad_category": None, "age_min": 18,
            "age_max": 65, "gender": "all", "location_countries": ["IN"],
            "message": "m", "headline": "h", "image_hash": "IMG"}
    out = mgr.create_full_campaign(db, "t1", spec=spec)
    assert out["ok"] is True
    # campaigns → adsets → adcreatives → ads, in that order
    assert calls == ["act_1/campaigns", "act_1/adsets", "act_1/adcreatives", "act_1/ads"]


def test_create_full_campaign_reports_missing_creds(monkeypatch):
    monkeypatch.setattr(mgr, "_get_ads_credentials", lambda db, t: None)
    out = mgr.create_full_campaign(FakeDB(), "t1", spec={})
    assert out["ok"] is False
    assert "credential" in out["error"].lower() or "token" in out["error"].lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_meta_ads_manager.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement the manager**

```python
# backend/app/services/meta_ads_manager.py
"""Write-capable Meta Marketing API client for Click-to-WhatsApp campaign
creation and management. Requires ads_management + pages_manage_ads. Standard
Access works against Aira's own ad account; client accounts need Advanced Access.
"""
import logging
import httpx

from app.services.meta_ads_insights_sync import _get_ads_credentials
from app.services.meta_ads_payloads import (
    build_campaign_payload, build_adset_payload, build_targeting,
    build_creative_payload, build_ad_payload,
)

logger = logging.getLogger(__name__)
_GRAPH_BASE = "https://graph.facebook.com/v21.0"


def _post(path: str, token: str, payload: dict) -> dict:
    with httpx.Client(timeout=30) as client:
        resp = client.post(f"{_GRAPH_BASE}/{path}",
                           data={**payload, "access_token": token})
        resp.raise_for_status()
        return resp.json()


def _get(path: str, token: str, params: dict) -> dict:
    with httpx.Client(timeout=30) as client:
        resp = client.get(f"{_GRAPH_BASE}/{path}", params={**params, "access_token": token})
        resp.raise_for_status()
        return resp.json()


def list_pages(token: str, account: str) -> list[dict]:
    body = _get(f"{account}/promote_pages", token, {"fields": "id,name", "limit": "100"})
    return body.get("data", [])


def upload_image(token: str, account: str, image_bytes: bytes, filename: str) -> str:
    with httpx.Client(timeout=60) as client:
        resp = client.post(f"{_GRAPH_BASE}/{account}/adimages",
                           data={"access_token": token},
                           files={"filename": (filename, image_bytes)})
        resp.raise_for_status()
        images = resp.json().get("images", {})
        first = next(iter(images.values()), {})
        return first.get("hash", "")


def create_full_campaign(db, tenant_id: str, *, spec: dict) -> dict:
    creds = _get_ads_credentials(db, tenant_id)
    if not creds:
        return {"ok": False, "error": "No Ads Account ID / token configured for this tenant.",
                "campaign_id": None, "meta_campaign_id": None}
    token, account = creds
    try:
        camp = _post(f"{account}/campaigns", token, build_campaign_payload(
            spec["name"],
            daily_budget_inr=spec.get("daily_budget_inr"),
            lifetime_budget_inr=spec.get("lifetime_budget_inr"),
            special_ad_category=spec.get("special_ad_category")))
        targeting = build_targeting(spec["location_countries"], spec["age_min"],
                                    spec["age_max"], spec["gender"])
        adset = _post(f"{account}/adsets", token, build_adset_payload(
            f"{spec['name']} — Ad set", camp["id"], spec["page_id"], targeting))
        creative = _post(f"{account}/adcreatives", token, build_creative_payload(
            spec["creative_label"], spec["page_id"], spec["message"], spec["headline"],
            spec["image_hash"], spec["greeting"]))
        ad = _post(f"{account}/ads", token, build_ad_payload(
            spec["creative_label"], adset["id"], creative["id"]))
    except Exception as e:
        logger.error(f"create_full_campaign failed (tenant {tenant_id}): {e}")
        return {"ok": False, "error": str(e), "campaign_id": None, "meta_campaign_id": None}

    meta_ids = {"campaign_id": camp["id"], "adset_id": adset["id"],
                "ad_id": ad["id"], "creative_id": creative["id"]}
    row = persist_created_campaign(db, tenant_id, meta_ids, spec)
    return {"ok": True, "error": None, "campaign_id": row["id"], "meta_campaign_id": camp["id"]}


def persist_created_campaign(db, tenant_id: str, meta_ids: dict, spec: dict) -> dict:
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    camp_row = db.table("ad_campaigns").insert({
        "tenant_id": tenant_id, "platform": "whatsapp",
        "campaign_name": spec["name"], "external_campaign_id": meta_ids["campaign_id"],
        "objective": "OUTCOME_ENGAGEMENT", "created_via": "aira",
        "page_id": spec.get("page_id"), "special_ad_category": spec.get("special_ad_category"),
        "daily_budget": spec.get("daily_budget_inr"),
        "lifetime_budget": spec.get("lifetime_budget_inr"),
        "effective_status": "IN_PROCESS",
    }).execute().data[0]

    db.table("ad_sets").insert({
        "tenant_id": tenant_id, "campaign_id": camp_row["id"],
        "meta_adset_id": meta_ids["adset_id"], "adset_name": f"{spec['name']} — Ad set",
        "optimization_goal": "CONVERSATIONS", "created_via": "aira",
        "targeting": {"age_min": spec.get("age_min"), "age_max": spec.get("age_max"),
                      "gender": spec.get("gender"), "countries": spec.get("location_countries")},
        "created_at": now, "updated_at": now,
    }).execute()

    db.table("ad_creatives").insert({
        "tenant_id": tenant_id, "campaign_id": camp_row["id"],
        "meta_ad_id": meta_ids["ad_id"], "meta_adset_id": meta_ids["adset_id"],
        "meta_campaign_id": meta_ids["campaign_id"], "creative_label": spec["creative_label"],
        "created_by_aira": True, "prefilled_greeting": spec.get("greeting"),
        "media_asset_ref": meta_ids.get("creative_id"), "cta_type": "WHATSAPP_MESSAGE",
        "created_at": now, "updated_at": now,
    }).execute()
    return camp_row


def _meta_campaign_id(db, tenant_id: str, campaign_id: str) -> str | None:
    row = (db.table("ad_campaigns").select("external_campaign_id")
           .eq("id", campaign_id).eq("tenant_id", tenant_id).limit(1).execute().data or [None])[0]
    return row.get("external_campaign_id") if row else None


def set_campaign_status(db, tenant_id: str, campaign_id: str, active: bool) -> dict:
    creds = _get_ads_credentials(db, tenant_id)
    if not creds:
        return {"ok": False, "error": "No credentials configured."}
    token, _ = creds
    mid = _meta_campaign_id(db, tenant_id, campaign_id)
    if not mid:
        return {"ok": False, "error": "Campaign not found."}
    status = "ACTIVE" if active else "PAUSED"
    try:
        _post(mid, token, {"status": status})
    except Exception as e:
        return {"ok": False, "error": str(e)}
    db.table("ad_campaigns").update({"effective_status": status}).eq(
        "id", campaign_id).eq("tenant_id", tenant_id).execute()
    return {"ok": True, "error": None, "status": status}


def update_campaign_budget(db, tenant_id: str, campaign_id: str, *,
                           daily_budget_inr=None, lifetime_budget_inr=None) -> dict:
    creds = _get_ads_credentials(db, tenant_id)
    if not creds:
        return {"ok": False, "error": "No credentials configured."}
    token, _ = creds
    mid = _meta_campaign_id(db, tenant_id, campaign_id)
    if not mid:
        return {"ok": False, "error": "Campaign not found."}
    payload, updates = {}, {}
    if daily_budget_inr is not None:
        payload["daily_budget"] = int(round(daily_budget_inr * 100))
        updates["daily_budget"] = daily_budget_inr
    if lifetime_budget_inr is not None:
        payload["lifetime_budget"] = int(round(lifetime_budget_inr * 100))
        updates["lifetime_budget"] = lifetime_budget_inr
    if not payload:
        return {"ok": False, "error": "No budget provided."}
    try:
        _post(mid, token, payload)
    except Exception as e:
        return {"ok": False, "error": str(e)}
    db.table("ad_campaigns").update(updates).eq("id", campaign_id).eq("tenant_id", tenant_id).execute()
    return {"ok": True, "error": None}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_meta_ads_manager.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/meta_ads_manager.py backend/tests/test_meta_ads_manager.py
git commit -m "feat(meta-ads): write client + create-orchestrator + persistence"
```

---

### Task 4: Write endpoints on the meta-ads router + api client + hooks

**Files:**
- Modify: `backend/app/routes/meta_ads.py`
- Modify: `frontend/lib/api.ts` (client methods + types)
- Modify: `frontend/hooks/useApi.ts` (pages hook)
- Test: `backend/tests/test_meta_ads_write_routes_static.py`

**Interfaces:**
- Produces HTTP:
  - `GET /api/v1/meta-ads/pages` → `{data: [{id,name}]}`
  - `GET /api/v1/meta-ads/whatsapp-numbers` → `{data: [{number}]}` (reuses the existing primary-number helper)
  - `POST /api/v1/meta-ads/media` (multipart file) → `{image_hash}`
  - `POST /api/v1/meta-ads/campaigns` (JSON body = create spec) → `{ok, campaign_id, meta_campaign_id, error}`
  - `POST /api/v1/meta-ads/{campaign_id}/status` `{active: bool}` → `{ok, status, error}`
  - `PATCH /api/v1/meta-ads/{campaign_id}/budget` `{daily_budget_inr?, lifetime_budget_inr?}` → `{ok, error}`
- TS: `api.metaAds.pages/whatsappNumbers/uploadMedia/createCampaign/setStatus/updateBudget`, type `MetaAdsCreateSpec`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_meta_ads_write_routes_static.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.routes import meta_ads


def test_write_routes_registered():
    paths = {(tuple(sorted(r.methods)), r.path) for r in meta_ads.router.routes if hasattr(r, "methods")}
    flat = {p for _, p in paths}
    assert "/pages" in flat
    assert "/media" in flat
    assert "/campaigns" in flat
    assert "/{campaign_id}/status" in flat
    assert "/{campaign_id}/budget" in flat
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_meta_ads_write_routes_static.py -v`
Expected: FAIL (paths not present)

- [ ] **Step 3: Add the endpoints**

Append to `backend/app/routes/meta_ads.py` (add `Body`, `UploadFile`, `File` to the fastapi import, and a Pydantic model):

```python
from fastapi import APIRouter, Depends, Query, Body, UploadFile, File
from pydantic import BaseModel


class CreateSpec(BaseModel):
    name: str
    creative_label: str
    message: str
    headline: str
    greeting: str
    image_hash: str
    page_id: str
    location_countries: list[str] = ["IN"]
    age_min: int = 18
    age_max: int = 65
    gender: str = "all"
    daily_budget_inr: float | None = None
    lifetime_budget_inr: float | None = None
    special_ad_category: str | None = None


@router.get("/pages")
async def pages(tenant_id: str = Depends(get_tenant_id)):
    from app.services.meta_ads_insights_sync import _get_ads_credentials
    from app.services.meta_ads_manager import list_pages
    db = get_supabase()
    creds = _get_ads_credentials(db, tenant_id)
    if not creds:
        return {"data": []}
    token, account = creds
    try:
        return {"data": list_pages(token, account)}
    except Exception as e:
        logger.error(f"meta-ads pages error: {e}")
        return {"data": []}


@router.get("/whatsapp-numbers")
async def whatsapp_numbers(tenant_id: str = Depends(get_tenant_id)):
    from app.routes.inbound_leads import _primary_whatsapp_number
    db = get_supabase()
    num = _primary_whatsapp_number(db, tenant_id)
    return {"data": [{"number": num}] if num else []}


@router.post("/media")
async def media(file: UploadFile = File(...), tenant_id: str = Depends(get_tenant_id)):
    from app.services.meta_ads_insights_sync import _get_ads_credentials
    from app.services.meta_ads_manager import upload_image
    db = get_supabase()
    creds = _get_ads_credentials(db, tenant_id)
    if not creds:
        return {"image_hash": "", "error": "No credentials configured."}
    token, account = creds
    try:
        data = await file.read()
        return {"image_hash": upload_image(token, account, data, file.filename or "ad.jpg")}
    except Exception as e:
        logger.error(f"meta-ads media upload error: {e}")
        return {"image_hash": "", "error": str(e)}


@router.post("/campaigns")
async def create_campaign(spec: CreateSpec, tenant_id: str = Depends(get_tenant_id)):
    from app.services.meta_ads_manager import create_full_campaign
    db = get_supabase()
    return create_full_campaign(db, tenant_id, spec=spec.model_dump())


@router.post("/{campaign_id}/status")
async def set_status(campaign_id: str, body: dict = Body(...), tenant_id: str = Depends(get_tenant_id)):
    from app.services.meta_ads_manager import set_campaign_status
    db = get_supabase()
    return set_campaign_status(db, tenant_id, campaign_id, bool(body.get("active")))


@router.patch("/{campaign_id}/budget")
async def set_budget(campaign_id: str, body: dict = Body(...), tenant_id: str = Depends(get_tenant_id)):
    from app.services.meta_ads_manager import update_campaign_budget
    db = get_supabase()
    return update_campaign_budget(db, tenant_id, campaign_id,
                                  daily_budget_inr=body.get("daily_budget_inr"),
                                  lifetime_budget_inr=body.get("lifetime_budget_inr"))
```

In `frontend/lib/api.ts`, add the type near the other Meta Ads types:

```typescript
export interface MetaAdsCreateSpec {
  name: string;
  creative_label: string;
  message: string;
  headline: string;
  greeting: string;
  image_hash: string;
  page_id: string;
  location_countries: string[];
  age_min: number;
  age_max: number;
  gender: string;
  daily_budget_inr?: number;
  lifetime_budget_inr?: number;
  special_ad_category?: string | null;
}
```

Add to the `metaAds` client block:

```typescript
    pages: async () => apiFetch<{ data: { id: string; name: string }[] }>(`/api/v1/meta-ads/pages`),
    whatsappNumbers: async () => apiFetch<{ data: { number: string }[] }>(`/api/v1/meta-ads/whatsapp-numbers`),
    uploadMedia: async (file: File) => {
      const fd = new FormData();
      fd.append("file", file);
      const headers = await getAuthHeaders();
      const res = await fetch(`${API_URL}/api/v1/meta-ads/media`, { method: "POST", headers, body: fd });
      if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
      return res.json() as Promise<{ image_hash: string; error?: string }>;
    },
    createCampaign: async (spec: MetaAdsCreateSpec) =>
      apiFetch<{ ok: boolean; campaign_id: string | null; meta_campaign_id: string | null; error: string | null }>(
        `/api/v1/meta-ads/campaigns`, { method: "POST", body: JSON.stringify(spec) }),
    setStatus: async (campaignId: string, active: boolean) =>
      apiFetch<{ ok: boolean; status?: string; error: string | null }>(
        `/api/v1/meta-ads/${campaignId}/status`, { method: "POST", body: JSON.stringify({ active }) }),
    updateBudget: async (campaignId: string, budget: { daily_budget_inr?: number; lifetime_budget_inr?: number }) =>
      apiFetch<{ ok: boolean; error: string | null }>(
        `/api/v1/meta-ads/${campaignId}/budget`, { method: "PATCH", body: JSON.stringify(budget) }),
```

In `frontend/hooks/useApi.ts`, add:

```typescript
export function useMetaAdsPages(enabled = true) {
  return useSWR<{ data: { id: string; name: string }[] }>(
    enabled ? "meta-ads/pages" : null,
    () => api.metaAds.pages(),
    defaultConfig,
  );
}
```

- [ ] **Step 4: Run backend test + frontend gates**

Run: `cd backend && pytest tests/test_meta_ads_write_routes_static.py -v`
Expected: PASS (1 passed)

Run: `cd frontend && npm run lint && npm run typecheck`
Expected: no errors

- [ ] **Step 5: Commit**

```bash
git add backend/app/routes/meta_ads.py backend/tests/test_meta_ads_write_routes_static.py frontend/lib/api.ts frontend/hooks/useApi.ts
git commit -m "feat(meta-ads): write endpoints (create/status/budget/media/pages) + api client"
```

---

### Task 5: Create tab UI (single-scroll wizard + live preview) + third header tab

**Files:**
- Create: `frontend/app/dashboard/meta-ads/MetaAdsCreateTab.tsx`
- Modify: `frontend/app/dashboard/meta-ads/MetaAdsClient.tsx` (add `create` tab)
- Modify: `frontend/components/AppHeader.tsx` (add "Create" pill)

**Interfaces:**
- Consumes: `api.metaAds.pages/whatsappNumbers/uploadMedia/createCampaign`, `useMetaAdsPages`.
- Produces: a single-scroll form — Objective (locked card), Audience (location/age/gender + special-category link), Budget & Schedule (daily/lifetime + amount), Creative (name/media/text/greeting/page) — with a sticky live preview and a Publish button.

- [ ] **Step 1: Add the `create` tab to the header**

In `AppHeader.tsx`, change the Meta Ads pill array from `["performance", "analytics"]` to `["create", "performance", "analytics"]`, add the label mapping, and update the default-tab check. Replace the Meta Ads pill block's `.map` body with:

```tsx
            {(["create", "performance", "analytics"] as const).map((t) => (
              <button
                key={t}
                onClick={() => {
                  const params = new URLSearchParams(searchParams.toString());
                  if (t === "performance") params.delete("tab");
                  else params.set("tab", t);
                  const query = params.toString();
                  router.replace(`/dashboard/meta-ads${query ? `?${query}` : ""}`, { scroll: false });
                }}
                className={cn(
                  "px-3 py-1.5 rounded-xl font-label text-xs font-bold transition-all",
                  (tab === t || (t === "performance" && !tab))
                    ? "bg-white text-primary shadow-sm"
                    : "text-[#78716c] hover:text-[#292524]"
                )}
              >
                {t === "create" ? "Create" : t === "performance" ? "Ad Performance" : "Analytics"}
              </button>
            ))}
```

Also update the `/dashboard/meta-ads` description block to mention Create:

```tsx
  if (pathname === "/dashboard/meta-ads") {
    let desc = "Full-account ad performance and lead-quality analytics across your Meta campaigns.";
    if (tab === "analytics") desc = "Lead-quality analytics and insights beyond what Meta's own dashboard can show.";
    if (tab === "create") desc = "Build and publish a Click-to-WhatsApp ad — no need to leave Aira.";
    return { title: "Meta Ads", description: desc };
  }
```

- [ ] **Step 2: Add `create` to the client switch**

In `MetaAdsClient.tsx`, import the new tab and extend the tab resolution:

```tsx
import { MetaAdsCreateTab } from "./MetaAdsCreateTab";
// ...
  const raw = searchParams.get("tab");
  const tab = raw === "analytics" ? "analytics" : raw === "create" ? "create" : "performance";
// ...
  return (
    <div className="p-6 md:p-8">
      {tab === "create" ? (
        <MetaAdsCreateTab />
      ) : tab === "performance" ? (
        <MetaAdsPerformanceTab dateFrom={dateFrom} dateTo={dateTo} setDateFrom={setDateFrom} setDateTo={setDateTo} />
      ) : (
        <MetaAdsAnalyticsTab dateFrom={dateFrom} dateTo={dateTo} setDateFrom={setDateFrom} setDateTo={setDateTo} />
      )}
    </div>
  );
```

- [ ] **Step 3: Build the Create tab**

```tsx
// frontend/app/dashboard/meta-ads/MetaAdsCreateTab.tsx
"use client";
import { useEffect, useState } from "react";
import { api, MetaAdsCreateSpec } from "@/lib/api";
import { useMetaAdsPages } from "@/hooks/useApi";
import { MessageCircle, Upload, Loader2 } from "lucide-react";
import { toast } from "sonner";

const inputCls = "h-9 w-full rounded-xl border border-surface-mid bg-white px-3 font-body text-sm text-on-surface focus:outline-none focus:ring-2 focus:ring-violet-200";
const labelCls = "mb-1 block font-label text-[10px] font-bold uppercase tracking-wider text-on-surface-muted";

export function MetaAdsCreateTab() {
  const { data: pagesData } = useMetaAdsPages();
  const pages = pagesData?.data ?? [];

  const [name, setName] = useState("");
  const [ageMin, setAgeMin] = useState(18);
  const [ageMax, setAgeMax] = useState(65);
  const [gender, setGender] = useState("all");
  const [budgetType, setBudgetType] = useState<"daily" | "lifetime">("daily");
  const [amount, setAmount] = useState<number>(500);
  const [message, setMessage] = useState("");
  const [headline, setHeadline] = useState("");
  const [greeting, setGreeting] = useState("Hi! I'm interested.");
  const [pageId, setPageId] = useState("");
  const [imageHash, setImageHash] = useState("");
  const [imagePreview, setImagePreview] = useState("");
  const [uploading, setUploading] = useState(false);
  const [publishing, setPublishing] = useState(false);

  useEffect(() => { if (pages.length && !pageId) setPageId(pages[0].id); }, [pages, pageId]);

  async function handleUpload(file: File) {
    setUploading(true);
    try {
      const res = await api.metaAds.uploadMedia(file);
      if (res.image_hash) {
        setImageHash(res.image_hash);
        setImagePreview(URL.createObjectURL(file));
        toast.success("Image uploaded");
      } else {
        toast.error(res.error ?? "Upload failed");
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  const canPublish = name && message && headline && greeting && pageId && imageHash && amount > 0;

  async function handlePublish() {
    if (!canPublish) return;
    setPublishing(true);
    try {
      const spec: MetaAdsCreateSpec = {
        name, creative_label: name, message, headline, greeting, image_hash: imageHash,
        page_id: pageId, location_countries: ["IN"], age_min: ageMin, age_max: ageMax, gender,
        daily_budget_inr: budgetType === "daily" ? amount : undefined,
        lifetime_budget_inr: budgetType === "lifetime" ? amount : undefined,
      };
      const res = await api.metaAds.createCampaign(spec);
      if (res.ok) toast.success("Campaign submitted to Meta — review takes ~24h.");
      else toast.error(res.error ?? "Publish failed");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Publish failed");
    } finally {
      setPublishing(false);
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
      {/* Form */}
      <div className="space-y-6">
        {/* Objective (locked) */}
        <section className="card rounded-2xl p-5">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-violet-50 text-violet-600"><MessageCircle size={22} /></div>
            <div>
              <h3 className="font-display text-base font-bold text-on-surface">Get WhatsApp messages</h3>
              <p className="font-body text-xs text-on-surface-muted">People tap your ad and land in a WhatsApp chat with you.</p>
            </div>
          </div>
        </section>

        {/* Audience */}
        <section className="card rounded-2xl p-5 space-y-4">
          <h3 className="font-display text-sm font-bold text-on-surface">Audience</h3>
          <div>
            <label className={labelCls}>Location</label>
            <input className={inputCls} value="India" disabled />
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div><label className={labelCls}>Age min</label>
              <input type="number" min={13} max={65} className={inputCls} value={ageMin} onChange={(e) => setAgeMin(+e.target.value)} /></div>
            <div><label className={labelCls}>Age max</label>
              <input type="number" min={13} max={65} className={inputCls} value={ageMax} onChange={(e) => setAgeMax(+e.target.value)} /></div>
            <div><label className={labelCls}>Gender</label>
              <select className={inputCls} value={gender} onChange={(e) => setGender(e.target.value)}>
                <option value="all">All</option><option value="male">Men</option><option value="female">Women</option>
              </select></div>
          </div>
          <p className="font-body text-[11px] text-on-surface-muted">Placements and audience-finding are optimized automatically by Meta Advantage+.</p>
        </section>

        {/* Budget */}
        <section className="card rounded-2xl p-5 space-y-4">
          <h3 className="font-display text-sm font-bold text-on-surface">Budget &amp; schedule</h3>
          <div className="flex gap-2">
            {(["daily", "lifetime"] as const).map((b) => (
              <button key={b} onClick={() => setBudgetType(b)}
                className={`px-3 py-1.5 rounded-xl text-xs font-bold ${budgetType === b ? "bg-primary text-white" : "bg-surface-low text-on-surface-muted"}`}>
                {b === "daily" ? "Daily" : "Total"}
              </button>
            ))}
          </div>
          <div>
            <label className={labelCls}>Amount (₹)</label>
            <input type="number" min={1} className={inputCls} value={amount} onChange={(e) => setAmount(+e.target.value)} />
          </div>
          <p className="rounded-lg bg-amber-50 px-3 py-2 font-body text-[11px] text-amber-700">💡 We recommend at least ₹1,500 total and 7 days so Meta can learn who to show your ad to.</p>
        </section>

        {/* Creative */}
        <section className="card rounded-2xl p-5 space-y-4">
          <h3 className="font-display text-sm font-bold text-on-surface">Creative</h3>
          <div><label className={labelCls}>Campaign name</label>
            <input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Diwali Offer" /></div>
          <div><label className={labelCls}>Photo</label>
            <label className="flex cursor-pointer items-center justify-center gap-2 rounded-xl border border-dashed border-surface-mid py-6 text-xs font-semibold text-on-surface-muted hover:bg-surface-low">
              {uploading ? <Loader2 size={16} className="animate-spin" /> : <Upload size={16} />}
              {imageHash ? "Replace image" : "Upload image"}
              <input type="file" accept="image/*" className="hidden" onChange={(e) => e.target.files?.[0] && handleUpload(e.target.files[0])} />
            </label></div>
          <div><label className={labelCls}>Ad text</label>
            <textarea className={`${inputCls} h-20 py-2`} value={message} onChange={(e) => setMessage(e.target.value)} placeholder="The message shown above your image" /></div>
          <div><label className={labelCls}>Headline</label>
            <input className={inputCls} value={headline} onChange={(e) => setHeadline(e.target.value)} /></div>
          <div><label className={labelCls}>Facebook Page</label>
            <select className={inputCls} value={pageId} onChange={(e) => setPageId(e.target.value)}>
              {pages.length === 0 && <option value="">No page available</option>}
              {pages.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select></div>
          <div><label className={labelCls}>Pre-filled greeting</label>
            <input className={inputCls} value={greeting} onChange={(e) => setGreeting(e.target.value)} />
            <p className="mt-1 font-body text-[11px] text-on-surface-muted">We add an invisible tracking tag to this automatically so replies attribute to this ad.</p></div>
        </section>

        <button onClick={handlePublish} disabled={!canPublish || publishing}
          className="flex w-full items-center justify-center gap-2 rounded-xl bg-primary py-3 font-label text-sm font-bold text-white transition-all hover:bg-primary/90 disabled:opacity-40">
          {publishing ? <Loader2 size={16} className="animate-spin" /> : null}
          {publishing ? "Publishing…" : "Publish campaign"}
        </button>
      </div>

      {/* Live preview */}
      <div className="lg:sticky lg:top-24 h-fit">
        <div className="card rounded-2xl p-4">
          <p className="mb-3 font-label text-[10px] font-bold uppercase tracking-wider text-on-surface-muted">Live preview</p>
          <div className="rounded-xl border border-surface-mid overflow-hidden">
            <div className="flex items-center gap-2 p-3">
              <div className="h-8 w-8 rounded-full bg-violet-100" />
              <span className="font-label text-xs font-bold text-on-surface">{pages.find((p) => p.id === pageId)?.name ?? "Your Page"}</span>
            </div>
            {imagePreview
              ? <img src={imagePreview} alt="Ad preview" className="w-full object-cover" style={{ maxHeight: 220 }} />
              : <div className="flex h-40 items-center justify-center bg-surface-low text-xs text-on-surface-muted">Image preview</div>}
            <div className="p-3">
              <p className="font-body text-sm text-on-surface">{message || "Your ad text appears here."}</p>
              <p className="mt-1 font-label text-xs font-bold text-on-surface">{headline || "Headline"}</p>
              <button className="mt-3 flex w-full items-center justify-center gap-2 rounded-lg bg-[#25D366] py-2 text-xs font-bold text-white">
                <MessageCircle size={14} /> Send Message
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Verify build + lint**

Run: `cd frontend && npm run lint && npm run typecheck`
Expected: no errors. (Note: the `<img>` will draw an `@next/next/no-img-element` **warning**, not an error — acceptable, matching the preview pattern; if it errors in this config, add `// eslint-disable-next-line @next/next/no-img-element` above the tag.)

- [ ] **Step 5: Commit**

```bash
git add frontend/app/dashboard/meta-ads/MetaAdsCreateTab.tsx frontend/app/dashboard/meta-ads/MetaAdsClient.tsx frontend/components/AppHeader.tsx
git commit -m "feat(meta-ads): Create tab — single-scroll CTWA wizard + live preview"
```

---

### Task 6: Management actions on the Ad Performance table (status toggle + budget edit)

**Files:**
- Modify: `frontend/app/dashboard/meta-ads/MetaAdsPerformanceTab.tsx`

**Interfaces:**
- Consumes: `api.metaAds.setStatus/updateBudget`, `mutate` from the SWR hook.
- Produces: a leading On/Off toggle column and an inline budget-edit control, both only for campaign-level rows (`level === "campaign"`, since status/budget are campaign-level). Editing discloses "shared across the campaign."

- [ ] **Step 1: Add the toggle + budget-edit UI**

At the top of `MetaAdsPerformanceTab.tsx` add imports and per-row handlers. Add `import { toast } from "sonner";` and a busy-state map:

```tsx
  const [busy, setBusy] = useState<Record<string, boolean>>({});

  async function toggleStatus(row: MetaAdsPerfRow) {
    if (level !== "campaign") return;
    const active = (row.status ?? "").toUpperCase() !== "ACTIVE";
    setBusy((b) => ({ ...b, [row.group_id]: true }));
    try {
      const res = await api.metaAds.setStatus(row.group_id, active);
      if (res.ok) { toast.success(active ? "Campaign activated" : "Campaign paused"); mutate(); }
      else toast.error(res.error ?? "Status change failed");
    } finally {
      setBusy((b) => ({ ...b, [row.group_id]: false }));
    }
  }

  async function editBudget(row: MetaAdsPerfRow) {
    const raw = window.prompt(`New daily budget in ₹ for "${row.name}" (shared across the whole campaign):`);
    if (!raw) return;
    const val = Number(raw);
    if (!val || val <= 0) { toast.error("Enter a valid amount"); return; }
    const res = await api.metaAds.updateBudget(row.group_id, { daily_budget_inr: val });
    if (res.ok) { toast.success("Budget updated"); mutate(); }
    else toast.error(res.error ?? "Budget update failed");
  }
```

Add `import { api } from "@/lib/api";` (extend the existing `@/lib/api` import to also pull `api`).

**Do NOT add "On" to the `headers` array** — that array drives index-based alignment (`i === 0 ? left : i === 1 ? center : right`), so inserting a column would misalign every existing header. Instead prepend a **standalone** `<th>` before the `{headers.map(...)}`:

```tsx
                <tr className="border-b border-surface-mid bg-surface-low/60">
                  <th className="px-3 py-3 font-label text-[10px] font-bold text-on-surface-muted uppercase tracking-wider">On</th>
                  {headers.map((h, i) => (
```

and a standalone leading `<td>` before the Name cell in each row:

```tsx
                  <tr key={r.group_id} className="hover:bg-surface-low/60 transition-colors">
                    <td className="px-3 py-3">
                      {level === "campaign" ? (
                        <button onClick={() => toggleStatus(r)} disabled={busy[r.group_id]}
                          className={cn("relative h-5 w-9 rounded-full transition-colors",
                            (r.status ?? "").toUpperCase() === "ACTIVE" ? "bg-emerald-500" : "bg-surface-mid")}>
                          <span className={cn("absolute top-0.5 h-4 w-4 rounded-full bg-white transition-transform",
                            (r.status ?? "").toUpperCase() === "ACTIVE" ? "translate-x-4" : "translate-x-0.5")} />
                        </button>
                      ) : <span className="text-on-surface-muted">—</span>}
                    </td>
```

And make the Budget cell editable at campaign level:

```tsx
                    <td className="px-4 py-3 text-right text-xs whitespace-nowrap">
                      {level === "campaign" ? (
                        <button onClick={() => editBudget(r)} className="text-primary hover:underline">
                          {r.budget_label ?? "Set"} ✎
                        </button>
                      ) : (r.budget_label ?? "—")}
                    </td>
```

(Replace the existing budget `<td>` with this; leave the other cells unchanged.)

- [ ] **Step 2: Verify build + lint**

Run: `cd frontend && npm run lint && npm run typecheck`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/dashboard/meta-ads/MetaAdsPerformanceTab.tsx
git commit -m "feat(meta-ads): campaign status toggle + inline budget edit on Ad Performance"
```

---

### Task 7: Full verification pass

**Files:** none (verification only)

- [ ] **Step 1: Backend suite**

Run: `cd backend && pytest -q`
Expected: all new tests pass; no new failures beyond documented pre-existing env-only ones.

- [ ] **Step 2: Frontend gates**

Run: `cd frontend && npm run lint && npm run typecheck && npm run build`
Expected: all pass; `/dashboard/meta-ads` builds with the Create tab.

- [ ] **Step 3: Live smoke test (user-side, gated on approval)**

This cannot be verified in CI — it needs a real Meta round-trip. On Standard Access, point `meta_ads_account_id` at **Aira's own test ad account** with a token carrying `ads_management` + `pages_manage_ads`:
1. Open **Meta Ads → Create**. Confirm the Page dropdown populates from `/pages`.
2. Fill the form, upload an image (confirm `/media` returns a hash), Publish. Confirm a campaign/adset/creative/ad appears in the test account's Ads Manager and an `ad_campaigns` row with `created_via='aira'` is written.
3. In **Ad Performance** (campaign level) toggle the campaign Off/On and edit its budget; confirm the change reflects in Meta Ads Manager.
Once Advanced Access is granted, repeat against a real client ad account — no code change required.

- [ ] **Step 4: Commit any fixes**

```bash
git add -A
git commit -m "fix(meta-ads): verification-pass fixes"
```

---

## Self-Review Notes

- **Spec coverage:** Create wizard (objective locked / audience / budget / creative / preview / publish) → Tasks 2–3, 5. Status/budget management → Tasks 3–4, 6. `ad_sets` table + create-columns → Task 1. Page-id + media-upload dependencies → Tasks 3–4. Draft-pending-approval reality → Global Constraints + Task 7 Step 3.
- **CBO invariant:** budget lives on the campaign in `build_campaign_payload`; `build_adset_payload` has no budget field — asserted in `test_adset_payload_is_whatsapp_conversations_no_budget`.
- **Money direction:** rupees→paise (`*100`) on every write payload; asserted in the campaign and budget tests. This is the exact inverse of Plan 1's `/100` read.
- **Not live-verifiable in CI:** actual Meta create/status/budget round-trips need `ads_management` (pending) — the payload builders (Task 2) and persistence (Task 3) are unit-tested; the HTTP wrappers are thin and covered by monkeypatched orchestration tests; live verification is the Task 7 Step 3 manual checklist.
- **Lint trap carried from Plan 1:** never name an unused param `_props`; the `<img>` in the preview is a warning not an error (disable-comment ready if the config escalates it).
