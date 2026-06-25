# Reengagement Service

> 24 nodes · cohesion 0.13

## Key Concepts

- **process_due_reengagements()** (10 connections) — `backend/app/services/reengagement_service.py`
- **_send_reengagement()** (10 connections) — `backend/app/services/reengagement_service.py`
- **reengagement_service.py** (7 connections) — `backend/app/services/reengagement_service.py`
- **_send_step_template()** (7 connections) — `backend/app/services/reengagement_service.py`
- **_process_reengagement_rules()** (6 connections) — `backend/app/main.py`
- **_lead_matches_sources()** (5 connections) — `backend/app/services/reengagement_service.py`
- **utcnow()** (4 connections) — `backend/app/services/reengagement_service.py`
- **_classify_source()** (4 connections) — `backend/app/services/reengagement_service.py`
- **trigger_now()** (3 connections) — `backend/app/routes/reengagement.py`
- **str** (3 connections) — `backend/app/services/reengagement_service.py`
- **bool** (3 connections) — `backend/app/services/reengagement_service.py`
- **datetime** (2 connections) — `backend/app/services/reengagement_service.py`
- **Map a lead to an acquisition-source bucket (ad referral wins over channel).** (2 connections) — `backend/app/services/reengagement_service.py`
- **APScheduler job: process due automated re-engagement steps.** (1 connections) — `backend/app/main.py`
- **int** (1 connections) — `backend/app/services/reengagement_service.py`
- **NULL/empty target_sources = all sources.** (1 connections) — `backend/app/services/reengagement_service.py`
- **Query and process all pending re-engagement steps for all tenants.** (1 connections) — `backend/app/services/reengagement_service.py`
- **Send a template message for a step and write message + reengagement logs.** (1 connections) — `backend/app/services/reengagement_service.py`
- **Send the re-engagement message to a single lead and write a log entry.** (1 connections) — `backend/app/services/reengagement_service.py`
- **APScheduler job: process due automated re-engagement steps.** (1 connections) — `backend/app/main.py`
- **APScheduler job: process due automated re-engagement steps.** (1 connections) — `backend/app/main.py`
- **APScheduler job: process due automated re-engagement steps.** (1 connections) — `backend/app/main.py`
- **Send a template message for a step and write message + reengagement logs.** (1 connections) — `backend/app/services/reengagement_service.py`
- **Send the re-engagement message to a single lead and write a log entry.** (1 connections) — `backend/app/services/reengagement_service.py`

## Relationships

- [[Operator Console & Audit]] (3 shared connections)
- [[App Entry & Schedulers]] (1 shared connections)
- [[Meta Cloud API Client]] (1 shared connections)
- [[Segments API]] (1 shared connections)
- [[Ai Reply Service]] (1 shared connections)

## Source Files

- `backend/app/main.py`
- `backend/app/routes/reengagement.py`
- `backend/app/services/reengagement_service.py`

## Audit Trail

- EXTRACTED: 68 (88%)
- INFERRED: 9 (12%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*