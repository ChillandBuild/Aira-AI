# Analytics API

> 14 nodes · cohesion 0.15

## Key Concepts

- **_window_aggregate()** (9 connections) — `backend/app/routes/analytics.py`
- **_caller_idle_minutes()** (6 connections) — `backend/app/routes/analytics.py`
- **datetime** (5 connections) — `backend/app/routes/analytics.py`
- **_is_connected()** (5 connections) — `backend/app/routes/analytics.py`
- **int** (3 connections) — `backend/app/routes/analytics.py`
- **qa_queue()** (3 connections) — `backend/app/routes/analytics.py`
- **bool** (1 connections) — `backend/app/routes/analytics.py`
- **float** (1 connections) — `backend/app/routes/analytics.py`
- **A call is 'connected' if it had talk time or a non-no_answer outcome.** (1 connections) — `backend/app/routes/analytics.py`
- **Idle minutes for one caller in [window_start, window_end): merged 'active'     i** (1 connections) — `backend/app/routes/analytics.py`
- **Aggregate metrics for a window, comparable in magnitude to the daily 'today'** (1 connections) — `backend/app/routes/analytics.py`
- **A call is 'connected' if it had talk time or a non-no_answer outcome.** (1 connections) — `backend/app/routes/analytics.py`
- **Idle minutes for one caller in [window_start, window_end): merged 'active'     i** (1 connections) — `backend/app/routes/analytics.py`
- **Aggregate metrics for a window, comparable in magnitude to the daily 'today'** (1 connections) — `backend/app/routes/analytics.py`

## Relationships

- [[Analytics API]] (9 shared connections)
- [[Calls API (TeleCMI dialer)]] (1 shared connections)

## Source Files

- `backend/app/routes/analytics.py`

## Audit Trail

- EXTRACTED: 38 (97%)
- INFERRED: 1 (3%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*