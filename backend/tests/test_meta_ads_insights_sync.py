from app.services.meta_ads_insights_sync import (
    is_click_to_whatsapp_adset,
    normalize_account_id,
    upsert_creative_from_insight,
    sync_tenant_ad_insights_verbose,
)


def test_normalize_account_id_adds_prefix():
    assert normalize_account_id("1910086849857231") == "act_1910086849857231"


def test_normalize_account_id_keeps_prefix():
    assert normalize_account_id("act_1910086849857231") == "act_1910086849857231"


def test_normalize_account_id_strips_whitespace():
    assert normalize_account_id("  act_123 ") == "act_123"


def test_only_exact_whatsapp_destination_is_included():
    assert is_click_to_whatsapp_adset({"destination_type": "WHATSAPP"}) is True
    assert is_click_to_whatsapp_adset({"destination_type": "MESSENGER"}) is False
    assert is_click_to_whatsapp_adset({
        "destination_type": "MESSAGING_MESSENGER_WHATSAPP",
    }) is False


def test_unique_reach_uses_one_meta_window_per_ad(monkeypatch):
    import app.services.meta_ads_insights_sync as mod

    requests = []

    class FakeResponse:
        def raise_for_status(self): pass
        def json(self): return {"data": [{"ad_id": "A1", "reach": "17309"}]}

    class FakeClient:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, url, params):
            requests.append((url, params))
            return FakeResponse()

    monkeypatch.setattr(mod.httpx, "Client", FakeClient)

    result = mod.fetch_unique_reach_by_ad(
        "token", "act_1", date_from="2026-07-03", date_to="2026-08-01",
    )

    assert result == {"A1": 17309}
    assert requests[0][1]["time_range"] == '{"since": "2026-07-03", "until": "2026-08-01"}'


class FakeTable:
    def __init__(self, store, name):
        self.store, self.name, self._filters, self._payload = store, name, {}, None
        self._op = None
        self._single = False

    def select(self, *a): self._op = "select"; return self
    def eq(self, k, v): self._filters[k] = v; return self
    def in_(self, k, v): self._filters[k] = ("in", v); return self
    def limit(self, n): return self
    def maybe_single(self): self._single = True; return self

    def insert(self, payload):
        self._op, self._payload = "insert", payload; return self

    def update(self, payload):
        self._op, self._payload = "update", payload; return self

    def upsert(self, payload, on_conflict=None):
        self._op, self._payload, self._on_conflict = "upsert", payload, on_conflict; return self

    def _matches(self, r):
        for k, v in self._filters.items():
            if isinstance(v, tuple) and v[0] == "in":
                if r.get(k) not in v[1]:
                    return False
            elif r.get(k) != v:
                return False
        return True

    def execute(self):
        rows = self.store.setdefault(self.name, [])
        if self._op == "select":
            match = [r for r in rows if self._matches(r)]
            class R: data = (match[0] if match else None) if self._single else match
            return R()
        if self._op == "insert":
            row = dict(self._payload); row.setdefault("id", f"cr-{len(rows)+1}")
            rows.append(row)
            class R: data = [row]
            return R()
        if self._op == "update":
            touched = []
            for r in rows:
                if self._matches(r):
                    r.update(self._payload)
                    touched.append(r)
            # PostgREST returns the updated rows (supabase-py sends
            # Prefer: return=representation), so the fake does too.
            class R: data = touched
            return R()
        if self._op == "upsert":
            key_cols = (self._on_conflict or "id").split(",")
            existing = next(
                (r for r in rows if all(r.get(k) == self._payload.get(k) for k in key_cols)),
                None,
            )
            if existing:
                existing.update(self._payload)
            else:
                rows.append(dict(self._payload))
            class R: data = [self._payload]
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


def test_verbose_sync_reports_missing_credentials():
    db = FakeDB()
    result = sync_tenant_ad_insights_verbose(db, "t1")
    assert result["ok"] is False
    assert "credentials" in result["error"].lower() or "token" in result["error"].lower()
    assert result["written"] == 0


