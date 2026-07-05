import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.routes import webhook


def _db(captured_messages: list[dict]):
    db = MagicMock()

    def table_selector(name):
        table = MagicMock()
        if name == "messages":
            def _insert(row):
                captured_messages.append(row)
                result = MagicMock()
                result.execute.return_value.data = [{"id": "message-1"}]
                return result
            table.insert.side_effect = _insert
        return table

    db.table.side_effect = table_selector
    return db


@pytest.mark.asyncio
async def test_audio_background_transcribes_inserts_and_routes_reply():
    captured_messages: list[dict] = []
    db = _db(captured_messages)

    with patch("app.db.supabase.get_supabase", return_value=db), \
         patch("app.services.conversation_state.get_or_create_state", return_value={"message_count": 0}), \
         patch.object(webhook, "_transcribe_whatsapp_audio", new=AsyncMock(return_value=("I need a flat near Andheri", "audio/ogg")), create=True) as transcribe, \
         patch("app.services.notify.notify_assigned_caller_of_reply") as notify, \
         patch("app.services.context_builder.build_scorer_context", return_value="ctx") as build_ctx, \
         patch("app.services.ai_reply.generate_reply", new=AsyncMock()) as generate_reply:
        await webhook._process_inbound_message_background(
            lead_id="lead-1",
            tenant_id="tenant-1",
            phone="+919999999999",
            body="",
            msg_type="audio",
            meta_phone_number_id="phone-number-1",
            meta_media_id="media-1",
        )

    transcribe.assert_awaited_once_with("media-1", "tenant-1")
    assert captured_messages == [{
        "lead_id": "lead-1",
        "direction": "inbound",
        "channel": "whatsapp",
        "content": "I need a flat near Andheri",
        "is_ai_generated": False,
        "meta_message_id": "media-1",
        "tenant_id": "tenant-1",
        "media_url": "meta:media-1",
        "media_type": "audio",
        "media_mime_type": "audio/ogg",
    }]
    notify.assert_called_once_with("lead-1", "tenant-1", db=db)
    build_ctx.assert_called_once_with("lead-1", db)
    generate_reply.assert_awaited_once_with(
        lead_id="lead-1",
        message="I need a flat near Andheri",
        phone="+919999999999",
        context_block="ctx",
        phone_number_id="phone-number-1",
    )
