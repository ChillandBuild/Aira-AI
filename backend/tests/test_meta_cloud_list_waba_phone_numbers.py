import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.services.meta_cloud import list_waba_phone_numbers


@pytest.mark.asyncio
async def test_list_waba_phone_numbers_single_page():
    mock_response = MagicMock()
    mock_response.is_success = True
    mock_response.json.return_value = {
        "data": [
            {
                "id": "111",
                "display_phone_number": "+1 555-0100",
                "verified_name": "Aira Main",
                "quality_rating": "GREEN",
                "messaging_limit_tier": "TIER_1000",
            },
        ],
        "paging": {},
    }
    with patch("httpx.AsyncClient") as MockClient:
        instance = MockClient.return_value.__aenter__.return_value
        instance.get = AsyncMock(return_value=mock_response)
        with patch("app.services.meta_cloud.get_setting", return_value="test_token"):
            result = await list_waba_phone_numbers(waba_id="waba-1", tenant_id="tenant-1")

    assert len(result) == 1
    assert result[0]["id"] == "111"
    assert result[0]["display_phone_number"] == "+1 555-0100"


@pytest.mark.asyncio
async def test_list_waba_phone_numbers_paginates():
    page1 = MagicMock()
    page1.is_success = True
    page1.json.return_value = {
        "data": [{"id": "111", "display_phone_number": "+15550100"}],
        "paging": {"next": "https://graph.facebook.com/v21.0/waba-1/phone_numbers?after=CURSOR"},
    }
    page2 = MagicMock()
    page2.is_success = True
    page2.json.return_value = {
        "data": [{"id": "222", "display_phone_number": "+15550200"}],
        "paging": {},
    }
    with patch("httpx.AsyncClient") as MockClient:
        instance = MockClient.return_value.__aenter__.return_value
        instance.get = AsyncMock(side_effect=[page1, page2])
        with patch("app.services.meta_cloud.get_setting", return_value="test_token"):
            result = await list_waba_phone_numbers(waba_id="waba-1", tenant_id="tenant-1")

    assert [n["id"] for n in result] == ["111", "222"]


@pytest.mark.asyncio
async def test_list_waba_phone_numbers_stops_on_meta_error():
    mock_response = MagicMock()
    mock_response.is_success = False
    mock_response.status_code = 400
    mock_response.text = '{"error": {"message": "Invalid waba"}}'
    with patch("httpx.AsyncClient") as MockClient:
        instance = MockClient.return_value.__aenter__.return_value
        instance.get = AsyncMock(return_value=mock_response)
        with patch("app.services.meta_cloud.get_setting", return_value="test_token"):
            result = await list_waba_phone_numbers(waba_id="waba-1", tenant_id="tenant-1")

    assert result == []


if __name__ == "__main__":
    unittest.main()
