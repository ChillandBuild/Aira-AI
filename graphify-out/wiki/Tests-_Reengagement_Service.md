# Tests: Reengagement Service

> 17 nodes · cohesion 0.29

## Key Concepts

- **test_reengagement_service.py** (11 connections) — `backend/tests/test_reengagement_service.py`
- **_lead()** (10 connections) — `backend/tests/test_reengagement_service.py`
- **_make_db()** (9 connections) — `backend/tests/test_reengagement_service.py`
- **_step()** (8 connections) — `backend/tests/test_reengagement_service.py`
- **test_freeform_window_closed_fallback_send_fails_logs_failed()** (5 connections) — `backend/tests/test_reengagement_service.py`
- **test_undeliverable_lead_is_skipped_no_send_no_log()** (5 connections) — `backend/tests/test_reengagement_service.py`
- **test_opted_out_lead_is_skipped_no_send_no_log()** (5 connections) — `backend/tests/test_reengagement_service.py`
- **_now_iso()** (4 connections) — `backend/tests/test_reengagement_service.py`
- **test_freeform_window_open_sends_freeform()** (4 connections) — `backend/tests/test_reengagement_service.py`
- **test_freeform_window_closed_with_fallback_sends_template()** (4 connections) — `backend/tests/test_reengagement_service.py`
- **test_freeform_window_closed_no_fallback_skips()** (4 connections) — `backend/tests/test_reengagement_service.py`
- **test_template_step_always_sends_template()** (4 connections) — `backend/tests/test_reengagement_service.py`
- **float** (2 connections) — `backend/tests/test_reengagement_service.py`
- **str** (1 connections) — `backend/tests/test_reengagement_service.py`
- **Supabase mock that records every reengagement_logs insert into captured_logs.** (1 connections) — `backend/tests/test_reengagement_service.py`
- **A lead Meta can't deliver to (whatsapp_undeliverable) must never be re-engaged** (1 connections) — `backend/tests/test_reengagement_service.py`
- **A lead who has opted out must never be re-engaged and must not appear     in re-** (1 connections) — `backend/tests/test_reengagement_service.py`

## Relationships

- [[AI Reply Pipeline (Groq)]] (1 shared connections)

## Source Files

- `backend/tests/test_reengagement_service.py`

## Audit Trail

- EXTRACTED: 78 (99%)
- INFERRED: 1 (1%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*