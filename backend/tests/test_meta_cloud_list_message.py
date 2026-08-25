import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.services.meta_cloud import send_list_message


@pytest.mark.asyncio
async def test_send_list_message_rejects_more_than_ten_rows():
    sections = [{"rows": [{"id": str(i), "title": f"Row {i}"} for i in range(11)]}]
    with pytest.raises(ValueError, match="10 rows"):
        await send_list_message("+911234567890", "body", "Choose", sections, tenant_id="tenant-1")


@pytest.mark.asyncio
async def test_send_list_message_rejects_no_rows():
    with pytest.raises(ValueError, match="at least one row"):
        await send_list_message("+911234567890", "body", "Choose", [], tenant_id="tenant-1")


@pytest.mark.asyncio
async def test_send_list_message_rejects_a_row_title_over_24_chars():
    sections = [{"rows": [{"id": "1", "title": "A Row Title Well Over Twenty Four Characters"}]}]
    with pytest.raises(ValueError, match="24 characters"):
        await send_list_message("+911234567890", "body", "Choose", sections, tenant_id="tenant-1")


@pytest.mark.asyncio
async def test_send_list_message_rejects_a_row_description_over_72_chars():
    long_desc = "x" * 73
    sections = [{"rows": [{"id": "1", "title": "Row", "description": long_desc}]}]
    with pytest.raises(ValueError, match="72 characters"):
        await send_list_message("+911234567890", "body", "Choose", sections, tenant_id="tenant-1")


@pytest.mark.asyncio
async def test_send_list_message_rejects_a_section_title_over_24_chars():
    sections = [{"title": "A Section Title Well Over Twenty Four Chars", "rows": [{"id": "1", "title": "Row"}]}]
    with pytest.raises(ValueError, match="24 characters"):
        await send_list_message("+911234567890", "body", "Choose", sections, tenant_id="tenant-1")


@pytest.mark.asyncio
async def test_send_list_message_rejects_a_button_label_over_20_chars():
    sections = [{"rows": [{"id": "1", "title": "Row"}]}]
    with pytest.raises(ValueError, match="20 characters"):
        await send_list_message("+911234567890", "body", "A Button Label Over Twenty Chars", sections, tenant_id="tenant-1")


@pytest.mark.asyncio
async def test_send_list_message_sends_valid_payload():
    mock_response = MagicMock()
    mock_response.is_success = True
    mock_response.json.return_value = {"messages": [{"id": "wamid.2"}]}

    sections = [{"rows": [{"id": "1", "title": "Row"}]}]
    with patch("httpx.AsyncClient") as MockClient:
        instance = MockClient.return_value.__aenter__.return_value
        instance.post = AsyncMock(return_value=mock_response)
        with patch("app.services.meta_cloud._creds", return_value=("pid-1", "tok-1")):
            result = await send_list_message("+911234567890", "body", "Choose", sections, tenant_id="tenant-1")

    assert result["messages"][0]["id"] == "wamid.2"
    payload = instance.post.call_args.kwargs["json"]
    assert payload["interactive"]["action"]["sections"] == sections
