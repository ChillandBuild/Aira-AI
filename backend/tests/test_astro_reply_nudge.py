"""The astrologer's answer is never sent over WhatsApp. The customer gets a
nudge into the app instead, and reads the answer there."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import intake as ik

SID = "11111111-2222-3333-4444-555555555555"
TENANT = "0f897915-2d34-4b67-8d69-f83f52e4fb6c"
PHONE = "+919345679286"
ANSWER = "Saturn is transiting your seventh house, so marriage is likely after..."


def _db():
    db = MagicMock()
    writes = []

    def table(name):
        t = MagicMock()
        if name == "intake_sessions":
            row = MagicMock()
            row.data = {"id": SID, "lead_id": "L1", "tenant_id": TENANT, "astro_last_reply_id": None}
            t.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = row

            def update(body):
                writes.append(body)
                chain = MagicMock()
                claimed = MagicMock()
                claimed.data = [{"id": SID}]
                chain.eq.return_value.eq.return_value.or_.return_value.execute.return_value = claimed
                chain.eq.return_value.eq.return_value.execute.return_value = claimed
                return chain
            t.update.side_effect = update
        elif name == "leads":
            row = MagicMock()
            row.data = {"id": "L1", "phone": PHONE}
            t.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = row
        return t

    cache = {}
    db.table.side_effect = lambda n: cache.setdefault(n, table(n))
    db._writes = writes
    return db


async def _deliver(db, send, nudge="Your answer is ready."):
    with patch("app.services.ai_reply.send_whatsapp", new=send), \
         patch.object(ik, "_astro_phone_number_id", return_value="pn1"), \
         patch.object(ik, "_log_astro_message") as logged, \
         patch.object(ik, "_compose_reply_nudge", new=AsyncMock(return_value=nudge)):
        out = await ik.deliver_astro_reply(
            {
                "external_ref": SID,
                "reply_id": 9,
                "reply_text": ANSWER,
                "reply_image_url": "https://astro.example.com/chart.png",
                "reply_voice_url": "https://astro.example.com/reading.mp3",
            },
            TENANT,
            db=db,
        )
    return out, logged


@pytest.mark.asyncio
async def test_the_customer_never_receives_the_answer_itself():
    """The whole point of the change: the reading lives in the app, and pushing
    it to WhatsApp would defeat the redirect."""
    send = AsyncMock(return_value="wamid.1")
    out, _ = await _deliver(_db(), send)
    assert out["nudged"] is True
    send.assert_awaited_once()
    sent_text = send.await_args[0][1]
    assert ANSWER not in sent_text
    assert sent_text == "Your answer is ready."


@pytest.mark.asyncio
async def test_the_image_and_voice_are_not_sent_either():
    send = AsyncMock(return_value="wamid.1")
    await _deliver(_db(), send)
    assert send.await_count == 1, "exactly one message: the nudge"
    assert "chart.png" not in send.await_args[0][1]
    assert "reading.mp3" not in send.await_args[0][1]


@pytest.mark.asyncio
async def test_the_answer_is_archived_for_support_but_not_logged_as_a_message():
    """Support needs to see what the astrologer wrote when a customer says they
    can't find it in the app — but `messages` is what the customer received."""
    db = _db()
    send = AsyncMock(return_value="wamid.1")
    _, logged = await _deliver(db, send)
    assert {"astro_last_reply_text": ANSWER} in db._writes
    logged.assert_called_once()
    assert logged.call_args[0][3] == "Your answer is ready."


@pytest.mark.asyncio
async def test_a_reply_with_no_text_still_nudges():
    """An astrologer who answers with only a voice note still triggers the
    redirect — the customer has an answer waiting either way."""
    db = _db()
    send = AsyncMock(return_value="wamid.1")
    with patch("app.services.ai_reply.send_whatsapp", new=send), \
         patch.object(ik, "_astro_phone_number_id", return_value="pn1"), \
         patch.object(ik, "_log_astro_message"), \
         patch.object(ik, "_compose_reply_nudge", new=AsyncMock(return_value="ready")):
        out = await ik.deliver_astro_reply(
            {"external_ref": SID, "reply_id": 9, "reply_voice_url": "https://x/r.mp3"},
            TENANT, db=db,
        )
    assert out["nudged"] is True
    assert not [w for w in db._writes if "astro_last_reply_text" in w]


# --- the nudge copy itself -------------------------------------------------


def _nudge_patches(link, line="Your answer is ready."):
    return [
        patch.object(ik, "get_intake_config", return_value={"service_noun": "reading"}),
        patch.object(ik, "resolve_language_mode", return_value="english"),
        patch.object(ik, "gather_context", new=AsyncMock(return_value=([], ""))),
        patch.object(ik, "collector_identity", return_value=""),
        patch.object(ik, "compose_line", new=AsyncMock(return_value=line)),
        patch("app.config_dynamic.get_setting", return_value=link),
    ]


async def _compose(link, line="Your answer is ready."):
    patches = _nudge_patches(link, line)
    for p in patches:
        p.start()
    try:
        return await ik._compose_reply_nudge("L1", TENANT, PHONE, MagicMock())
    finally:
        for p in patches:
            p.stop()


@pytest.mark.asyncio
async def test_the_link_is_appended_in_code_not_written_by_the_model():
    """A model that invents a download URL sends a paying customer nowhere —
    the same lesson as commit 24494b3d on the intake offer message."""
    text = await _compose("https://astrotamil.co.in/app/consultation/")
    assert text == "Your answer is ready.\nhttps://astrotamil.co.in/app/consultation/"


@pytest.mark.asyncio
async def test_a_missing_app_link_still_tells_them_but_logs_an_error():
    """Better than silence, but they have no way to reach the answer — that is a
    configuration error and must be loud in the logs."""
    with patch.object(ik.logger, "error") as log_error:
        text = await _compose(None)
    assert text == "Your answer is ready."
    assert log_error.called
    assert "app_download_link" in log_error.call_args[0][0]


@pytest.mark.asyncio
async def test_the_copy_is_asked_for_in_the_tenants_own_service_noun():
    compose = AsyncMock(return_value="Your answer is ready.")
    patches = [p for p in _nudge_patches("https://x/app") if p.attribute != "compose_line"]
    patches.append(patch.object(ik, "compose_line", new=compose))
    for p in patches:
        p.start()
    try:
        await ik._compose_reply_nudge("L1", TENANT, PHONE, MagicMock())
    finally:
        for p in patches:
            p.stop()
    assert compose.await_args[0][0] == "reply_ready"
    assert compose.await_args[1]["field_label"] == "reading"
