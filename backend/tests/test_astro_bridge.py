import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import hashlib
import hmac
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import astro_bridge

TENANT = "0f897915-2d34-4b67-8d69-f83f52e4fb6c"
SESSION_ID = "11111111-2222-3333-4444-555555555555"

_SETTINGS = {
    "astro_bridge_url": "https://astro.example.com/",
    "astro_bridge_api_key": "aira-bridge-local-dev-key-2026",
    "astro_bridge_secret": "s3cr3t",
}


def _settings_stub(recorder=None):
    def _get_setting(key, fallback=None, tenant_id=None):
        if recorder is not None:
            recorder.append((key, tenant_id))
        return _SETTINGS.get(key, fallback)

    return _get_setting


def _session(**overrides):
    session = {
        "id": SESSION_ID,
        "amount_paise": 19900,
        "trigger_reason": "Will I get married this year?",
        "collected_data": {
            "name": "Meena Raman",
            "Date of Birth": "12th March 1990",
            "birth_time": "9:30 AM",
            "gender": "female",
            "birthplace": "Coimbatore, Tamil Nadu",
            "question": "When will I get married?",
        },
    }
    session.update(overrides)
    return session


def _lead(**overrides):
    lead = {"name": "Meena", "phone": "+919345679286"}
    lead.update(overrides)
    return lead


def _response(payload, status_code=200, text=""):
    response = MagicMock()
    response.status_code = status_code
    response.text = text
    response.json.return_value = payload
    return response


def _client_patch(post_mock):
    patcher = patch("httpx.AsyncClient")
    mock_client = patcher.start()
    mock_client.return_value.__aenter__.return_value.post = post_mock
    return patcher, mock_client


@pytest.mark.asyncio
async def test_push_consultation_sends_normalised_payload():
    post = AsyncMock(return_value=_response({
        "success": True,
        "question_id": 123,
        "horoscope_id": "HOR-AB12CD34",
        "astro_user_id": 456,
        "already_existed": False,
    }))
    patcher, _ = _client_patch(post)
    try:
        with patch.object(astro_bridge, "get_setting", new=_settings_stub()):
            result = await astro_bridge.push_consultation(_session(), _lead(), TENANT)
    finally:
        patcher.stop()

    assert result["question_id"] == 123
    url, = post.call_args[0]
    assert url == "https://astro.example.com/api/astrologer-welcome/bridge/consultation/"
    assert post.call_args[1]["headers"] == {"X-API-Key": "aira-bridge-local-dev-key-2026"}
    body = post.call_args[1]["json"]
    assert body == {
        "external_ref": SESSION_ID,
        "phone": "+919345679286",
        "customer_name": "Meena Raman",
        "person_name": "Meena Raman",
        "person_gender": "F",
        "person_birth_date": "1990-03-12",
        "person_birth_time": "09:30:00",
        "person_birth_place": "Coimbatore, Tamil Nadu",
        "question_text": "When will I get married?",
        "amount": 199.0,
        "tenant_id": TENANT,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,bad_value",
    [
        ("Date of Birth", "sometime in the 90s"),
        ("birth_time", "no idea"),
        ("gender", "not sure"),
        ("question", ""),
    ],
)
async def test_push_consultation_refuses_unparseable_field(field, bad_value):
    session = _session()
    session["collected_data"][field] = bad_value
    if field == "question":
        session["trigger_reason"] = ""
    post = AsyncMock()
    patcher, _ = _client_patch(post)
    try:
        with patch.object(astro_bridge, "get_setting", new=_settings_stub()):
            result = await astro_bridge.push_consultation(session, _lead(), TENANT)
    finally:
        patcher.stop()

    assert result is None
    post.assert_not_called()


@pytest.mark.asyncio
async def test_push_consultation_refuses_unparseable_phone():
    post = AsyncMock()
    patcher, _ = _client_patch(post)
    try:
        with patch.object(astro_bridge, "get_setting", new=_settings_stub()):
            result = await astro_bridge.push_consultation(_session(), _lead(phone="12345"), TENANT)
    finally:
        patcher.stop()

    assert result is None
    post.assert_not_called()


