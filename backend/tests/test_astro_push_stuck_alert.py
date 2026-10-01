"""A paid question AstroTamil still has not accepted after the retry job has had its go must reach
a human. Before 2026-10-01 the only trace was a log line, so a customer who paid could wait forever."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import astro_bridge
from app.services import intake as ik

TENANT = "eba3ed94-277c-430f-a992-19bbe855e2f4"
SID = "7d2b0cd5-9852-42ef-804c-d4b665607b10"
LEAD = {"id": "L1", "name": "Keerthi", "phone": "+916369781582"}


_CONNECTED = {"astro_bridge_url": "https://astro.example.com", "astro_bridge_api_key": "k"}


@pytest.fixture(autouse=True)
def connected():
    """Alerts are for AstroTamil clients; the one test about everyone else switches this off."""
    with patch.object(astro_bridge, "get_setting", lambda k, fallback=None, tenant_id=None: _CONNECTED.get(k, fallback)):
        yield


def _session(minutes_ago=30, **collected):
    data = {"name": "Keerthi", "gender": "Male", "date_of_birth": "2003-11-19",
            "time_of_birth": "10:30 AM", "place_of_birth": "Neyveli", "question": "job eppo?", **collected}
    paid = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    return {"id": SID, "tenant_id": TENANT, "lead_id": "L1", "collected_data": data,
            "skipped_fields": [], "paid_at": paid.isoformat()}


def _db(already_alerted=False):
    db = MagicMock()
    res = MagicMock()
    res.data = [{"id": "n1"}] if already_alerted else []
    db.table.return_value.select.return_value.eq.return_value.eq.return_value.like.return_value.limit.return_value.execute.return_value = res
    return db


def test_alerts_staff_naming_the_customer_and_the_unusable_detail():
    with patch.object(ik, "notify_pool") as notify:
        sent = ik.alert_astro_push_stuck(_db(), _session(date_of_birth="sometime in the 90s"), LEAD, TENANT)
    assert sent is True
    tenant, kind, title, message = notify.call_args[0][:4]
    assert tenant == TENANT and kind == "intake_astro_push_failed"
    assert "Keerthi" in message and "birth date" in message and SID in message


def test_says_so_when_the_details_are_fine_and_astrotamil_did_not_accept():
    with patch.object(ik, "notify_pool") as notify:
        assert ik.alert_astro_push_stuck(_db(), _session(), LEAD, TENANT) is True
    assert "did not accept" in notify.call_args[0][3]


def test_a_client_without_the_astrotamil_connection_is_never_alerted():
    """The retry job scans every client's paid sessions; only AstroTamil ones ever get a question id."""
    with patch.object(astro_bridge, "get_setting", lambda k, fallback=None, tenant_id=None: fallback), \
         patch.object(ik, "notify_pool") as notify:
        assert ik.alert_astro_push_stuck(_db(), _session(), LEAD, TENANT) is False
    notify.assert_not_called()


def test_a_question_held_only_in_trigger_reason_is_not_called_unusable():
    session = _session()
    session["collected_data"].pop("question")
    session["trigger_reason"] = "job eppo?"
    with patch.object(ik, "notify_pool") as notify:
        ik.alert_astro_push_stuck(_db(), session, LEAD, TENANT)
    assert "did not accept" in notify.call_args[0][3]  # the push would send it, so it is not the cause


def test_a_payment_from_the_last_few_minutes_is_left_to_the_retry_job():
    with patch.object(ik, "notify_pool") as notify:
        assert ik.alert_astro_push_stuck(_db(), _session(minutes_ago=2), LEAD, TENANT) is False
    notify.assert_not_called()


def test_one_alert_per_session_not_one_per_retry():
    with patch.object(ik, "notify_pool") as notify:
        assert ik.alert_astro_push_stuck(_db(already_alerted=True), _session(), LEAD, TENANT) is False
    notify.assert_not_called()


@pytest.mark.asyncio
async def test_the_retry_job_raises_the_alert_when_the_push_still_fails():
    row = {**_session(), "trigger_reason": "q", "amount_paise": 100}
    db = MagicMock()
    sessions = MagicMock()
    sessions.data = [row]
    db.table.return_value.select.return_value.eq.return_value.is_.return_value.gte.return_value.limit.return_value.execute.return_value = sessions
    lead = MagicMock()
    lead.data = LEAD
    db.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = lead
    with patch("app.services.astro_bridge.push_consultation", new=AsyncMock(return_value=None)), \
         patch.object(ik, "alert_astro_push_stuck") as alert:
        pushed = await ik.reconcile_pending_astro_pushes(db=db)
    assert pushed == 0
    alert.assert_called_once()
    assert alert.call_args[0][1]["id"] == SID
