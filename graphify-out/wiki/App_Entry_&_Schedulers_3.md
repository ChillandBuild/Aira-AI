# App Entry & Schedulers

> 7 nodes · cohesion 0.29

## Key Concepts

- **_process_scheduled_broadcasts()** (7 connections) — `backend/app/main.py`
- **_process_automation_waits()** (3 connections) — `backend/app/main.py`
- **APScheduler job: fire scheduled_broadcasts rows whose fire_at has passed.** (2 connections) — `backend/app/main.py`
- **APScheduler job: fire scheduled_broadcasts rows whose fire_at has passed.** (1 connections) — `backend/app/main.py`
- **APScheduler job: fire scheduled_broadcasts rows whose fire_at has passed.** (1 connections) — `backend/app/main.py`
- **APScheduler job: resume automation wait-step executions that are due.** (1 connections) — `backend/app/main.py`
- **APScheduler job: fire scheduled_broadcasts rows whose fire_at has passed.** (1 connections) — `backend/app/main.py`

## Relationships

- [[App Entry & Schedulers]] (2 shared connections)
- [[Calls API (TeleCMI dialer)]] (1 shared connections)
- [[Broadcast Executor & Outbound Router]] (1 shared connections)

## Source Files

- `backend/app/main.py`

## Audit Trail

- EXTRACTED: 14 (88%)
- INFERRED: 2 (12%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*