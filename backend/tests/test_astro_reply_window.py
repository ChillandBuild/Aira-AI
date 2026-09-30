"""WhatsApp only allows free-form text within 24h of the customer's last message.
An astrologer who answers later must still reach them, so the "answer ready"
nudge falls back to the pre-approved astro_reply_ready template. Ported from
Ansar's PR #22 (41adb305) onto the intake module."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import intake as ik

SID = "11111111-2222-3333-4444-555555555555"
TENANT = "0f897915-2d34-4b67-8d69-f83f52e4fb6c"
PHONE = "+919345679286"


def _ago(hours: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


def _db(last_inbound_at):
    db = MagicMock()
    writes = []

    def table(name):
        t = MagicMock()
        if name == "intake_sessions":
            row = MagicMock()
            row.data = {"id": SID, "lead_id": "L1", "tenant_id": TENANT, "astro_last_reply_id": 4}
            t.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = row

            def update(body):
                writes.append(body)
                chain = MagicMock()
                claimed = MagicMock()
                claimed.data = [{"id": SID}]
                chain.eq.return_value.eq.return_value.or_.return_value.execute.return_value = claimed
                chain.eq.return_value.eq.return_value.eq.return_value.execute.return_value = claimed
                chain.eq.return_value.eq.return_value.execute.return_value = claimed
                return chain
            t.update.side_effect = update
        elif name == "leads":
            row = MagicMock()
            row.data = {"id": "L1", "phone": PHONE, "last_inbound_at": last_inbound_at}
            t.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = row
        return t

    cache = {}
    db.table.side_effect = lambda n: cache.setdefault(n, table(n))
    db._writes = writes
    return db


async def _deliver(db, *, text_mid="wamid.text", template=None):
    send = AsyncMock(return_value=text_mid)
    template = template or AsyncMock(return_value={"messages": [{"id": "wamid.tpl"}]})
    with patch("app.services.ai_reply.send_whatsapp", new=send), \
         patch("app.services.meta_cloud.send_template_message", new=template), \
         patch("app.config_dynamic.get_setting", side_effect=lambda key, fallback=None, tenant_id=None: fallback), \
         patch.object(ik, "_astro_phone_number_id", return_value="pn1"), \
         patch.object(ik, "_log_astro_message") as logged, \
         patch.object(ik, "notify_pool") as alerted, \
         patch.object(ik, "resolve_intake_session"), \
         patch.object(ik, "_compose_reply_nudge", new=AsyncMock(return_value="Answer ready\nhttps://x/app")):
        out = await ik.deliver_astro_reply({"external_ref": SID, "reply_id": 9}, TENANT, db=db)
    return out, send, template, logged, alerted


@pytest.mark.asyncio
async def test_inside_the_window_the_nudge_goes_as_text():
    out, send, template, logged, _ = await _deliver(_db(_ago(2)))
    assert out == {"ok": True, "nudged": True, "via": "text"}
    send.assert_awaited_once()
    template.assert_not_awaited()
    assert logged.call_args[0][3:] == ("Answer ready\nhttps://x/app", "wamid.text", "sent")


@pytest.mark.asyncio
async def test_after_24h_the_template_is_sent_instead_of_text():
    """Priya paid Monday 10am, the astrologer answered Tuesday 3pm (29h later).
    Free-form text would be refused by Meta; the approved template is not."""
    out, send, template, logged, _ = await _deliver(_db(_ago(29)))
    assert out == {"ok": True, "nudged": True, "via": "template"}
    send.assert_not_awaited()
    template.assert_awaited_once()
    assert template.await_args.kwargs["template_name"] == "astro_reply_ready"
    assert template.await_args.kwargs["to_number"] == PHONE
    assert logged.call_args[0][4:] == ("wamid.tpl", "sent")


@pytest.mark.asyncio
async def test_a_lead_who_never_messaged_is_outside_the_window():
    out, send, template, _, _ = await _deliver(_db(None))
    assert out["via"] == "template"
    send.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_failed_text_falls_back_to_the_template():
    out, send, template, _, _ = await _deliver(_db(_ago(2)), text_mid=None)
    assert out == {"ok": True, "nudged": True, "via": "template"}
    send.assert_awaited_once()
    template.assert_awaited_once()


@pytest.mark.asyncio
async def test_total_failure_is_logged_alerted_and_retryable():
    """The customer must not silently miss their answer: the failed nudge shows
    in the chat thread, staff are alerted, and the claim is released so a
    re-push from the expert platform can try again."""
    db = _db(_ago(29))
    failing = AsyncMock(side_effect=RuntimeError("template not approved"))
    out, _, _, logged, alerted = await _deliver(db, template=failing)
    assert out == {"ok": True, "nudged": False, "reason": "send_failed"}
    assert logged.call_args[0][4:] == (None, "failed")
    alerted.assert_called_once()
    assert PHONE in alerted.call_args[0][3]
    assert db._writes[-1] == {"astro_last_reply_id": 4}, "claim rolls back to the prior reply id"


def test_the_log_row_carries_the_delivery_status():
    db = MagicMock()
    ik._log_astro_message(db, "L1", TENANT, "hi", None, "failed")
    row = db.table.return_value.insert.call_args[0][0]
    assert row["delivery_status"] == "failed"
    assert row["reply_source"] == "expert_handoff"


@pytest.mark.parametrize("value,expected", [
    (None, False),
    ("", False),
    ("not a date", False),
    (_ago(23.5), True),
    (_ago(24.5), False),
    ((datetime.utcnow() - timedelta(hours=1)).isoformat(), True),  # naive = UTC
    (_ago(1).replace("+00:00", "Z"), True),
])
def test_window_check(value, expected):
    assert ik._within_whatsapp_window(value) is expected


# --- the nudge wording ---------------------------------------------------------


@pytest.mark.asyncio
async def test_the_nudge_is_the_ai_line_followed_by_the_app_link():
    compose = AsyncMock(return_value="Unga kelvikku astrologer pathil sollitaanga.")
    with patch.object(ik, "get_intake_config", return_value={"service_noun": "reading"}), \
         patch.object(ik, "resolve_language_mode", return_value="tanglish"), \
         patch.object(ik, "gather_context", new=AsyncMock(return_value=([], ""))), \
         patch.object(ik, "collector_identity", return_value=""), \
         patch.object(ik, "compose_line", new=compose), \
         patch("app.services.ai_reply.business_app_link", return_value="https://astrotamil.co.in/app/questions"):
        text = await ik._compose_reply_nudge("L1", TENANT, PHONE, MagicMock())
    assert text == "Unga kelvikku astrologer pathil sollitaanga.\nhttps://astrotamil.co.in/app/questions"
    assert compose.await_args.kwargs["field_label"] == "reading"
