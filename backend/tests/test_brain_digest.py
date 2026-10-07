"""Aira Brain weekly digest: quiet tenants skipped, owners only, failures isolated, message text."""
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import brain_digest as bd

NOW = datetime(2026, 9, 28, 3, 30, tzinfo=timezone.utc)


class _Result:
    def __init__(self, data):
        self.data = data


class _Q:
    def __init__(self, rows):
        self.rows, self.filters = rows, []

    def select(self, *a, **k): return self
    def eq(self, c, v): self.filters.append(lambda r: r.get(c) == v); return self
    def execute(self): return _Result([r for r in self.rows if all(f(r) for f in self.filters)])


class _FakeDb:
    def __init__(self, tenants, users):
        self.tables = {"tenants": tenants, "tenant_users": users}

    def table(self, name):
        return _Q(self.tables[name])


def _gap(question):
    return {"kind": "knowledge_gap", "likely_question": question}


def _db(*tenant_ids, users=None):
    return _FakeDb([{"id": t} for t in tenant_ids], users or [])


def _summary(count):
    return {"count": count}


def _run(db, summaries, handover_rows):
    """Run the digest with waiting_summary/recent_handovers stubbed per tenant; return notify calls."""
    with patch.object(bd.waiting, "waiting_summary", side_effect=lambda _db, t: summaries[t]), \
         patch.object(bd.handovers, "recent_handovers", side_effect=lambda _db, t, since: handover_rows.get(t, [])), \
         patch.object(bd, "notify_user") as notify:
        sent = bd.send_weekly_digests(db, now=NOW)
    return sent, notify.call_args_list


def test_skips_tenant_with_nothing_waiting_and_no_gaps():
    db = _db("t1", users=[{"tenant_id": "t1", "user_id": "u1", "role": "owner"}])
    sent, calls = _run(db, {"t1": _summary(0)}, {"t1": [{"kind": "asked_for_human", "likely_question": "call me"}]})
    assert sent == 0 and calls == []


def test_notifies_owners_only_not_callers_or_admins():
    users = [
        {"tenant_id": "t1", "user_id": "owner1", "role": "owner"},
        {"tenant_id": "t1", "user_id": "owner2", "role": "owner"},
        {"tenant_id": "t1", "user_id": "admin1", "role": "admin"},
        {"tenant_id": "t1", "user_id": "caller1", "role": "caller"},
        {"tenant_id": "t2", "user_id": "other_owner", "role": "owner"},
    ]
    sent, calls = _run(_db("t1", users=users), {"t1": _summary(2)}, {})
    assert sent == 2
    assert [c.args[1] for c in calls] == ["owner1", "owner2"]
    assert all(c.args[0] == "t1" and c.args[2] == "brain_digest" for c in calls)
    assert all(c.kwargs["push_url"] == "/dashboard/brain" for c in calls)
    assert all(c.args[3] == "Anril Brain weekly digest" for c in calls)


def test_one_tenant_exception_does_not_stop_the_others(caplog):
    users = [{"tenant_id": t, "user_id": f"o-{t}", "role": "owner"} for t in ("t1", "t2", "t3")]
    db = _db("t1", "t2", "t3", users=users)

    def summary(_db, tenant_id):
        if tenant_id == "t2":
            raise RuntimeError("boom")
        return _summary(1)

    with patch.object(bd.waiting, "waiting_summary", side_effect=summary), \
         patch.object(bd.handovers, "recent_handovers", return_value=[]), \
         patch.object(bd, "notify_user") as notify, caplog.at_level("ERROR"):
        sent = bd.send_weekly_digests(db, now=NOW)
    assert sent == 2
    assert [c.args[0] for c in notify.call_args_list] == ["t1", "t3"]
    assert "t2" in caplog.text


def test_message_with_zero_questions():
    assert bd.build_digest_message(3, []) == "Anril Brain: 3 things need you."


def test_message_with_one_question_and_singular_count():
    msg = bd.build_digest_message(1, ["Do you deliver to Madurai?"])
    assert msg == "Anril Brain: 1 thing needs you. Top question Anril couldn't answer: 'Do you deliver to Madurai?'"


def test_message_with_three_questions():
    msg = bd.build_digest_message(3, ["a?", "b?", "c?"])
    assert msg == "Anril Brain: 3 things need you. Top questions Anril couldn't answer: 'a?'; 'b?'; 'c?'"


def test_message_when_only_gaps_and_nothing_waiting():
    msg = bd.build_digest_message(0, ["a?"])
    assert msg.startswith("Anril Brain: nothing is waiting on you.") and "'a?'" in msg


def test_message_none_when_nothing_to_say():
    assert bd.build_digest_message(0, []) is None


def test_top_questions_keep_only_gaps_dedupe_and_cap_at_three():
    rows = [_gap("A?"), {"kind": "payment", "likely_question": "pay"}, _gap("a?"), _gap(None),
            _gap("B?"), _gap("C?"), _gap("D?")]
    with patch.object(bd.handovers, "recent_handovers", return_value=rows):
        assert bd.top_unanswered_questions(MagicMock(), "t1", "since") == ["A?", "B?", "C?"]


def test_long_question_truncated_to_preview_limit():
    with patch.object(bd.handovers, "recent_handovers", return_value=[_gap("x" * 200)]):
        (q,) = bd.top_unanswered_questions(MagicMock(), "t1", "since")
    assert len(q) == bd.QUESTION_PREVIEW_CHARS and q.endswith("...")


def test_gaps_only_week_still_sends_and_uses_seven_day_window():
    users = [{"tenant_id": "t1", "user_id": "o1", "role": "owner"}]
    seen = {}

    def recent(_db, tenant_id, since):
        seen["since"] = since
        return [_gap("Do you deliver to Madurai?")]

    with patch.object(bd.waiting, "waiting_summary", return_value=_summary(0)), \
         patch.object(bd.handovers, "recent_handovers", side_effect=recent), \
         patch.object(bd, "notify_user") as notify:
        assert bd.send_weekly_digests(_db("t1", users=users), now=NOW) == 1
    assert seen["since"].startswith("2026-09-21T03:30")
    assert "Madurai" in notify.call_args.args[4]


def test_digest_makes_no_model_call_or_network_request():
    users = [{"tenant_id": "t1", "user_id": "o1", "role": "owner"}]
    with patch("httpx.Client.send", side_effect=AssertionError("network call")) as sync_send, \
         patch("httpx.AsyncClient.send", side_effect=AssertionError("network call")) as async_send, \
         patch("app.services.consistency.gather") as gather:
        sent, _ = _run(_db("t1", users=users), {"t1": _summary(1)}, {"t1": [_gap("q?")]})
    assert sent == 1
    sync_send.assert_not_called()
    async_send.assert_not_called()
    gather.assert_not_called()
