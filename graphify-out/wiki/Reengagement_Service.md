# Reengagement Service

> 18 nodes · cohesion 0.19

## Key Concepts

- **process_due_reengagements()** (10 connections) — `backend/app/services/reengagement_service.py`
- **_send_reengagement()** (10 connections) — `backend/app/services/reengagement_service.py`
- **reengagement_service.py** (7 connections) — `backend/app/services/reengagement_service.py`
- **_send_step_template()** (7 connections) — `backend/app/services/reengagement_service.py`
- **_lead_matches_sources()** (5 connections) — `backend/app/services/reengagement_service.py`
- **utcnow()** (4 connections) — `backend/app/services/reengagement_service.py`
- **_classify_source()** (4 connections) — `backend/app/services/reengagement_service.py`
- **str** (3 connections) — `backend/app/services/reengagement_service.py`
- **bool** (3 connections) — `backend/app/services/reengagement_service.py`
- **datetime** (2 connections) — `backend/app/services/reengagement_service.py`
- **Map a lead to an acquisition-source bucket (ad referral wins over channel).** (2 connections) — `backend/app/services/reengagement_service.py`
- **int** (1 connections) — `backend/app/services/reengagement_service.py`
- **NULL/empty target_sources = all sources.** (1 connections) — `backend/app/services/reengagement_service.py`
- **Query and process all pending re-engagement steps for all tenants.** (1 connections) — `backend/app/services/reengagement_service.py`
- **Send a template message for a step and write message + reengagement logs.** (1 connections) — `backend/app/services/reengagement_service.py`
- **Send the re-engagement message to a single lead and write a log entry.** (1 connections) — `backend/app/services/reengagement_service.py`
- **Send a template message for a step and write message + reengagement logs.** (1 connections) — `backend/app/services/reengagement_service.py`
- **Send the re-engagement message to a single lead and write a log entry.** (1 connections) — `backend/app/services/reengagement_service.py`

## Relationships

- [[Calls API (TeleCMI dialer)]] (1 shared connections)
- [[App Entry & Schedulers]] (1 shared connections)
- [[Operator Console & Audit]] (1 shared connections)
- [[Meta Cloud API Client]] (1 shared connections)
- [[Booking Flow]] (1 shared connections)
- [[Razorpay Payments]] (1 shared connections)

## Source Files

- `backend/app/services/reengagement_service.py`

## Audit Trail

- EXTRACTED: 58 (91%)
- INFERRED: 6 (9%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*