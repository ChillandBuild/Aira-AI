# Calls API (TeleCMI dialer)

> 73 nodes · cohesion 0.05

## Key Concepts

- **get_supabase()** (289 connections) — `/Users/prem/Documents/Aira Ai/backend/app/db/supabase.py`
- **get_setting()** (38 connections) — `backend/app/config_dynamic.py`
- **calls.py** (23 connections) — `backend/app/routes/calls.py`
- **telecmi_cdr()** (15 connections) — `backend/app/routes/calls.py`
- **set_outcome()** (11 connections) — `backend/app/routes/calls.py`
- **_run_summarization()** (10 connections) — `backend/app/routes/calls.py`
- **InitiateCall** (9 connections) — `backend/app/routes/calls.py`
- **initiate_call()** (8 connections) — `backend/app/routes/calls.py`
- **_verify_telecmi_webhook_secret()** (8 connections) — `backend/app/routes/calls.py`
- **str** (8 connections) — `backend/app/routes/calls.py`
- **telecmi_live_events()** (8 connections) — `backend/app/routes/calls.py`
- **backfill_summaries()** (8 connections) — `backend/app/routes/calls.py`
- **sync_template_status()** (8 connections) — `backend/app/routes/templates.py`
- **sync_templates_from_meta()** (8 connections) — `backend/app/routes/templates.py`
- **update_pickup_rate()** (8 connections) — `/Users/prem/Documents/Aira Ai/backend/app/services/voice_router.py`
- **_process_telecmi_recording()** (7 connections) — `backend/app/routes/calls.py`
- **generate_summary()** (7 connections) — `backend/app/routes/calls.py`
- **_extract_call_log_id()** (6 connections) — `backend/app/routes/calls.py`
- **next_lead()** (6 connections) — `backend/app/routes/calls.py`
- **delete_template()** (6 connections) — `backend/app/routes/templates.py`
- **get_best_voice_number()** (6 connections) — `/Users/prem/Documents/Aira Ai/backend/app/services/voice_router.py`
- **increment_voice_call_count()** (6 connections) — `/Users/prem/Documents/Aira Ai/backend/app/services/voice_router.py`
- **report_spam_flag()** (6 connections) — `/Users/prem/Documents/Aira Ai/backend/app/services/voice_router.py`
- **voice_router.py** (5 connections) — `/Users/prem/Documents/Aira Ai/backend/app/services/voice_router.py`
- **my_performance()** (4 connections) — `backend/app/routes/callers.py`
- *... and 48 more nodes in this community*

## Relationships

- [[Operator Console & Audit]] (41 shared connections)
- [[Leads API]] (24 shared connections)
- [[Callers CRUD & Coaching]] (18 shared connections)
- [[Booking Flow]] (17 shared connections)
- [[Templates API]] (14 shared connections)
- [[Assignment Service]] (13 shared connections)
- [[Tenant]] (12 shared connections)
- [[Analytics API]] (11 shared connections)
- [[Upload API]] (11 shared connections)
- [[Ai Tune API]] (8 shared connections)
- [[Knowledge Base (pgvector RAG)]] (8 shared connections)
- [[Growth Service]] (8 shared connections)

## Source Files

- `/Users/prem/Documents/Aira Ai/backend/app/db/supabase.py`
- `/Users/prem/Documents/Aira Ai/backend/app/services/voice_router.py`
- `backend/app/config_dynamic.py`
- `backend/app/routes/callers.py`
- `backend/app/routes/calls.py`
- `backend/app/routes/conversations.py`
- `backend/app/routes/operator.py`
- `backend/app/routes/templates.py`
- `backend/app/services/voice_router.py`

## Audit Trail

- EXTRACTED: 223 (37%)
- INFERRED: 374 (63%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*