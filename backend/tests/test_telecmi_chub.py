import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.telecmi_client import initiate_click2call, _normalize_phone


def test_normalize_phone():
    assert _normalize_phone("9876543210") == "919876543210"
    assert _normalize_phone("+91 98765-43210") == "919876543210"
    assert _normalize_phone("919876543210") == "919876543210"
    assert _normalize_phone("+1 555-0100") == "15550100"


@pytest.mark.asyncio
async def test_initiate_click2call_success():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "code": 200,
        "msg": "Call initiated",
        "request_id": "test-req-12345",
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp) as mock_post:
        res = await initiate_click2call(
            agent_id="agent_101",
            secret="test-app-secret",
            to="9876543210",
            callerid="9876500000",
            custom="log_abc123",
        )

        assert res["code"] == 200
        assert res["request_id"] == "test-req-12345"

        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        payload = kwargs["json"]
        assert payload["user_id"] == "agent_101"
        assert payload["secret"] == "test-app-secret"
        assert payload["to"] == 919876543210
        assert payload["callerid"] == 919876500000
        assert payload["webrtc"] is False
        assert payload["followme"] is True
        assert payload["extra_params"] == {"call_log_id": "log_abc123"}


@pytest.mark.asyncio
async def test_initiate_click2call_invalid_secret():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "code": 407,
        "msg": "invalid app secret",
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
        with pytest.raises(RuntimeError, match="Invalid TeleCMI App Secret"):
            await initiate_click2call(
                agent_id="agent_101",
                secret="wrong-secret",
                to="9876543210",
                callerid="9876500000",
            )


@pytest.mark.asyncio
async def test_initiate_click2call_invalid_user_id():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "code": 404,
        "msg": "invalid user_id",
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
        with pytest.raises(RuntimeError, match="Invalid TeleCMI User ID 'agent_unknown'"):
            await initiate_click2call(
                agent_id="agent_unknown",
                secret="test-secret",
                to="9876543210",
                callerid="9876500000",
            )
