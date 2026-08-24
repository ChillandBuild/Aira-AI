import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.services.meta_cloud import send_interactive_buttons


@pytest.mark.asyncio
async def test_send_interactive_buttons_rejects_long_title():
    with pytest.raises(ValueError, match="20 characters"):
        await send_interactive_buttons(
            to_number="+919000000000",
            body_text="Pick one",
            buttons=[{"id": "a", "title": "Detailed Consultation"}],  # 21 chars
            tenant_id="tenant-1",
        )


@pytest.mark.asyncio
async def test_send_interactive_buttons_rejects_too_many():
    with pytest.raises(ValueError, match="3 buttons"):
        await send_interactive_buttons(
            to_number="+919000000000",
            body_text="Pick one",
            buttons=[{"id": str(i), "title": f"B{i}"} for i in range(4)],
            tenant_id="tenant-1",
        )


@pytest.mark.asyncio
async def test_send_interactive_buttons_rejects_empty():
    with pytest.raises(ValueError, match="at least one"):
        await send_interactive_buttons(
            to_number="+919000000000",
            body_text="Pick one",
            buttons=[],
            tenant_id="tenant-1",
        )


@pytest.mark.asyncio
async def test_send_interactive_buttons_sends_valid_payload():
    mock_response = MagicMock()
    mock_response.is_success = True
    mock_response.json.return_value = {"messages": [{"id": "wamid.1"}]}

    with patch("httpx.AsyncClient") as MockClient:
        instance = MockClient.return_value.__aenter__.return_value
        instance.post = AsyncMock(return_value=mock_response)
        with patch("app.services.meta_cloud._creds", return_value=("pid-1", "tok-1")):
            result = await send_interactive_buttons(
                to_number="+919000000000",
                body_text="Pick one",
                buttons=[{"id": "basic", "title": "One Question"}],
                tenant_id="tenant-1",
            )

    assert result["messages"][0]["id"] == "wamid.1"
    payload = instance.post.call_args.kwargs["json"]
    assert payload["interactive"]["action"]["buttons"] == [
        {"type": "reply", "reply": {"id": "basic", "title": "One Question"}}
    ]
