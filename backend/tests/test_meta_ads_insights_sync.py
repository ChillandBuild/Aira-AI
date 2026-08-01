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
            for r in rows:
                if self._matches(r):
                    r.update(self._payload)
            class R: data = []
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
