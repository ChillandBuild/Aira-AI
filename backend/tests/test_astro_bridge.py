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
        ("birth_time", "around the evening"),  # "no idea" is now an unknown time: see the placeholder tests
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


# ── Connection check, field roles, form check and the unknown-birth-time placeholder ──
def test_is_connected_needs_both_url_and_key():
    with patch.object(astro_bridge, "get_setting", new=_settings_stub()):
        assert astro_bridge.is_connected(TENANT) is True
    only_url = {"astro_bridge_url": "https://astro.example.com/"}
    with patch.object(astro_bridge, "get_setting", lambda k, fallback=None, tenant_id=None: only_url.get(k, fallback)):
        assert astro_bridge.is_connected(TENANT) is False
    assert astro_bridge.is_connected(TENANT) is False  # conftest default: nothing saved


@pytest.mark.parametrize(
    "key,role",
    [
        ("name", "person_name"), ("full_name", "person_name"),
        ("gender", "gender"), ("Sex", "gender"),
        ("date_of_birth", "birth_date"), ("dob", "birth_date"), ("Date Of Birth", "birth_date"),
        ("time_of_birth", "birth_time"), ("tob", "birth_time"),
        ("place_of_birth", "birth_place"), ("birthplace", "birth_place"),
        ("question", "question"),
        ("place_of_birh", None),  # the live typo from 2026-09-30
        ("email", None), ("unisex", None),
    ],
)
def test_field_role_reads_the_tenant_authored_key(key, role):
    assert astro_bridge.field_role(key) == role


def test_missing_form_fields_names_what_the_form_cannot_provide():
    form = [{"key": "name"}, {"key": "date_of_birth"}, {"key": "time_of_birth"},
            {"key": "place_of_birh"}, {"key": "question"}]
    assert astro_bridge.missing_form_fields(form) == ["Gender", "Place of birth"]
    assert astro_bridge.unrecognised_form_keys(form) == ["place_of_birh"]
    full = form[:3] + [{"key": "gender"}, {"key": "place_of_birth"}, {"key": "question"}]
    assert astro_bridge.missing_form_fields(full) == []


def test_unusable_for_push_matches_what_the_push_would_refuse():
    good = {"name": "Keerthi", "gender": "Male", "date_of_birth": "2003-11-15",
            "time_of_birth": "10:30 AM", "place_of_birth": "Neyveli", "question": "job?"}
    assert astro_bridge.unusable_for_push(good, [], "+916369781582") == []
    bad = {**good, "date_of_birth": "sometime in the 90s", "gender": "theriyathu", "time_of_birth": "abc"}
    assert astro_bridge.unusable_for_push(bad, [], "+916369781582") == ["birth date", "birth time", "gender"]


@pytest.mark.asyncio
@pytest.mark.parametrize("how", ["skipped", "says_unknown"])
async def test_unknown_birth_time_is_sent_as_noon_with_a_note(how):
    collected = {"name": "Keerthi", "gender": "Male", "date_of_birth": "2003-11-15",
                 "place_of_birth": "Neyveli", "question": "job eppo?"}
    skipped = []
    if how == "skipped":
        skipped = ["time_of_birth"]
    else:
        collected["time_of_birth"] = "theriyathu"
    post = AsyncMock(return_value=_response({"success": True, "question_id": 1}))
    patcher, _ = _client_patch(post)
    try:
        with patch.object(astro_bridge, "get_setting", new=_settings_stub()):
            result = await astro_bridge.push_consultation(
                _session(collected_data=collected, skipped_fields=skipped), _lead(), TENANT)
    finally:
        patcher.stop()
    sent = post.call_args.kwargs["json"]
    assert result and sent["person_birth_time"] == "12:00:00"
    assert "birth time" in sent["question_text"].lower() and "12:00" in sent["question_text"]
    assert sent["question_text"].startswith("job eppo?")


@pytest.mark.asyncio
async def test_a_skipped_birth_date_is_still_refused():
    collected = {"name": "K", "gender": "Male", "time_of_birth": "10:30 AM", "question": "job?"}
    with patch.object(astro_bridge, "get_setting", new=_settings_stub()):
        result = await astro_bridge.push_consultation(
            _session(collected_data=collected, skipped_fields=["date_of_birth"]), _lead(), TENANT)
    assert result is None


@pytest.mark.asyncio
async def test_a_real_time_inside_an_i_dont_know_sentence_is_kept_not_replaced_by_noon():
    collected = {"name": "K", "gender": "Male", "date_of_birth": "2003-11-15", "place_of_birth": "Neyveli",
                 "time_of_birth": "I don't know exactly, maybe 6 am", "question": "job?"}
    post = AsyncMock(return_value=_response({"success": True, "question_id": 1}))
    patcher, _ = _client_patch(post)
    try:
        with patch.object(astro_bridge, "get_setting", new=_settings_stub()):
            await astro_bridge.push_consultation(_session(collected_data=collected), _lead(), TENANT)
    finally:
        patcher.stop()
    sent = post.call_args.kwargs["json"]
    assert sent["person_birth_time"] == "06:00:00" and "placeholder" not in sent["question_text"]


def test_unusable_for_push_counts_trigger_reason_as_a_question_like_the_push_does():
    collected = {"gender": "Male", "date_of_birth": "2003-11-15", "time_of_birth": "10:30 AM", "place_of_birth": "Neyveli"}
    assert astro_bridge.unusable_for_push(collected, [], "+916369781582") == ["question"]
    assert astro_bridge.unusable_for_push(collected, [], "+916369781582", "job eppo?") == []


@pytest.mark.parametrize("place", [None, "", "?", "idk"])
def test_a_missing_or_junk_birth_place_is_unusable(place):
    collected = {"gender": "Male", "date_of_birth": "2003-11-15", "time_of_birth": "10:30 AM", "question": "job?"}
    if place is not None:
        collected["place_of_birth"] = place
    assert astro_bridge.unusable_for_push(collected, [], "+916369781582") == ["birth place"]


@pytest.mark.parametrize("raw_time", ["5:30", "1030", "9"])
def test_a_time_that_could_be_am_or_pm_is_unusable_whatever_path_saved_it(raw_time):
    collected = {"gender": "Male", "date_of_birth": "2003-11-15", "place_of_birth": "Neyveli",
                 "question": "job?", "time_of_birth": raw_time}
    assert astro_bridge.unusable_for_push(collected, [], "+916369781582") == ["birth time"]
