import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import inspect
from datetime import datetime, timezone

from app.routes import chat_handovers
from app.services import ai_reply


# --- the AI must stay live through the whole handover -----------------------

def test_escalation_does_not_disable_ai():
    """_trigger_chat_escalation must not set ai_enabled False — an escalated
    customer should never get silence while waiting for a human."""
    src = inspect.getsource(ai_reply._trigger_chat_escalation)
    assert '"ai_enabled": False' not in src
    assert '"needs_human_attention": True' in src


def test_resolve_does_not_reenable_ai():
    """resolve_handover must not set ai_enabled True — escalation no longer
    disables it, so writing True would clobber a manual admin mute."""
    src = inspect.getsource(chat_handovers.resolve_handover)
    assert '"ai_enabled": True' not in src
    assert '"needs_human_attention": False' in src


def test_escalation_queues_whatsapp_alert():
    src = inspect.getsource(ai_reply._trigger_chat_escalation)
    assert "queue_escalation_whatsapp_alert" in src


def test_hot_lead_helper_import_removed():
    """should_escalate_hot_lead was dead config — it must not be imported."""
    src = Path(ai_reply.__file__).read_text(encoding="utf-8")
    assert "should_escalate_hot_lead" not in src


def test_lead_select_includes_needs_human_attention():
    """The prompt block keys off needs_human_attention, so it must be selected."""
    src = Path(ai_reply.__file__).read_text(encoding="utf-8")
    body = src.split("async def generate_reply")[1][:4000]
    assert "needs_human_attention" in body


# --- situational prompt block ----------------------------------------------

def _bh(**overrides):
    base = {
        "enabled": True, "timezone": "Asia/Kolkata",
        "open_time": "09:00", "close_time": "19:00",
        "working_days": [1, 2, 3, 4, 5, 6],
    }
    base.update(overrides)
    return base


# Monday 06:30 UTC == 12:00 IST (open); Monday 15:00 UTC == 20:30 IST (closed).
MON_OPEN = datetime(2026, 7, 20, 6, 30, tzinfo=timezone.utc)
MON_CLOSED = datetime(2026, 7, 20, 15, 0, tzinfo=timezone.utc)


def test_prompt_block_marks_office_open_in_hours():
    block = ai_reply._escalation_prompt_block(_bh(), now=MON_OPEN)
    assert "currently OPEN" in block
    assert "contact them shortly" in block
    assert "Monday to Saturday" in block


def test_prompt_block_marks_office_closed_out_of_hours():
    block = ai_reply._escalation_prompt_block(_bh(), now=MON_CLOSED)
    assert "currently CLOSED" in block
    assert "call them tomorrow" in block
    assert "Monday to Saturday" in block


def test_prompt_block_forbids_specific_promises():
    block = ai_reply._escalation_prompt_block(_bh(), now=MON_OPEN)
    assert "Never promise a specific time" in block
    assert "Never claim someone has already called" in block
    assert "Never say the request was resolved" in block


def test_prompt_block_tells_ai_to_keep_answering():
    """The AI must not become a one-note holding-reply bot."""
    block = ai_reply._escalation_prompt_block(_bh(), now=MON_OPEN)
    assert "keep answering their questions normally" in block
