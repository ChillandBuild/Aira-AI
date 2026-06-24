# Calls API

> 11 nodes · cohesion 0.24

## Key Concepts

- **calls.py** (24 connections) — `backend/app/routes/calls.py`
- **set_outcome()** (11 connections) — `backend/app/routes/calls.py`
- **next_lead()** (6 connections) — `backend/app/routes/calls.py`
- **get_call_log()** (4 connections) — `backend/app/routes/calls.py`
- **delete_call_log()** (4 connections) — `backend/app/routes/calls.py`
- **OutcomeUpdate** (3 connections) — `backend/app/routes/calls.py`
- **recent_by_leads()** (3 connections) — `backend/app/routes/calls.py`
- **UUID** (3 connections) — `backend/app/routes/calls.py`
- **stats_today()** (2 connections) — `backend/app/routes/calls.py`
- **get_assignment_mode()** (2 connections) — `backend/app/routes/calls.py`
- **get_pending_wrapups()** (2 connections) — `backend/app/routes/calls.py`

## Relationships

- [[Operator Console & Audit]] (11 shared connections)
- [[Calls API (TeleCMI dialer)]] (7 shared connections)
- [[Calls API]] (5 shared connections)
- [[Assignment Service]] (4 shared connections)
- [[Growth Service]] (2 shared connections)
- [[Config]] (1 shared connections)
- [[Templates API]] (1 shared connections)
- [[App Entry & Schedulers]] (1 shared connections)
- [[Pydantic Schemas]] (1 shared connections)
- [[Notify Service]] (1 shared connections)

## Source Files

- `backend/app/routes/calls.py`

## Audit Trail

- EXTRACTED: 44 (69%)
- INFERRED: 20 (31%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*