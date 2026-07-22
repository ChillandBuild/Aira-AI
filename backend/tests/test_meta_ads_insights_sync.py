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
