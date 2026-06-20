# App Entry & Schedulers

> 15 nodes · cohesion 0.13

## Key Concepts

- **main.py** (16 connections) — `backend/app/main.py`
- **_process_reengagement_rules()** (5 connections) — `backend/app/main.py`
- **_sweep_unassigned_leads()** (5 connections) — `backend/app/main.py`
- **_record_scheduler_event()** (4 connections) — `backend/app/main.py`
- **lifespan()** (2 connections) — `backend/app/main.py`
- **health()** (2 connections) — `backend/app/main.py`
- **APScheduler job: process due automated re-engagement steps.** (1 connections) — `backend/app/main.py`
- **APScheduler job: state-based safety net that assigns any unassigned lead     who** (1 connections) — `backend/app/main.py`
- **Persist every job run to scheduler_runs for the operator Scheduler Health     vi** (1 connections) — `backend/app/main.py`
- **trigger_error()** (1 connections) — `backend/app/main.py`
- **Persist every job run to scheduler_runs for the operator Scheduler Health     vi** (1 connections) — `backend/app/main.py`
- **APScheduler job: process due automated re-engagement steps.** (1 connections) — `backend/app/main.py`
- **APScheduler job: state-based safety net that assigns any unassigned lead     who** (1 connections) — `backend/app/main.py`
- **APScheduler job: process due automated re-engagement steps.** (1 connections) — `backend/app/main.py`
- **APScheduler job: state-based safety net that assigns any unassigned lead     who** (1 connections) — `backend/app/main.py`

## Relationships

- [[App Entry & Schedulers]] (6 shared connections)
- [[Assignment Service]] (2 shared connections)
- [[Tenant]] (2 shared connections)
- [[Calls API (TeleCMI dialer)]] (2 shared connections)
- [[Config]] (1 shared connections)
- [[Contact Recycler Service]] (1 shared connections)
- [[Reengagement Service]] (1 shared connections)

## Source Files

- `backend/app/main.py`

## Audit Trail

- EXTRACTED: 39 (91%)
- INFERRED: 4 (9%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*