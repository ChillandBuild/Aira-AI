"""Wiring checks for the silence nudge hooks.

These are deliberately source-level. The behaviour they protect — "a failure
while arming must never stop a customer receiving their reply" — lives inside
generate_reply(), a function whose full execution needs the whole world mocked.
Asserting the guard is present is cheaper than that and fails just as loudly if
someone removes it.
"""
from pathlib import Path

import pytest


def _source(module) -> str:
    return Path(module.__file__).read_text(encoding="utf-8")


def test_outbound_insert_result_is_captured():
    """maybe_arm_after_ai_reply needs the inserted row id as its anchor, so the
    Step 4 insert must no longer discard its result."""
    import app.services.ai_reply as ar
    assert '_outbound_res = db.table("messages").insert(outbound_row).execute()' in _source(ar)


def test_ai_reply_wraps_the_arm_call_in_try_except():
    """Source-level guard: the arm hook sits inside a try/except that logs."""
    import app.services.ai_reply as ar
    src = _source(ar)
    idx = src.index("maybe_arm_after_ai_reply(")
    window = src[idx - 600:idx + 600]
    assert "try:" in window
    assert "except Exception" in window
    assert "logger.exception" in window


def test_arm_hook_passes_every_gate_argument():
    """A missing kwarg would make maybe_arm_after_ai_reply arm unconditionally
    or raise — both worse than not arming at all."""
    import app.services.ai_reply as ar
    src = _source(ar)
    idx = src.index("maybe_arm_after_ai_reply(")
    window = src[idx:idx + 500]
    for kwarg in ("tenant_id=", "lead_id=", "channel=", "is_ai=", "sid=",
                  "reply_source=", "inserted="):
        assert kwarg in window, f"arm hook is missing {kwarg}"


@pytest.mark.parametrize("marker", [
    '"direction": "inbound"',
])
def test_webhook_cancels_pending_nudges_at_every_inbound_site(marker):
    """Both WhatsApp inbound insert sites (text and audio) must cancel."""
    import app.routes.webhook as wh
    src = _source(wh)
    inbound_sites = src.count(marker)
    assert inbound_sites == 2, f"expected 2 inbound insert sites, found {inbound_sites}"
    assert src.count("cancel_pending(") == inbound_sites


def test_webhook_cancel_is_wrapped_so_it_cannot_drop_an_inbound_message():
    import app.routes.webhook as wh
    src = _source(wh)
    start = 0
    for _ in range(2):
        idx = src.index("cancel_pending(", start)
        window = src[idx - 300:idx + 300]
        assert "try:" in window
        assert "except Exception" in window
        start = idx + 1