def test_verbose_sync_reports_fetch_failure(monkeypatch):
    import app.services.meta_ads_insights_sync as mod
    db = FakeDB()
    db.store["app_settings"] = [
        {"tenant_id": "t1", "key": "meta_ads_access_token", "value": "tok"},
        {"tenant_id": "t1", "key": "meta_ads_account_id", "value": "act_1"},
    ]
    def boom(*a, **k):
        raise RuntimeError("Meta 400: Missing Permissions")
    monkeypatch.setattr(mod, "_fetch_insights", boom)
    result = sync_tenant_ad_insights_verbose(db, "t1")
    assert result["ok"] is False
    assert "Missing Permissions" in result["error"]
    assert result["written"] == 0


def test_verbose_sync_writes_and_reports_success(monkeypatch):
    import app.services.meta_ads_insights_sync as mod
    monkeypatch.setattr(mod, "get_or_create_campaign", lambda **k: {"id": "camp-1"})
    db = FakeDB()
    db.store["app_settings"] = [
        {"tenant_id": "t1", "key": "meta_ads_access_token", "value": "tok"},
        {"tenant_id": "t1", "key": "meta_ads_account_id", "value": "act_1"},
    ]
    fake_rows = [{
        "ad_id": "A1", "ad_name": "Clarity", "adset_id": "as1", "adset_name": "Set",
        "campaign_id": "c1", "campaign_name": "Camp",
        "clicks": "5", "inline_link_clicks": "4", "spend": "10.0", "date_start": "2026-07-20",
    }]
    monkeypatch.setattr(mod, "_fetch_insights", lambda *a, **k: fake_rows)
    monkeypatch.setattr(mod, "_fetch_adsets", lambda *a, **k: [{
        "id": "as1",
        "name": "Set",
        "destination_type": "WHATSAPP",
        "optimization_goal": "CONVERSATIONS",
        "effective_status": "ACTIVE",
        "daily_budget": "80000",
    }])
    # Campaign metadata enrichment is a separate Meta call — mock it so the
    # unit test stays hermetic (no live Graph API request).
    monkeypatch.setattr(mod, "_fetch_campaigns", lambda *a, **k: [])
    result = sync_tenant_ad_insights_verbose(db, "t1")
    assert result["ok"] is True
    assert result["error"] is None
    assert result["rows_fetched"] == 1
    assert result["whatsapp_rows"] == 1
    assert result["skipped_non_whatsapp"] == 0
    assert result["written"] == 1
    assert len(db.store["ad_insights_daily"]) == 1
    assert db.store["ad_insights_daily"][0]["meta_ad_account_id"] == "act_1"
    assert db.store["ad_creatives"][0]["is_click_to_whatsapp"] is True
    assert db.store["ad_sets"][0]["meta_ad_account_id"] == "act_1"
    assert db.store["ad_sets"][0]["daily_budget"] == 800.0


def test_verbose_sync_includes_today_live_delivery(monkeypatch):
    import app.services.meta_ads_insights_sync as mod

    monkeypatch.setattr(mod, "get_or_create_campaign", lambda **k: {"id": "camp-1"})
    db = FakeDB()
    db.store["app_settings"] = [
        {"tenant_id": "t1", "key": "meta_ads_access_token", "value": "tok"},
        {"tenant_id": "t1", "key": "meta_ads_account_id", "value": "act_1"},
    ]
    presets = []

    def fetch_insights(_token, _account, preset):
        presets.append(preset)
        return [{
            "ad_id": "A1", "ad_name": "Clarity", "adset_id": "as1", "adset_name": "Set",
            "campaign_id": "c1", "campaign_name": "Camp", "date_start": "2026-08-02",
        }] if preset == "last_30d" else [{
            "ad_id": "A1", "ad_name": "Clarity", "adset_id": "as1", "adset_name": "Set",
            "campaign_id": "c1", "campaign_name": "Camp", "date_start": "2026-08-03",
        }]

    monkeypatch.setattr(mod, "_fetch_insights", fetch_insights)
    monkeypatch.setattr(mod, "_fetch_adsets", lambda *a, **k: [{
        "id": "as1", "destination_type": "WHATSAPP",
    }])
    monkeypatch.setattr(mod, "_fetch_campaigns", lambda *a, **k: [])

    result = sync_tenant_ad_insights_verbose(db, "t1")

    assert result["ok"] is True
    assert presets == ["last_30d", "today"]
    assert result["rows_fetched"] == 2
    assert result["written"] == 2
    assert {row["insight_date"] for row in db.store["ad_insights_daily"]} == {
        "2026-08-02", "2026-08-03",
    }


