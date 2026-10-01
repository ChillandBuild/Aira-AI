"""The Intake table shows whether a paid question reached AstroTamil, but only for clients that
have the AstroTamil connection. Everyone else gets the same rows as before, with no AstroTamil keys."""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_and_role
from app.main import app
from app.services import astro_bridge

_CONNECTED = {"astro_bridge_url": "https://astro.example.com", "astro_bridge_api_key": "k"}
SENT = {"id": "s-1", "status": "paid", "created_at": "2026-10-01T05:00:00Z",
        "astro_question_id": 5856, "astro_horoscope_id": "HOR-RM8CPTET"}
UNSENT = {"id": "s-2", "status": "paid", "created_at": "2026-10-01T04:00:00Z",
          "astro_question_id": None, "astro_horoscope_id": None}


@pytest.fixture
def client():
    app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}
    app.dependency_overrides[get_tenant_and_role] = lambda: {"tenant_id": "t-1", "role": "owner", "permissions": []}
    yield TestClient(app)
    app.dependency_overrides.clear()


def _list(client, rows):
    db = MagicMock()
    res = MagicMock()
    res.data = [dict(r) for r in rows]
    db.table.return_value.select.return_value.eq.return_value.in_.return_value.order.return_value.order.return_value.limit.return_value.execute.return_value = res
    with patch("app.routes.intake.get_supabase", return_value=db):
        return client.get("/api/v1/intake/sessions?status=all").json()["data"]


def test_a_connected_client_sees_whether_each_question_reached_astrotamil(client):
    with patch.object(astro_bridge, "get_setting", lambda k, fallback=None, tenant_id=None: _CONNECTED.get(k, fallback)):
        sent, unsent = _list(client, [SENT, UNSENT])
    assert sent["astro"] == {"sent": True, "question_id": 5856, "horoscope_id": "HOR-RM8CPTET"}
    assert unsent["astro"] == {"sent": False, "question_id": None, "horoscope_id": None}
    assert "astro_question_id" not in sent  # one shape, not two


def test_a_client_without_the_connection_gets_no_astrotamil_data_at_all(client):
    rows = _list(client, [SENT, UNSENT])
    assert all("astro" not in r and "astro_question_id" not in r and "astro_horoscope_id" not in r for r in rows)
    assert [r["id"] for r in rows] == ["s-1", "s-2"]


RESOLVED = {"id": "s-3", "status": "resolved", "created_at": "2026-10-01T03:00:00Z",
            "astro_question_id": 5856, "astro_horoscope_id": "HOR-RM8CPTET"}


def _statuses_asked(client, status, connected):
    """The status list the route filters on, for one request."""
    db = MagicMock()
    res = MagicMock()
    res.data = []
    chain = db.table.return_value.select.return_value.eq.return_value
    chain.in_.return_value.order.return_value.order.return_value.limit.return_value.execute.return_value = res
    setting = (lambda k, fallback=None, tenant_id=None: _CONNECTED.get(k, fallback)) if connected else (lambda k, fallback=None, tenant_id=None: fallback)
    with patch("app.routes.intake.get_supabase", return_value=db), patch.object(astro_bridge, "get_setting", setting):
        resp = client.get(f"/api/v1/intake/sessions?status={status}")
    asked = chain.in_.call_args.args[1] if chain.in_.called else None
    return resp, asked


def test_a_connected_client_sees_resolved_rows_in_all_and_in_their_own_tab(client):
    resp, asked = _statuses_asked(client, "all", connected=True)
    assert asked == ["awaiting_payment", "paid", "resolved"] and resp.json()["astro_connected"] is True
    _, asked = _statuses_asked(client, "resolved", connected=True)
    assert asked == ["resolved"]


def test_a_client_without_the_connection_never_gets_resolved_rows_or_a_resolved_tab(client):
    resp, asked = _statuses_asked(client, "all", connected=False)
    assert asked == ["awaiting_payment", "paid"] and "astro_connected" not in resp.json()
    resp, _ = _statuses_asked(client, "resolved", connected=False)
    assert resp.status_code == 400


def test_there_is_no_manual_resolve_endpoint_any_more(client):
    assert client.patch("/api/v1/intake/sessions/s-1/resolve").status_code in (404, 405)
