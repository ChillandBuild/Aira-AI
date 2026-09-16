from urllib.parse import parse_qs, urlparse

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.telecmi_client import (
    build_recording_url,
    initiate_click2call,
    _implausible_reason,
    _normalize_phone,
)


def test_normalize_phone():
    assert _normalize_phone("9876543210") == "919876543210"
    assert _normalize_phone("+91 98765-43210") == "919876543210"
    assert _normalize_phone("919876543210") == "919876543210"
    assert _normalize_phone("+1 555-0100") == "15550100"


def test_implausible_reason_flags_dropped_digit():
    # A +91 number is 12 digits; 11 means a digit was dropped when the caller ID
    # was typed into settings. TeleCMI accepts the request and fails at dial
    # time, so this is the only place the typo is still traceable.
    assert _implausible_reason("91120320393") is not None
    assert _implausible_reason("911203203937") is None
    assert _implausible_reason("919876543210") is None
    # Out-of-range lengths are flagged regardless of country code.
    assert _implausible_reason("12345") is not None


def test_build_recording_url_matches_play_record_docs():
    # play-record docs: rest.telecmi.com/v2/play?appid=…&secret=…&file=…
    url = build_recording_url(appid="33337312", secret="2e0d-75d8", filename="1650.mp3")
    parts = urlparse(url)
    assert parts.netloc == "rest.telecmi.com"
    assert parts.path == "/v2/play"
    query = parse_qs(parts.query)
    assert query["appid"] == ["33337312"]
    # The parameter is `secret`, not `token` (that's the PIOPIY product's API).
    assert query["secret"] == ["2e0d-75d8"]
    assert "token" not in query
    assert query["file"] == ["1650.mp3"]


def test_build_recording_url_honours_override_and_escapes():
    url = build_recording_url(
        appid="1", secret="a+b/c=", filename="rec 01.mp3", base_url="https://x.test/v9/play"
    )
    assert url.startswith("https://x.test/v9/play?")
    query = parse_qs(urlparse(url).query)
    # Secrets and filenames must survive a round-trip through the query string.
    assert query["secret"] == ["a+b/c="]
    assert query["file"] == ["rec 01.mp3"]


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
