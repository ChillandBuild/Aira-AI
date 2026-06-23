# Broadcast Retry Service

> 22 nodes · cohesion 0.16

## Key Concepts

- **broadcast_retry.py** (11 connections) — `backend/app/services/broadcast_retry.py`
- **_process_chain()** (8 connections) — `backend/app/services/broadcast_retry.py`
- **_next_fire()** (6 connections) — `backend/app/services/broadcast_retry.py`
- **_eligible_leads()** (6 connections) — `backend/app/services/broadcast_retry.py`
- **process_due_retries()** (6 connections) — `backend/app/services/broadcast_retry.py`
- **_process_broadcast_retries()** (5 connections) — `backend/app/main.py`
- **_tenant_tz()** (4 connections) — `backend/app/services/broadcast_retry.py`
- **_parse_dt()** (4 connections) — `backend/app/services/broadcast_retry.py`
- **datetime** (4 connections) — `backend/app/services/broadcast_retry.py`
- **str** (3 connections) — `backend/app/services/broadcast_retry.py`
- **ZoneInfo** (3 connections) — `backend/app/services/broadcast_retry.py`
- **_parse_time()** (3 connections) — `backend/app/services/broadcast_retry.py`
- **_mark_completed()** (3 connections) — `backend/app/services/broadcast_retry.py`
- **dtime** (2 connections) — `backend/app/services/broadcast_retry.py`
- **APScheduler job: advance broadcast auto-retry chains that are due.** (1 connections) — `backend/app/main.py`
- **Broadcast auto-retry orchestrator.  Re-sends a broadcast's undelivered leads (Me** (1 connections) — `backend/app/services/broadcast_retry.py`
- **First occurrence of retry_time (tenant tz) that is >= last_sent + MIN_GAP_HOURS.** (1 connections) — `backend/app/services/broadcast_retry.py`
- **Rebuild the undelivered-lead subset for the next attempt, newest recipient row p** (1 connections) — `backend/app/services/broadcast_retry.py`
- **APScheduler entry — advance every active retry chain that is due.** (1 connections) — `backend/app/services/broadcast_retry.py`
- **APScheduler job: advance broadcast auto-retry chains that are due.** (1 connections) — `backend/app/main.py`
- **APScheduler entry — advance every active retry chain that is due.** (1 connections) — `backend/app/services/broadcast_retry.py`
- **APScheduler job: advance broadcast auto-retry chains that are due.** (1 connections) — `backend/app/main.py`

## Relationships

- [[App Entry & Schedulers]] (1 shared connections)
- [[Operator Console & Audit]] (1 shared connections)

## Source Files

- `backend/app/main.py`
- `backend/app/services/broadcast_retry.py`

## Audit Trail

- EXTRACTED: 73 (96%)
- INFERRED: 3 (4%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*