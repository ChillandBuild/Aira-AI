# Upload API

> 10 nodes · cohesion 0.20

## Key Concepts

- **refresh_broadcast_metrics()** (9 connections) — `backend/app/routes/upload.py`
- **_refresh_delivered_opened_timewindow()** (6 connections) — `backend/app/routes/upload.py`
- **Update delivered/opened counts via time-window fallback (legacy/compat).** (1 connections) — `backend/app/routes/upload.py`
- **Re-query delivery status for all broadcasts and update history.** (1 connections) — `backend/app/routes/upload.py`
- **Update delivered/opened counts via time-window fallback (legacy/compat).** (1 connections) — `backend/app/routes/upload.py`
- **Re-query delivery status for all broadcasts and update history.** (1 connections) — `backend/app/routes/upload.py`
- **Update delivered/opened counts via time-window fallback (legacy/compat).** (1 connections) — `backend/app/routes/upload.py`
- **Re-query delivery status for all broadcasts and update history.** (1 connections) — `backend/app/routes/upload.py`
- **Update delivered/opened counts via time-window fallback (legacy/compat).** (1 connections) — `backend/app/routes/upload.py`
- **Re-query delivery status for all broadcasts and update history.** (1 connections) — `backend/app/routes/upload.py`

## Relationships

- [[CSV Upload & Bulk Send]] (3 shared connections)
- [[Operator Console & Audit]] (1 shared connections)
- [[Upload API]] (1 shared connections)

## Source Files

- `backend/app/routes/upload.py`

## Audit Trail

- EXTRACTED: 22 (96%)
- INFERRED: 1 (4%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*