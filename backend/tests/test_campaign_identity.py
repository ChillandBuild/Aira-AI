"""get_or_create_campaign matches on external_campaign_id first and falls back to
the campaign name. That fallback used to adopt ANY same-named row, so two
distinct Meta campaigns sharing a name collapsed into one ad_campaigns row --
which is how a deleted ad ended up inheriting a still-live campaign's ACTIVE
status in the Meta Ads dashboard's Delivery column.

The fallback still exists because CSV upload supplies a campaign name and no id,
but it now refuses a row already claimed by a different external id.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.growth import get_or_create_campaign


class FakeTable:
    def __init__(self, rows):
        self.rows, self._filters, self._op, self._payload = rows, {}, None, None

    def select(self, *a): self._op = "select"; return self
    def eq(self, k, v): self._filters[k] = v; return self
    def limit(self, n): return self

    def insert(self, payload): self._op, self._payload = "insert", payload; return self
    def update(self, payload): self._op, self._payload = "update", payload; return self

    def _matches(self, r):
        return all(r.get(k) == v for k, v in self._filters.items())

    def execute(self):
        if self._op == "select":
            class R: data = [r for r in self.rows if self._matches(r)]
            R.data = [r for r in self.rows if self._matches(r)]
            return R()
        if self._op == "insert":
            row = dict(self._payload)
            row.setdefault("id", f"camp-{len(self.rows) + 1}")
            self.rows.append(row)
            class R: pass
            R.data = [row]
            return R()
        if self._op == "update":
            touched = []
            for r in self.rows:
                if self._matches(r):
                    r.update(self._payload)
                    touched.append(r)
            class R: pass
            R.data = touched
            return R()
        class R: pass
        R.data = []
        return R()


class FakeDB:
    def __init__(self, rows=None): self.rows = rows if rows is not None else []
    def table(self, name): return FakeTable(self.rows)


def test_same_name_different_meta_id_creates_a_separate_campaign():
    """The regression. Two 'Astro Whatsapp-WB' campaigns exist in Ads Manager;
    they must not share one row, or the deleted one shows the live one's status."""
    db = FakeDB([{
        "id": "camp-live", "tenant_id": "t1", "platform": "whatsapp",
        "campaign_name": "Astro Whatsapp-WB",
        "external_campaign_id": "120254794740460747",
        "effective_status": "ACTIVE",
    }])

    result = get_or_create_campaign(
        db, tenant_id="t1", platform="whatsapp",
        campaign_name="Astro Whatsapp-WB",
        external_campaign_id="120254601940740747",
    )

    assert result["id"] != "camp-live"
    assert result["external_campaign_id"] == "120254601940740747"
    # The live campaign's id must not have been rewritten.
    live = next(r for r in db.rows if r["id"] == "camp-live")
    assert live["external_campaign_id"] == "120254794740460747"


def test_external_id_match_wins_regardless_of_name():
    db = FakeDB([{
        "id": "camp-1", "tenant_id": "t1", "platform": "whatsapp",
        "campaign_name": "Old Name", "external_campaign_id": "999",
    }])

    result = get_or_create_campaign(
        db, tenant_id="t1", platform="whatsapp",
        campaign_name="Renamed In Meta", external_campaign_id="999",
    )

    assert result["id"] == "camp-1"
    assert result["campaign_name"] == "Renamed In Meta"
    assert len(db.rows) == 1


def test_csv_upload_row_without_an_id_is_adopted_by_name():
    """Upload supplies a name and no external id; the name fallback must survive."""
    db = FakeDB([{
        "id": "camp-csv", "tenant_id": "t1", "platform": "whatsapp",
        "campaign_name": "Diwali Push", "external_campaign_id": None,
    }])

    result = get_or_create_campaign(
        db, tenant_id="t1", platform="whatsapp", campaign_name="Diwali Push",
    )

    assert result["id"] == "camp-csv"
    assert len(db.rows) == 1


def test_unclaimed_name_row_is_linked_to_the_meta_id_that_arrives_later():
    db = FakeDB([{
        "id": "camp-csv", "tenant_id": "t1", "platform": "whatsapp",
        "campaign_name": "Diwali Push", "external_campaign_id": None,
    }])

    result = get_or_create_campaign(
        db, tenant_id="t1", platform="whatsapp",
        campaign_name="Diwali Push", external_campaign_id="12345",
    )

    assert result["id"] == "camp-csv"
    assert result["external_campaign_id"] == "12345"
    assert len(db.rows) == 1
