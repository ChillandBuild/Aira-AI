import pytest
from unittest.mock import MagicMock, AsyncMock, patch


def _db():
    db = MagicMock()
    t = MagicMock()
    t.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {"name": "Asha", "tenant_id": "t1"}
    ]
    db.table.return_value = t
    return db


_THREAD = [
    {"direction": "outbound", "content": "The property is 4.7 km from the festival ground."},
    {"direction": "inbound", "content": "How far is the property from the music fest?"},
]


@pytest.mark.asyncio
async def test_returns_trimmed_single_line():
    from app.services import ai_reply as ar
    with patch.object(ar, "_recent_thread", return_value=_THREAD), \
         patch.object(ar, "_llm_complete", new=AsyncMock(return_value="  Happy to help \n with the cycle rental if you need it.  ")):
        out = await ar.generate_silence_nudge("lead-1", db=_db())
    assert out == "Happy to help with the cycle rental if you need it."


@pytest.mark.asyncio
async def test_truncates_to_160_chars():
    from app.services import ai_reply as ar
    with patch.object(ar, "_recent_thread", return_value=_THREAD), \
         patch.object(ar, "_llm_complete", new=AsyncMock(return_value="x" * 400)):
        out = await ar.generate_silence_nudge("lead-1", db=_db())
    assert len(out) == 160


@pytest.mark.asyncio
async def test_falls_back_when_llm_raises():
    from app.services import ai_reply as ar
    from app.services.silence_nudge import SILENCE_NUDGE_FALLBACK
    with patch.object(ar, "_recent_thread", return_value=_THREAD), \
         patch.object(ar, "_llm_complete", new=AsyncMock(side_effect=RuntimeError("boom"))):
        out = await ar.generate_silence_nudge("lead-1", db=_db())
    assert out == SILENCE_NUDGE_FALLBACK


@pytest.mark.asyncio
async def test_falls_back_when_llm_returns_blank():
    from app.services import ai_reply as ar
    from app.services.silence_nudge import SILENCE_NUDGE_FALLBACK
    with patch.object(ar, "_recent_thread", return_value=_THREAD), \
         patch.object(ar, "_llm_complete", new=AsyncMock(return_value="   \n  ")):
        out = await ar.generate_silence_nudge("lead-1", db=_db())
    assert out == SILENCE_NUDGE_FALLBACK


@pytest.mark.asyncio
async def test_prompt_bans_links_and_carries_thread():
    from app.services import ai_reply as ar
    spy = AsyncMock(return_value="ok")
    with patch.object(ar, "_recent_thread", return_value=_THREAD), \
         patch.object(ar, "_llm_complete", new=spy):
        await ar.generate_silence_nudge("lead-1", db=_db())
    prompt = spy.await_args.args[0]
    assert "music fest" in prompt           # thread history reached the model
    assert "NEVER include links" in prompt  # the leak ban is present
    assert spy.await_args.kwargs["max_tokens"] == 60


@pytest.mark.asyncio
async def test_empty_thread_still_produces_a_prompt():
    from app.services import ai_reply as ar
    spy = AsyncMock(return_value="ok")
    with patch.object(ar, "_recent_thread", return_value=[]), \
         patch.object(ar, "_llm_complete", new=spy):
        out = await ar.generate_silence_nudge("lead-1", db=_db())
    assert out == "ok"
    assert "No prior conversation history available." in spy.await_args.args[0]