def test_verbose_sync_skips_non_whatsapp_ads(monkeypatch):
    import app.services.meta_ads_insights_sync as mod
    db = FakeDB()
    db.store["app_settings"] = [
        {"tenant_id": "t1", "key": "meta_ads_access_token", "value": "tok"},
        {"tenant_id": "t1", "key": "meta_ads_account_id", "value": "act_1"},
    ]
    monkeypatch.setattr(mod, "_fetch_insights", lambda *a, **k: [{
        "ad_id": "A1",
        "adset_id": "as1",
        "campaign_id": "c1",
        "date_start": "2026-07-20",
    }])
    monkeypatch.setattr(mod, "_fetch_adsets", lambda *a, **k: [{
        "id": "as1",
        "destination_type": "WEBSITE",
    }])
    monkeypatch.setattr(mod, "_fetch_campaigns", lambda *a, **k: [])

    result = sync_tenant_ad_insights_verbose(db, "t1")

    assert result["ok"] is True
    assert result["rows_fetched"] == 1
    assert result["whatsapp_rows"] == 0
    assert result["skipped_non_whatsapp"] == 1
    assert result["written"] == 0
    assert db.store.get("ad_creatives", []) == []


# --- Ad-level delivery status (fix for stale "Active" on deleted ads) ---------
#
# The dashboard's Delivery column used to render the *campaign's* status. An ad
# deleted in Ads Manager stopped coming back from Meta, the update-only sync
# never touched its row again, and it kept showing Active indefinitely.


def _creative(cid, ad_id, status="ACTIVE", tenant="t1", account="act_1"):
    return {
        "id": cid, "tenant_id": tenant, "meta_ad_id": ad_id,
        "meta_ad_account_id": account, "ad_effective_status": status,
    }


def test_fetch_ads_asks_meta_for_deleted_and_archived():
    """Meta's /ads edge hides DELETED/ARCHIVED unless the request names them."""
    import app.services.meta_ads_insights_sync as mod
    import json as _json

    captured = {}

    class FakeResponse:
        def raise_for_status(self): pass
        def json(self): return {"data": [{"id": "A1", "effective_status": "DELETED"}]}

    class FakeClient:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, url, params):
            captured["url"], captured["params"] = url, params
            return FakeResponse()

    import unittest.mock as _mock
    with _mock.patch.object(mod.httpx, "Client", FakeClient):
        ads = mod._fetch_ads("token", "act_1")

    assert ads == [{"id": "A1", "effective_status": "DELETED"}]
    assert captured["url"].endswith("/act_1/ads")
    clause = _json.loads(captured["params"]["filtering"])[0]
    assert clause["field"] == "ad.effective_status"
    assert "DELETED" in clause["value"] and "ARCHIVED" in clause["value"]


