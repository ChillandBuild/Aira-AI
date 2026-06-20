# Broadcast Retry Service

> 15 nodes · cohesion 0.28

## Key Concepts

- **broadcast_retry.py** (11 connections) — `backend/app/services/broadcast_retry.py`
- **_process_chain()** (8 connections) — `backend/app/services/broadcast_retry.py`
- **_next_fire()** (6 connections) — `backend/app/services/broadcast_retry.py`
- **_eligible_leads()** (6 connections) — `backend/app/services/broadcast_retry.py`
- **_tenant_tz()** (4 connections) — `backend/app/services/broadcast_retry.py`
- **_parse_dt()** (4 connections) — `backend/app/services/broadcast_retry.py`
- **datetime** (4 connections) — `backend/app/services/broadcast_retry.py`
- **str** (3 connections) — `backend/app/services/broadcast_retry.py`
- **ZoneInfo** (3 connections) — `backend/app/services/broadcast_retry.py`
- **_parse_time()** (3 connections) — `backend/app/services/broadcast_retry.py`
- **_mark_completed()** (3 connections) — `backend/app/services/broadcast_retry.py`
- **dtime** (2 connections) — `backend/app/services/broadcast_retry.py`
- **Broadcast auto-retry orchestrator.  Re-sends a broadcast's undelivered leads (Me** (1 connections) — `backend/app/services/broadcast_retry.py`
- **First occurrence of retry_time (tenant tz) that is >= last_sent + MIN_GAP_HOURS.** (1 connections) — `backend/app/services/broadcast_retry.py`
- **Rebuild the undelivered-lead subset for the next attempt, newest recipient row p** (1 connections) — `backend/app/services/broadcast_retry.py`

## Relationships

- [[App Entry & Schedulers]] (2 shared connections)

## Source Files

- `backend/app/services/broadcast_retry.py`

## Audit Trail

- EXTRACTED: 60 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*