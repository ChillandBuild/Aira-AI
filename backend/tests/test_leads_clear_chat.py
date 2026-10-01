"""Clear Data erases the lead and everything about it, money records included. It used to be
"Clear Chat", which kept the lead row, its score and every paid booking, so a cleared test lead
came back "A · Hot" with half its history (Keerthi, 2026-10-01)."""
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_and_role
from app.main import app
from app.services import lead_wipe

LEAD_ID = "0761bbde-8626-42c3-963e-327f162ca37e"
TENANT = "t-1"


class FakeQuery:
    def __init__(self, db, table):
        self.db, self.table, self.op, self.filters = db, table, None, {}

    def select(self, *_a, **_k):
        self.op = "select"
        return self

    def delete(self):
        self.op = "delete"
        return self

    def eq(self, column, value):
        self.filters[column] = value
        return self

    def maybe_single(self):
        return self

    def execute(self):
        self.db.log.append((self.table, self.op, dict(self.filters)))
        res = MagicMock()
        if self.op == "select" and self.table == "leads":
            res.data = {"id": LEAD_ID} if self.db.lead_exists else None
        elif self.op == "select":
            res.data = self.db.open_links.get(self.table, [])
        else:
            res.data = []
        return res


class FakeDB:
    def __init__(self, lead_exists=True, open_links=None):
        self.lead_exists, self.open_links, self.log = lead_exists, open_links or {}, []

    def table(self, name):
        return FakeQuery(self, name)

    def deletes(self):
        return [(t, f) for t, op, f in self.log if op == "delete"]


@pytest.fixture
def client():
    app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}
    yield TestClient(app)
    app.dependency_overrides.clear()


def _as(role):
    app.dependency_overrides[get_tenant_and_role] = lambda: {"tenant_id": TENANT, "role": role}


@pytest.mark.parametrize("path", ["clear-data", "clear-chat"])
def test_owner_wipes_the_lead_and_every_non_cascading_table(client, path):
    _as("owner")
    db = FakeDB()
    with patch("app.routes.leads.get_supabase", return_value=db):
        res = client.delete(f"/api/v1/leads/{LEAD_ID}/{path}")

    assert res.status_code == 200
    deleted = {t: f for t, f in db.deletes()}
    for table in lead_wipe.NON_CASCADING_TABLES:
        assert deleted[table] == {"lead_id": LEAD_ID, "tenant_id": TENANT}
    assert deleted["leads"] == {"id": LEAD_ID, "tenant_id": TENANT}
    # The lead row goes last: chat_handovers / broadcast_recipients would block it otherwise.
    assert db.deletes()[-1][0] == "leads"


def test_open_payment_links_are_cancelled_before_anything_is_deleted(client):
    _as("owner")
    session = {"id": "s-1", "tenant_id": TENANT, "status": "awaiting_payment"}
    deal = {"id": "d-1", "tenant_id": TENANT, "stage": "awaiting_payment"}
    db = FakeDB(open_links={"intake_sessions": [session], "deals": [deal]})
    cancel_session = AsyncMock(return_value=True)
    cancel_deal = AsyncMock(return_value=True)
    with patch("app.routes.leads.get_supabase", return_value=db), \
         patch.object(lead_wipe, "cancel_session_link", cancel_session), \
         patch.object(lead_wipe, "_cancel_replaced_link", cancel_deal):
        res = client.delete(f"/api/v1/leads/{LEAD_ID}/clear-data")

    assert res.json()["payment_links_cancelled"] == 2
    cancel_session.assert_awaited_once_with(db, session)
    cancel_deal.assert_awaited_once_with(deal, None)
    first_delete = next(i for i, (_t, op, _f) in enumerate(db.log) if op == "delete")
    link_lookups = [i for i, (t, op, _f) in enumerate(db.log) if op == "select" and t in ("intake_sessions", "deals")]
    assert link_lookups and max(link_lookups) < first_delete


def test_a_caller_cannot_clear_data(client):
    _as("caller")
    db = FakeDB()
    with patch("app.routes.leads.get_supabase", return_value=db):
        res = client.delete(f"/api/v1/leads/{LEAD_ID}/clear-data")

    assert res.status_code == 403
    assert db.deletes() == []


def test_404_for_a_lead_in_another_tenant(client):
    _as("owner")
    db = FakeDB(lead_exists=False)
    with patch("app.routes.leads.get_supabase", return_value=db):
        res = client.delete(f"/api/v1/leads/{LEAD_ID}/clear-data")

    assert res.status_code == 404
    assert db.deletes() == []
