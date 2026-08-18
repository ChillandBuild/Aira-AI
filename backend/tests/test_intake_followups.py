"""Follow-up forwarding: once the expert has answered, everything the paid
customer says goes to that same expert and the AI stays out of it."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import intake as ik

SID = "11111111-2222-3333-4444-555555555555"
TENANT = "0f897915-2d34-4b67-8d69-f83f52e4fb6c"
LEAD = "22222222-3333-4444-5555-666666666666"
PHONE = "+919345679286"


def _session(**over):
    """A paid session the expert has already answered once."""
    return {
        "id": SID,
        "status": "paid",
        "lead_id": LEAD,
        "tenant_id": TENANT,
        "collected_data": {"name": "Meena"},
        "astro_question_id": 501,
        "astro_last_reply_id": 77,
        "astro_followup_count": 0,
        **over,
    }


def _db(claim_results=None, counts=None):
    """`claim_results` is what each compare-and-set UPDATE returns in order —
    a row list means claimed, [] means another message got that number first."""
    claim_results = [[{"id": SID}]] if claim_results is None else list(claim_results)
    counts = list(counts or [])
    db = MagicMock()
    updates = []

    def table(name):
        t = MagicMock()
        if name == "intake_sessions":
            def update(patch_body):
                updates.append(patch_body)
                chain = MagicMock()
                result = MagicMock()
                result.data = claim_results.pop(0) if claim_results else []
                chain.eq.return_value.eq.return_value.eq.return_value.execute.return_value = result
                return chain
            t.update.side_effect = update
            fresh = MagicMock()
            fresh.data = {"astro_followup_count": counts.pop(0)} if counts else {"astro_followup_count": 0}
            t.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = fresh
        elif name == "leads":
            row = MagicMock()
            row.data = {"id": LEAD, "name": "Meena Raman", "phone": PHONE}
            t.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = row
        return t

    cache = {}
    db.table.side_effect = lambda n: cache.setdefault(n, table(n))
    db._updates = updates
    return db


def _receipt_patches(send=None):
    return [
        patch.object(ik, "resolve_language_mode", return_value="english"),
        patch.object(ik, "gather_context", new=AsyncMock(return_value=([], ""))),
        patch.object(ik, "collector_identity", return_value=""),
        patch.object(ik, "compose_line", new=AsyncMock(return_value="Passed on to your expert.")),
        patch.object(ik, "_send_and_log", new=send or AsyncMock()),
    ]


async def _forward(db, session=None, body="And my career?", push=None):
    push = push or AsyncMock(return_value={"question_id": 9})
    patches = _receipt_patches()
    for p in patches:
        p.start()
    try:
        with patch("app.services.astro_bridge.push_followup", new=push):
            return await ik.forward_followup_to_astrologer(
                session or _session(), LEAD, TENANT, PHONE, body, db
            ), push
    finally:
        for p in patches:
            p.stop()


@pytest.mark.asyncio
async def test_forwards_the_message_and_consumes_the_turn():
    """Consuming the turn is what keeps the AI from also answering — that is the
    whole point: the customer paid a human for this answer."""
    db = _db()
    consumed, push = await _forward(db)
    assert consumed is True
    session_arg, lead_arg, question, tenant, n = push.await_args[0]
    assert question == "And my career?"
    assert tenant == TENANT
    assert n == 1
    assert lead_arg["name"] == "Meena Raman"


@pytest.mark.asyncio
async def test_sends_the_customer_a_receipt_so_they_are_not_left_in_silence():
    """The 2026-08-07..11 incident: a muted paid lead heard nothing at all. The
    expert answers the question, but the customer must see that it landed."""
    send = AsyncMock()
    db = _db()
    patches = _receipt_patches(send=send)
    for p in patches:
        p.start()
    try:
        with patch("app.services.astro_bridge.push_followup", new=AsyncMock(return_value={"question_id": 9})):
            await ik.forward_followup_to_astrologer(_session(), LEAD, TENANT, PHONE, "hi", db)
    finally:
        for p in patches:
            p.stop()
    send.assert_awaited_once()
    assert send.await_args[0][0] == PHONE


@pytest.mark.asyncio
async def test_does_not_forward_before_the_expert_has_answered():
    """Paid but unanswered is the waiting state, where ai_reply's paid prompt
    block keeps the AI reassuring the lead rather than silent."""
    db = _db()
    consumed, push = await _forward(db, session=_session(astro_last_reply_id=None))
    assert consumed is False
    push.assert_not_awaited()


@pytest.mark.asyncio
async def test_does_not_forward_when_the_consultation_never_reached_the_bridge():
    """No Django thread exists yet — astro-push-reconcile still owes it a push."""
    db = _db()
    consumed, push = await _forward(db, session=_session(astro_question_id=None))
    assert consumed is False
    push.assert_not_awaited()


@pytest.mark.asyncio
async def test_follow_up_number_continues_from_the_stored_count():
    """Django keys idempotency off "{sid}::f{n}" and silently swallows a repeat,
    so n must never restart."""
    db = _db()
    _, push = await _forward(db, session=_session(astro_followup_count=4))
    assert push.await_args[0][4] == 5


@pytest.mark.asyncio
async def test_retries_the_claim_when_another_message_took_that_number():
    db = _db(claim_results=[[], [{"id": SID}]], counts=[1])
    _, push = await _forward(db)
    assert push.await_args[0][4] == 2


@pytest.mark.asyncio
async def test_yields_to_the_ai_when_the_push_fails_rather_than_going_silent():
    db = _db()
    with patch.object(ik, "notify_pool") as notify:
        consumed, _ = await _forward(db, push=AsyncMock(return_value=None))
    assert consumed is False
    notify.assert_called_once()


@pytest.mark.asyncio
async def test_gives_the_number_back_when_the_push_fails():
    """Burning n on a failed push would leave a permanent gap in the thread."""
    db = _db()
    with patch.object(ik, "notify_pool"):
        await _forward(db, push=AsyncMock(return_value=None))
    assert {"astro_followup_count": 1} in db._updates
    assert {"astro_followup_count": 0} in db._updates


@pytest.mark.asyncio
async def test_a_raising_push_is_treated_as_a_failure_not_a_crash():
    db = _db()
    with patch.object(ik, "notify_pool"):
        consumed, _ = await _forward(db, push=AsyncMock(side_effect=RuntimeError("django down")))
    assert consumed is False


@pytest.mark.asyncio
async def test_a_failed_receipt_still_consumes_the_turn():
    """The expert has the question either way; letting the AI answer it too would
    put a machine's answer next to the astrologer's."""
    db = _db()
    patches = _receipt_patches(send=AsyncMock(side_effect=RuntimeError("meta down")))
    for p in patches:
        p.start()
    try:
        with patch("app.services.astro_bridge.push_followup", new=AsyncMock(return_value={"question_id": 9})):
            consumed = await ik.forward_followup_to_astrologer(_session(), LEAD, TENANT, PHONE, "hi", db)
    finally:
        for p in patches:
            p.stop()
    assert consumed is True


@pytest.mark.asyncio
async def test_route_intake_hands_a_paid_session_to_the_follow_up_path():
    """Wiring check: the branch sits ahead of the brain-led yield, so follow-ups
    work in both collector modes."""
    db = MagicMock()
    forward = AsyncMock(return_value=True)
    with patch.object(ik, "get_intake_config", return_value={"enabled": True, "fields": [], "service_noun": "reading"}), \
         patch.object(ik, "_get_active_session", return_value=_session()), \
         patch.object(ik, "forward_followup_to_astrologer", new=forward), \
         patch.object(ik, "is_brain_led", return_value=True):
        consumed = await ik.route_intake(LEAD, TENANT, PHONE, "And my career?", db=db)
    assert consumed is True
    forward.assert_awaited_once()


@pytest.mark.asyncio
async def test_route_intake_leaves_unpaid_sessions_alone():
    forward = AsyncMock(return_value=True)
    with patch.object(ik, "get_intake_config", return_value={"enabled": True, "fields": [], "service_noun": "reading"}), \
         patch.object(ik, "_get_active_session", return_value=_session(status="awaiting_payment")), \
         patch.object(ik, "forward_followup_to_astrologer", new=forward), \
         patch.object(ik, "is_brain_led", return_value=True):
        await ik.route_intake(LEAD, TENANT, PHONE, "hello", db=MagicMock())
    forward.assert_not_awaited()
