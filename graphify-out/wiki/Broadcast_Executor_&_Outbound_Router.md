# Broadcast Executor & Outbound Router

> 10 nodes · cohesion 0.38

## Key Concepts

- **execute_broadcast()** (13 connections) — `backend/app/services/broadcast_executor.py`
- **broadcast_executor.py** (6 connections) — `backend/app/services/broadcast_executor.py`
- **str** (4 connections) — `backend/app/services/broadcast_executor.py`
- **_meta_error_detail()** (4 connections) — `backend/app/services/broadcast_executor.py`
- **_normalize_phone()** (3 connections) — `backend/app/services/broadcast_executor.py`
- **_clean_text()** (3 connections) — `backend/app/services/broadcast_executor.py`
- **_finish()** (3 connections) — `backend/app/services/broadcast_executor.py`
- **Human-readable Meta error for the failed CSV — '(#code) message', else trimmed r** (2 connections) — `backend/app/services/broadcast_executor.py`
- **Execute a scheduled broadcast row from the scheduled_broadcasts table.** (1 connections) — `backend/app/services/broadcast_executor.py`
- **Run a single scheduled_broadcasts row and return a result dict.** (1 connections) — `backend/app/services/broadcast_executor.py`

## Relationships

- [[Calls API (TeleCMI dialer)]] (1 shared connections)
- [[App Entry & Schedulers]] (1 shared connections)
- [[Razorpay Payments]] (1 shared connections)
- [[Meta Cloud API Client]] (1 shared connections)

## Source Files

- `backend/app/services/broadcast_executor.py`

## Audit Trail

- EXTRACTED: 34 (85%)
- INFERRED: 6 (15%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*