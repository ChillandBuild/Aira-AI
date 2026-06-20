# Growth Service

> 18 nodes · cohesion 0.24

## Key Concepts

- **record_stage_event()** (14 connections) — `backend/app/services/growth.py`
- **sync_follow_up_jobs()** (14 connections) — `backend/app/services/growth.py`
- **growth.py** (10 connections) — `backend/app/services/growth.py`
- **run_due_follow_ups()** (9 connections) — `backend/app/routes/follow_ups.py`
- **get_or_create_campaign()** (9 connections) — `backend/app/services/growth.py`
- **str** (8 connections) — `backend/app/services/growth.py`
- **build_follow_up_summary()** (7 connections) — `backend/app/services/growth.py`
- **build_ad_performance()** (6 connections) — `backend/app/services/growth.py`
- **utcnow()** (5 connections) — `backend/app/services/growth.py`
- **Any** (5 connections) — `backend/app/services/growth.py`
- **stage_depth()** (4 connections) — `backend/app/services/growth.py`
- **cancel_pending_follow_ups()** (4 connections) — `backend/app/services/growth.py`
- **datetime** (3 connections) — `backend/app/services/growth.py`
- **normalize_platform()** (3 connections) — `backend/app/services/growth.py`
- **int** (1 connections) — `backend/app/routes/follow_ups.py`
- **int** (1 connections) — `backend/app/services/growth.py`
- **float** (1 connections) — `backend/app/services/growth.py`
- **bool** (1 connections) — `backend/app/services/growth.py`

## Relationships

- [[Calls API (TeleCMI dialer)]] (8 shared connections)
- [[Leads API]] (6 shared connections)
- [[Follow-ups & Callback Scheduling API]] (3 shared connections)
- [[AI Reply Pipeline (Groq)]] (3 shared connections)
- [[Booking Flow]] (3 shared connections)
- [[CSV Upload & Bulk Send]] (3 shared connections)
- [[Facebook / Webhook Verification]] (2 shared connections)
- [[Instagram Channel]] (2 shared connections)
- [[Razorpay Payments]] (1 shared connections)
- [[Assignment Service]] (1 shared connections)
- [[Analytics API]] (1 shared connections)

## Source Files

- `backend/app/routes/follow_ups.py`
- `backend/app/services/growth.py`

## Audit Trail

- EXTRACTED: 70 (67%)
- INFERRED: 35 (33%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*