# Analytics API

> 14 nodes · cohesion 0.14

## Key Concepts

- **_range_params()** (10 connections) — `backend/app/routes/analytics.py`
- **inbound_analytics()** (8 connections) — `backend/app/routes/analytics.py`
- **messaging_analytics()** (7 connections) — `backend/app/routes/analytics.py`
- **MessagingAnalytics** (6 connections) — `frontend/lib/api.ts`
- **Return (window_start_utc, list_of_date_iso_strings) for a range value.** (1 connections) — `backend/app/routes/analytics.py`
- **Messaging analytics with optional channel filter and date range.** (1 connections) — `backend/app/routes/analytics.py`
- **New inbound leads acquired, split organic vs ad. Range: today|7d|30d.** (1 connections) — `backend/app/routes/analytics.py`
- **Return (window_start_utc, list_of_date_iso_strings) for a range value.** (1 connections) — `backend/app/routes/analytics.py`
- **Messaging analytics with optional channel filter and date range.** (1 connections) — `backend/app/routes/analytics.py`
- **New inbound leads acquired, split organic vs ad. Range: today|7d|30d.** (1 connections) — `backend/app/routes/analytics.py`
- **Messaging analytics with optional channel filter and date range.** (1 connections) — `backend/app/routes/analytics.py`
- **New inbound leads acquired, split organic vs ad. Range: today|7d|30d.** (1 connections) — `backend/app/routes/analytics.py`
- **Return (window_start_utc, list_of_date_iso_strings) for a range value.** (1 connections) — `backend/app/routes/analytics.py`
- **Messaging analytics with optional channel filter and date range.** (1 connections) — `backend/app/routes/analytics.py`

## Relationships

- [[Analytics API]] (10 shared connections)
- [[Calls API (TeleCMI dialer)]] (2 shared connections)
- [[Inbound Lead Reporting]] (1 shared connections)
- [[Analytics Page]] (1 shared connections)
- [[API Client (frontend)]] (1 shared connections)

## Source Files

- `backend/app/routes/analytics.py`
- `frontend/lib/api.ts`

## Audit Trail

- EXTRACTED: 38 (93%)
- INFERRED: 3 (7%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*