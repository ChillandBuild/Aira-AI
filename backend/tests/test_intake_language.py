import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services import intake as ik


_FIELDS = [
    {"key": "name", "label": "Full name", "type": "text"},
    {"key": "dob", "label": "Date of birth", "type": "date"},
]

_CONFIG = {
    "enabled": True,
    "trigger_description": "astrology question",
    "offer_message": "Verum ₹29 dhaan. Proceed pannalaama?",
    "fields": _FIELDS,
    "packages": [{"key": "standard", "name": "Consultation", "amount_paise": 2900, "description": ""}],
    "service_noun": "consultation",
    "amount_paise": 2900,
}


def _session(status: str, **extra):
    return {"id": "s-1", "status": status, "collected_data": {}, **extra}


@pytest.mark.asyncio
async def test_collecting_asks_in_the_tenant_language():
    db = MagicMock()
    sent: list[str] = []
    with patch.object(ik, "get_intake_config", return_value=_CONFIG), \
         patch.object(ik, "_get_active_session", return_value=_session("collecting")), \
         patch.object(ik, "_update_session"), \
         patch.object(ik, "extract_fields", new=AsyncMock(return_value={"name": "Cheran"})), \
         patch.object(ik, "resolve_language_mode", return_value="tanglish"), \
         patch.object(ik, "gather_context", new=AsyncMock(return_value=([], ""))), \
         patch.object(ik, "compose_line", new=AsyncMock(return_value="Unga piranthaa thedhi enna?")), \
         patch.object(ik, "_send_and_log", new=AsyncMock(side_effect=lambda p, t, *a, **k: sent.append(t))):
        consumed = await ik.route_intake(lead_id="l-1", tenant_id="t-1", phone="+91", body="Cheran", db=db)
    assert consumed is True
    assert sent == ["Unga piranthaa thedhi enna?"]


@pytest.mark.asyncio
async def test_payment_message_keeps_the_real_url_and_uses_composed_intro():
    db = MagicMock()
    sent: list[str] = []
    session = _session(
        "awaiting_confirmation",
        collected_data={"name": "Cheran", "dob": "06.06.2000"},
        package_amount_paise=2900,
    )
    with patch.object(ik, "get_intake_config", return_value=_CONFIG), \
         patch.object(ik, "_get_active_session", return_value=session), \
         patch.object(ik, "_update_session"), \
         patch.object(ik, "_is_affirmative", return_value=True), \
         patch.object(ik, "resolve_language_mode", return_value="tamil"), \
         patch.object(ik, "gather_context", new=AsyncMock(return_value=([], ""))), \
         patch.object(ik, "compose_line", new=AsyncMock(return_value="இதோ உங்க பேமெண்ட் லிங்க்:")), \
         patch.object(ik, "create_payment_link", new=AsyncMock(return_value={"payment_link_url": "https://rzp.io/rzp/ABC"})), \
         patch.object(ik, "_send_and_log", new=AsyncMock(side_effect=lambda p, t, *a, **k: sent.append(t))):
        consumed = await ik.route_intake(lead_id="l-1", tenant_id="t-1", phone="+91", body="சரி", db=db)
    assert consumed is True
    assert sent == ["இதோ உங்க பேமெண்ட் லிங்க்:\nhttps://rzp.io/rzp/ABC"]


@pytest.mark.asyncio
async def test_summary_block_values_are_never_rewritten():
    db = MagicMock()
    sent: list[str] = []
    with patch.object(ik, "get_intake_config", return_value=_CONFIG), \
         patch.object(ik, "_get_active_session", return_value=_session("collecting")), \
         patch.object(ik, "_update_session"), \
         patch.object(ik, "extract_fields", new=AsyncMock(return_value={"name": "Cheran", "dob": "06.06.2000"})), \
         patch.object(ik, "resolve_language_mode", return_value="tanglish"), \
         patch.object(ik, "gather_context", new=AsyncMock(return_value=([], ""))), \
         patch.object(ik, "compose_wrapped", new=AsyncMock(side_effect=lambda *a, **k: f"INTRO\n\n{k['block']}\n\nOK?")), \
         patch.object(ik, "_send_and_log", new=AsyncMock(side_effect=lambda p, t, *a, **k: sent.append(t))):
        await ik.route_intake(lead_id="l-1", tenant_id="t-1", phone="+91", body="06.06.2000", db=db)
    assert "Full name: Cheran" in sent[0]
    assert "Date of birth: 06.06.2000" in sent[0]


def test_summary_block_marks_skipped_fields_distinctly():
    block = ik._summary_block(_FIELDS, {"name": "Cheran"}, skipped=("dob",))
    assert "Full name: Cheran" in block
    assert "Date of birth: — (not provided)" in block


def test_package_list_block_renders_prices_in_python():
    packages = [{"key": "s", "name": "Consultation", "amount_paise": 2900, "description": "30 min"}]
    block = ik.package_list_block(packages)
    assert "₹29" in block
    assert "30 min" in block