@pytest.mark.asyncio
async def test_push_consultation_falls_back_to_trigger_reason_for_question():
    session = _session()
    del session["collected_data"]["question"]
    post = AsyncMock(return_value=_response({"success": True, "question_id": 7}))
    patcher, _ = _client_patch(post)
    try:
        with patch.object(astro_bridge, "get_setting", new=_settings_stub()):
            result = await astro_bridge.push_consultation(session, _lead(), TENANT)
    finally:
        patcher.stop()

    assert result["question_id"] == 7
    assert post.call_args[1]["json"]["question_text"] == "Will I get married this year?"


@pytest.mark.asyncio
async def test_push_consultation_returns_none_when_bridge_unconfigured():
    post = AsyncMock()
    patcher, _ = _client_patch(post)
    try:
        with patch.object(astro_bridge, "get_setting", new=lambda *a, **k: None):
            result = await astro_bridge.push_consultation(_session(), _lead(), TENANT)
    finally:
        patcher.stop()

    assert result is None
    post.assert_not_called()


@pytest.mark.asyncio
async def test_push_consultation_returns_none_on_django_error_response():
    post = AsyncMock(return_value=_response({"success": False, "error": "question_text required"}, status_code=400))
    patcher, _ = _client_patch(post)
    try:
        with patch.object(astro_bridge, "get_setting", new=_settings_stub()):
            result = await astro_bridge.push_consultation(_session(), _lead(), TENANT)
    finally:
        patcher.stop()

    assert result is None


@pytest.mark.asyncio
async def test_push_consultation_never_raises_on_transport_error():
    import httpx

    post = AsyncMock(side_effect=httpx.ConnectTimeout("boom"))
    patcher, _ = _client_patch(post)
    try:
        with patch.object(astro_bridge, "get_setting", new=_settings_stub()):
            result = await astro_bridge.push_consultation(_session(), _lead(), TENANT)
    finally:
        patcher.stop()

    assert result is None


@pytest.mark.asyncio
async def test_push_consultation_always_passes_tenant_id_to_get_setting():
    reads = []
    post = AsyncMock(return_value=_response({"success": True, "question_id": 1}))
    patcher, _ = _client_patch(post)
    try:
        with patch.object(astro_bridge, "get_setting", new=_settings_stub(reads)):
            await astro_bridge.push_consultation(_session(), _lead(), TENANT)
    finally:
        patcher.stop()

    assert reads, "no settings were read"
    assert {key for key, _ in reads} == {"astro_bridge_url", "astro_bridge_api_key"}
    assert all(tenant_id == TENANT for _, tenant_id in reads)


def test_get_bridge_secret_passes_tenant_id():
    reads = []
    with patch.object(astro_bridge, "get_setting", new=_settings_stub(reads)):
        assert astro_bridge.get_bridge_secret(TENANT) == "s3cr3t"
    assert reads == [("astro_bridge_secret", TENANT)]


def _sign(body: bytes, secret: str = "s3cr3t") -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_verify_astro_signature_accepts_prefixed_header():
    body = b'{"external_ref":"abc","reply_id":7}'
    assert astro_bridge.verify_astro_signature(body, f"sha256={_sign(body)}", "s3cr3t") is True


def test_verify_astro_signature_accepts_bare_hexdigest():
    body = b'{"external_ref":"abc","reply_id":7}'
    assert astro_bridge.verify_astro_signature(body, _sign(body), "s3cr3t") is True


def test_verify_astro_signature_accepts_uppercase_hex():
    body = b'{"external_ref":"abc"}'
    assert astro_bridge.verify_astro_signature(body, f"SHA256={_sign(body).upper()}", "s3cr3t") is True


def test_verify_astro_signature_rejects_wrong_secret():
    body = b'{"external_ref":"abc"}'
    assert astro_bridge.verify_astro_signature(body, _sign(body, "other"), "s3cr3t") is False


def test_verify_astro_signature_rejects_tampered_body():
    body = b'{"external_ref":"abc"}'
    signature = _sign(body)
    assert astro_bridge.verify_astro_signature(b'{"external_ref":"xyz"}', signature, "s3cr3t") is False


def test_verify_astro_signature_rejects_missing_header_or_secret():
    body = b"{}"
    assert astro_bridge.verify_astro_signature(body, "", "s3cr3t") is False
    assert astro_bridge.verify_astro_signature(body, _sign(body), "") is False
    assert astro_bridge.verify_astro_signature(body, None, "s3cr3t") is False


def test_verify_astro_signature_rejects_non_ascii_header_without_raising():
    body = b"{}"
    assert astro_bridge.verify_astro_signature(body, "sha256=ஆம்", "s3cr3t") is False
