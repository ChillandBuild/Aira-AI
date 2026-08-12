from unittest.mock import MagicMock, patch

from app.services import ai_reply


def _db():
    return MagicMock()


def _patch_mode(mode: str):
    return patch.object(ai_reply, "_resolve_reply_language_mode", return_value=mode)


def test_tamil_answer_in_tamil_script_does_not_lock():
    db = _db()
    with _patch_mode("tanglish_escalate_tamil"):
        locked = ai_reply.record_tamil_lock_request(db, "lead-1", "t-1", "என்னோட பிறந்த டைம் தெரியாது")
    assert locked is False
    db.table.assert_not_called()


def test_tamil_script_request_locks():
    db = _db()
    with _patch_mode("tanglish_escalate_tamil"):
        locked = ai_reply.record_tamil_lock_request(db, "lead-1", "t-1", "தமிழ்ல பேசுங்க")
    assert locked is True
    db.table.assert_called_with("leads")


def test_romanized_request_does_not_lock():
    db = _db()
    with _patch_mode("tanglish_escalate_tamil"):
        locked = ai_reply.record_tamil_lock_request(db, "lead-1", "t-1", "tamil sollunga")
    assert locked is False
    db.table.assert_not_called()


def test_no_lock_when_tenant_is_not_on_escalate_mode():
    db = _db()
    with _patch_mode("tanglish"):
        locked = ai_reply.record_tamil_lock_request(db, "lead-1", "t-1", "தமிழ்ல பேசுங்க")
    assert locked is False
    db.table.assert_not_called()


def test_resolve_tamil_lock_returns_tamil_when_flag_already_set():
    db = _db()
    mode = ai_reply._resolve_tamil_lock(db, "lead-1", {"tamil_locked": True}, "anything")
    assert mode == "tamil"


def test_resolve_tamil_lock_stays_tanglish_for_plain_tamil_answer():
    db = _db()
    mode = ai_reply._resolve_tamil_lock(db, "lead-1", {"tamil_locked": False}, "சிதம்பரம்")
    assert mode == "tanglish"
