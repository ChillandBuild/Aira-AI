"""R2: Razorpay cancelled/expired events only change state when they are about the row's
CURRENT link. We cancel replaced links ourselves, so those echoes (and a late expiry for a
superseded link) must never close a live deal. Rows with no stored link id (pre-212) keep
the old behaviour."""
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes.intake import _handle_deal_payment_event, public_router

app = FastAPI()
app.include_router(public_router, prefix="/api/v1/expert-handoff")
client = TestClient(app)
URL = "/api/v1/expert-handoff/razorpay-webhook"


def _session_event(event, plink_id="plink_old"):
    return {
        "event": event,
        "payload": {"payment_link": {"entity": {
            "id": plink_id, "notes": {"booking_id": "sess-1", "booking_ref": "IN-1"},
        }}},
    }


def _deal_event(plink_id):
    return {"payload": {"payment_link": {"entity": {"id": plink_id, "notes": {"deal_id": "d1"}}}}}


@pytest.fixture
def signed():
    with patch("app.routes.intake.get_session_tenant_id", return_value="t-1"), \
         patch("app.routes.intake.verify_webhook_signature", return_value=True):
        yield


class TestSessionExpiry:
    def test_expiry_of_a_replaced_link_changes_nothing(self, signed):
        with patch("app.routes.intake._current_plink_id", return_value="plink_new"), \
             patch("app.routes.intake.expire_intake_session") as expire:
            res = client.post(URL, json=_session_event("payment_link.expired", "plink_old"))
        assert res.json()["status"] == "ignored"
        expire.assert_not_called()

    def test_expiry_of_the_current_link_still_expires_the_session(self, signed):
        with patch("app.routes.intake._current_plink_id", return_value="plink_new"), \
             patch("app.routes.intake.expire_intake_session", return_value=True) as expire:
            res = client.post(URL, json=_session_event("payment_link.expired", "plink_new"))
        assert res.json()["status"] == "ok"
        expire.assert_called_once_with("sess-1")

    def test_a_session_from_before_link_ids_were_stored_keeps_todays_behaviour(self, signed):
        with patch("app.routes.intake._current_plink_id", return_value=None), \
             patch("app.routes.intake.expire_intake_session", return_value=True) as expire:
            res = client.post(URL, json=_session_event("payment_link.expired", "plink_any"))
        assert res.json()["status"] == "ok"
        expire.assert_called_once()

    def test_an_expiry_event_without_a_link_id_is_ignored_when_the_session_has_one(self, signed):
        body = _session_event("payment_link.expired")
        del body["payload"]["payment_link"]["entity"]["id"]
        with patch("app.routes.intake._current_plink_id", return_value="plink_new"), \
             patch("app.routes.intake.expire_intake_session") as expire:
            res = client.post(URL, json=body)
        assert res.json()["status"] == "ignored"
        expire.assert_not_called()

    def test_an_unreadable_session_row_fails_closed(self, signed):
        with patch("app.routes.intake._current_plink_id", side_effect=RuntimeError("db down")), \
             patch("app.routes.intake.expire_intake_session") as expire:
            res = client.post(URL, json=_session_event("payment_link.expired"))
        assert res.json()["status"] == "ignored"
        expire.assert_not_called()

    def test_the_signature_check_still_runs_first(self):
        with patch("app.routes.intake.get_session_tenant_id", return_value="t-1"), \
             patch("app.routes.intake.verify_webhook_signature", return_value=False), \
             patch("app.routes.intake.expire_intake_session") as expire:
            res = client.post(URL, json=_session_event("payment_link.expired"))
        assert res.status_code == 400
        expire.assert_not_called()


class TestDealEvents:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("event", ["payment_link.expired", "payment_link.cancelled"])
    async def test_event_for_a_replaced_deal_link_does_not_mark_the_deal_lost(self, event):
        with patch("app.routes.intake._current_plink_id", return_value="plink_new"), \
             patch("app.services.deals.expire_deal_link") as expire, \
             patch("app.services.deals.mark_lost") as lost:
            out = await _handle_deal_payment_event(_deal_event("plink_old"), event, "d1", "t1")
        assert out["status"] == "ignored"
        lost.assert_not_called()
        expire.assert_not_called()

    @pytest.mark.asyncio
    async def test_expiry_of_the_current_deal_link_keeps_the_deal_open(self):
        with patch("app.routes.intake._current_plink_id", return_value="plink_new"), \
             patch("app.services.deals.expire_deal_link", return_value=True) as expire, \
             patch("app.services.deals.mark_lost") as lost:
            out = await _handle_deal_payment_event(_deal_event("plink_new"), "payment_link.expired", "d1", "t1")
        assert out["status"] == "ok"
        expire.assert_called_once_with("t1", "d1")
        lost.assert_not_called()

    @pytest.mark.asyncio
    async def test_cancel_of_the_current_deal_link_still_marks_it_lost(self):
        with patch("app.routes.intake._current_plink_id", return_value="plink_new"), \
             patch("app.services.deals.mark_lost", return_value={"deal": {}}) as lost:
            out = await _handle_deal_payment_event(_deal_event("plink_new"), "payment_link.cancelled", "d1", "t1")
        assert out["status"] == "ok"
        lost.assert_called_once_with("t1", "d1", "Payment link cancelled", only_from=("quoted", "awaiting_payment"))

    @pytest.mark.asyncio
    async def test_a_deal_with_no_stored_link_id_keeps_todays_behaviour(self):
        with patch("app.routes.intake._current_plink_id", return_value=None), \
             patch("app.services.deals.mark_lost", return_value={"deal": {}}) as lost:
            await _handle_deal_payment_event(_deal_event("plink_any"), "payment_link.cancelled", "d1", "t1")
        lost.assert_called_once()

    @pytest.mark.asyncio
    async def test_the_lookup_is_tenant_scoped(self):
        with patch("app.routes.intake._current_plink_id", return_value=None) as lookup, \
             patch("app.services.deals.expire_deal_link", return_value=False):
            await _handle_deal_payment_event(_deal_event("p"), "payment_link.expired", "d1", "t1")
        lookup.assert_called_once_with("deals", "d1", "t1")
