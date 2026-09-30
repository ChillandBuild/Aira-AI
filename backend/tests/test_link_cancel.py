"""R2 money safety: replacing a payment link cancels the old one on Razorpay (best effort,
only after the new link is stored), and the session records which Razorpay link is current."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services import intake

TENANT = "tenant-1"


def _in(**delta) -> str:
    return (datetime.now(timezone.utc) + timedelta(**delta)).isoformat()


def _session(**over) -> dict:
    return {
        "id": "s1", "tenant_id": TENANT, "lead_id": "lead-1", "status": "awaiting_payment",
        "payment_link": "https://rzp.io/old", "razorpay_payment_link_id": "plink_old",
        "payment_link_expires_at": _in(hours=10), **over,
    }


class Recorder:
    """Records cancel calls (and the order relative to other events)."""

    def __init__(self, result=True):
        self.calls: list[tuple] = []
        self.events: list[str] = []
        self.result = result

    async def cancel(self, plink_id, tenant_id=None):
        self.calls.append((plink_id, tenant_id))
        self.events.append("cancel")
        return self.result


@pytest.fixture
def rec():
    r = Recorder()
    with patch.object(intake, "cancel_payment_link", r.cancel):
        yield r


class TestCancelSessionLink:
    @pytest.mark.asyncio
    async def test_cancels_the_stored_plink_for_the_sessions_tenant(self, rec):
        assert await intake.cancel_session_link(object(), _session()) is True
        assert rec.calls == [("plink_old", TENANT)]

    @pytest.mark.asyncio
    async def test_skips_when_the_replacement_is_the_same_link(self, rec):
        # Razorpay replays the original link for a repeated idempotency key.
        assert await intake.cancel_session_link(object(), _session(), keep_plink_id="plink_old") is False
        assert rec.calls == []

    @pytest.mark.asyncio
    async def test_skips_sessions_with_no_stored_plink_or_no_outstanding_link(self, rec):
        await intake.cancel_session_link(object(), _session(razorpay_payment_link_id=None))
        await intake.cancel_session_link(object(), _session(payment_link=None))
        assert rec.calls == []

    @pytest.mark.asyncio
    async def test_skips_a_link_that_already_expired(self, rec):
        await intake.cancel_session_link(object(), _session(payment_link_expires_at=_in(hours=-1)))
        assert rec.calls == []

    @pytest.mark.asyncio
    async def test_a_failed_cancel_is_reported_not_raised(self):
        r = Recorder(result=False)
        with patch.object(intake, "cancel_payment_link", r.cancel):
            assert await intake.cancel_session_link(object(), _session()) is False

    @pytest.mark.asyncio
    async def test_reads_the_plink_from_the_db_when_the_row_was_a_partial_select(self, rec):
        class Db:
            def table(self, name):
                return self

            def __getattr__(self, name):
                return lambda *a, **k: self

            def execute(self):
                return SimpleNamespace(data={"razorpay_payment_link_id": "plink_db"})

        partial = {"id": "s1", "tenant_id": TENANT, "payment_link": "u", "payment_link_expires_at": None}
        await intake.cancel_session_link(Db(), partial)
        assert rec.calls == [("plink_db", TENANT)]


class TestLinkStorePatch:
    def test_carries_the_razorpay_id_url_and_expiry(self):
        link = {"payment_link_url": "u", "razorpay_payment_link_id": "plink_new", "payment_link_expires_at": "e"}
        assert intake.link_store_patch(link) == {
            "payment_link": "u", "razorpay_payment_link_id": "plink_new", "payment_link_expires_at": "e",
        }


class TestLegacyIdempotencyKey:
    def test_first_link_keeps_the_historic_key(self):
        assert intake.legacy_link_key({"id": "s1"}) == "booking:s1:payment_link"

    def test_a_relink_after_a_cancel_gets_a_new_key(self):
        key = intake.legacy_link_key({"id": "s1", "razorpay_payment_link_id": "plink_old"})
        assert key != "booking:s1:payment_link" and "plink_old" in key and key.endswith(":payment_link")


class TestChangeSessionPackage:
    @pytest.mark.asyncio
    async def test_repointing_cancels_the_old_plink_after_the_update(self, rec):
        events = rec.events

        class Chain:
            def __init__(self, op=None):
                self.op = op

            def __getattr__(self, name):
                def call(*a, **k):
                    if name == "update":
                        return Chain("update")
                    return self
                return call

            def execute(self):
                if self.op == "update":
                    events.append("update")
                    return SimpleNamespace(data=[{"id": "s1"}])
                return SimpleNamespace(data=_session(package_key="a"))

        class Db:
            def table(self, name):
                return Chain()

        config = {"packages": [{"key": "b", "name": "B", "amount_paise": 9900}]}
        with patch.object(intake, "get_intake_config", return_value=config), patch.object(intake, "_sync_deal"):
            out = await intake.change_session_package("s1", TENANT, "b", db=Db())
        assert out["package_key"] == "b"
        assert rec.calls == [("plink_old", TENANT)]
        assert events == ["update", "cancel"]
