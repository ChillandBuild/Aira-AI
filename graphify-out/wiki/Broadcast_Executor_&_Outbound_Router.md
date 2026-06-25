# Broadcast Executor & Outbound Router

> 27 nodes · cohesion 0.11

## Key Concepts

- **execute_broadcast()** (13 connections) — `backend/app/services/broadcast_executor.py`
- **_process_scheduled_broadcasts()** (8 connections) — `backend/app/main.py`
- **increment_send_count()** (8 connections) — `/Users/prem/Documents/Aira Ai/backend/app/services/outbound_router.py`
- **get_best_number()** (7 connections) — `/Users/prem/Documents/Aira Ai/backend/app/services/outbound_router.py`
- **broadcast_executor.py** (6 connections) — `backend/app/services/broadcast_executor.py`
- **str** (4 connections) — `backend/app/services/broadcast_executor.py`
- **_meta_error_detail()** (4 connections) — `backend/app/services/broadcast_executor.py`
- **outbound_router.py** (4 connections) — `/Users/prem/Documents/Aira Ai/backend/app/services/outbound_router.py`
- **_warmup_daily_cap()** (4 connections) — `/Users/prem/Documents/Aira Ai/backend/app/services/outbound_router.py`
- **_normalize_phone()** (3 connections) — `backend/app/services/broadcast_executor.py`
- **_clean_text()** (3 connections) — `backend/app/services/broadcast_executor.py`
- **_finish()** (3 connections) — `backend/app/services/broadcast_executor.py`
- **_process_automation_waits()** (3 connections) — `backend/app/main.py`
- **Human-readable Meta error for the failed CSV — '(#code) message', else trimmed r** (2 connections) — `backend/app/services/broadcast_executor.py`
- **int** (2 connections) — `/Users/prem/Documents/Aira Ai/backend/app/services/outbound_router.py`
- **str** (2 connections) — `/Users/prem/Documents/Aira Ai/backend/app/services/outbound_router.py`
- **reset_daily_counts()** (2 connections) — `/Users/prem/Documents/Aira Ai/backend/app/services/outbound_router.py`
- **APScheduler job: fire scheduled_broadcasts rows whose fire_at has passed.** (2 connections) — `backend/app/main.py`
- **int** (2 connections) — `backend/app/services/outbound_router.py`
- **str** (2 connections) — `backend/app/services/outbound_router.py`
- **APScheduler job: fire scheduled_broadcasts rows whose fire_at has passed.** (1 connections) — `backend/app/main.py`
- **Execute a scheduled broadcast row from the scheduled_broadcasts table.** (1 connections) — `backend/app/services/broadcast_executor.py`
- **Run a single scheduled_broadcasts row and return a result dict.** (1 connections) — `backend/app/services/broadcast_executor.py`
- **APScheduler job: fire scheduled_broadcasts rows whose fire_at has passed.** (1 connections) — `backend/app/main.py`
- **APScheduler job: fire scheduled_broadcasts rows whose fire_at has passed.** (1 connections) — `backend/app/main.py`
- *... and 2 more nodes in this community*

## Relationships

- [[Operator Console & Audit]] (5 shared connections)
- [[App Entry & Schedulers]] (2 shared connections)
- [[CSV Upload & Bulk Send]] (2 shared connections)
- [[Ai Reply Service]] (1 shared connections)
- [[Meta Cloud API Client]] (1 shared connections)

## Source Files

- `/Users/prem/Documents/Aira Ai/backend/app/services/outbound_router.py`
- `backend/app/main.py`
- `backend/app/services/broadcast_executor.py`
- `backend/app/services/outbound_router.py`

## Audit Trail

- EXTRACTED: 76 (84%)
- INFERRED: 15 (16%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*