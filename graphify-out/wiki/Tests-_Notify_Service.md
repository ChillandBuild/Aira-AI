# Tests: Notify Service

> 9 nodes · cohesion 0.39

## Key Concepts

- **test_notify_service.py** (8 connections) — `backend/tests/test_notify_service.py`
- **_make_db()** (7 connections) — `backend/tests/test_notify_service.py`
- **test_notify_user_inserts_one_row()** (2 connections) — `backend/tests/test_notify_service.py`
- **test_notify_user_dedupe_skips_when_unread_exists()** (2 connections) — `backend/tests/test_notify_service.py`
- **test_notify_pool_fans_out_to_active_callers_and_owner()** (2 connections) — `backend/tests/test_notify_service.py`
- **test_notify_pool_excludes_given_user()** (2 connections) — `backend/tests/test_notify_service.py`
- **test_notify_never_raises_on_db_error()** (2 connections) — `backend/tests/test_notify_service.py`
- **test_notify_assigned_caller_of_reply_skips_when_unassigned()** (2 connections) — `backend/tests/test_notify_service.py`
- **test_notify_assigned_caller_of_reply_notifies_assigned_caller()** (2 connections) — `backend/tests/test_notify_service.py`

## Relationships

- [[AI Reply Pipeline (Groq)]] (1 shared connections)

## Source Files

- `backend/tests/test_notify_service.py`

## Audit Trail

- EXTRACTED: 28 (97%)
- INFERRED: 1 (3%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*