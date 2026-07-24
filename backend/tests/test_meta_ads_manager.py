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
