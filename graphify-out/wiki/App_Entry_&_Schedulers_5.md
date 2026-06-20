# App Entry & Schedulers

> 6 nodes · cohesion 0.33

## Key Concepts

- **process_due_retries()** (6 connections) — `backend/app/services/broadcast_retry.py`
- **_process_broadcast_retries()** (4 connections) — `backend/app/main.py`
- **APScheduler job: advance broadcast auto-retry chains that are due.** (1 connections) — `backend/app/main.py`
- **APScheduler entry — advance every active retry chain that is due.** (1 connections) — `backend/app/services/broadcast_retry.py`
- **APScheduler entry — advance every active retry chain that is due.** (1 connections) — `backend/app/services/broadcast_retry.py`
- **APScheduler job: advance broadcast auto-retry chains that are due.** (1 connections) — `backend/app/main.py`

## Relationships

- [[Broadcast Retry Service]] (2 shared connections)
- [[App Entry & Schedulers]] (1 shared connections)
- [[Calls API (TeleCMI dialer)]] (1 shared connections)

## Source Files

- `backend/app/main.py`
- `backend/app/services/broadcast_retry.py`

## Audit Trail

- EXTRACTED: 11 (79%)
- INFERRED: 3 (21%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*