def test_fetch_all_statuses_falls_back_when_meta_rejects_the_filter():
    """A rejected filter must not take the whole sync down with it."""
    import app.services.meta_ads_insights_sync as mod
    import httpx as _httpx

    calls = []

    def fake_paged(url, params):
        calls.append(params)
        if "filtering" in params:
            request = _httpx.Request("GET", url)
            response = _httpx.Response(400, text="unsupported filter", request=request)
            raise _httpx.HTTPStatusError("400", request=request, response=response)
        return [{"id": "A1"}]

    import unittest.mock as _mock
    with _mock.patch.object(mod, "_fetch_paged", fake_paged):
        out = mod._fetch_paged_all_statuses(
            "http://x/ads", {"fields": "id"},
            status_field="ad.effective_status", statuses=["ACTIVE", "DELETED"],
        )

    assert out == [{"id": "A1"}]
    assert len(calls) == 2 and "filtering" not in calls[1]


def test_delivery_status_writes_each_ads_own_status():
    import app.services.meta_ads_insights_sync as mod
    db = FakeDB()
    db.store["ad_creatives"] = [
        _creative("cr-1", "A1"), _creative("cr-2", "A2"), _creative("cr-3", "A3"),
    ]

    result = mod.sync_ad_delivery_status(
        db, "t1", "token", "act_1",
        ads=[
            {"id": "A1", "effective_status": "ACTIVE"},
            {"id": "A2", "effective_status": "PAUSED"},
            {"id": "A3", "effective_status": "DELETED"},
        ],
    )

    by_id = {r["id"]: r for r in db.store["ad_creatives"]}
    assert by_id["cr-1"]["ad_effective_status"] == "ACTIVE"
    assert by_id["cr-2"]["ad_effective_status"] == "PAUSED"
    assert by_id["cr-3"]["ad_effective_status"] == "DELETED"
    assert all(r.get("last_seen_at") for r in db.store["ad_creatives"])
    assert result["reconciled"] is True and result["marked_deleted"] == 0


def test_ad_missing_from_meta_is_marked_deleted():
    """The reported bug: the ad is gone from Ads Manager, so Meta stops
    returning it entirely -- not even with DELETED in the status filter."""
    import app.services.meta_ads_insights_sync as mod
    db = FakeDB()
    db.store["ad_creatives"] = [_creative("cr-1", "A1"), _creative("cr-2", "GONE")]

    result = mod.sync_ad_delivery_status(
        db, "t1", "token", "act_1",
        ads=[{"id": "A1", "effective_status": "ACTIVE"}],
    )

    by_id = {r["id"]: r for r in db.store["ad_creatives"]}
    assert by_id["cr-1"]["ad_effective_status"] == "ACTIVE"
    assert by_id["cr-2"]["ad_effective_status"] == "DELETED"
    assert result["marked_deleted"] == 1


def test_empty_ads_response_does_not_mark_everything_deleted():
    """An empty edge is a failed/denied fetch far more often than an empty
    account. Marking the tenant's whole table DELETED on that would be worse
    than the stale status this fix replaces."""
    import app.services.meta_ads_insights_sync as mod
    db = FakeDB()
    db.store["ad_creatives"] = [_creative("cr-1", "A1")]

    result = mod.sync_ad_delivery_status(db, "t1", "token", "act_1", ads=[])

    assert db.store["ad_creatives"][0]["ad_effective_status"] == "ACTIVE"
    assert result["reconciled"] is False and result["marked_deleted"] == 0


def test_other_tenants_creatives_are_untouched():
    import app.services.meta_ads_insights_sync as mod
    db = FakeDB()
    db.store["ad_creatives"] = [
        _creative("cr-1", "A1"),
        _creative("cr-2", "B1", tenant="t2"),
    ]

    mod.sync_ad_delivery_status(db, "t1", "token", "act_1", ads=[{"id": "A1", "effective_status": "PAUSED"}])

    by_id = {r["id"]: r for r in db.store["ad_creatives"]}
    assert by_id["cr-1"]["ad_effective_status"] == "PAUSED"
    assert by_id["cr-2"]["ad_effective_status"] == "ACTIVE"
    assert by_id["cr-2"].get("last_seen_at") is None
