# Leads API

> 11 nodes · cohesion 0.18

## Key Concepts

- **takeover_lead()** (12 connections) — `backend/app/routes/leads.py`
- **is_caller_on_call()** (9 connections) — `backend/app/services/assignment.py`
- **Allow a telecaller to claim an overdue callback from an unavailable caller.** (1 connections) — `backend/app/routes/leads.py`
- **Return True if the caller has an active call log (status in ('initiated', 'in_pr** (1 connections) — `backend/app/services/assignment.py`
- **Allow a telecaller to claim an overdue callback from an unavailable caller.** (1 connections) — `backend/app/routes/leads.py`
- **Return True if the caller has an active call log (status in ('initiated', 'in_pr** (1 connections) — `backend/app/services/assignment.py`
- **Allow a telecaller to claim an overdue callback from an unavailable caller.** (1 connections) — `backend/app/routes/leads.py`
- **Return True if the caller has an active call log (status in ('initiated', 'in_pr** (1 connections) — `backend/app/services/assignment.py`
- **Allow a telecaller to claim an overdue callback from an unavailable caller.** (1 connections) — `backend/app/routes/leads.py`
- **Return True if the caller has an active call log (status in ('initiated', 'in_pr** (1 connections) — `backend/app/services/assignment.py`
- **Allow a telecaller to claim/take over an overdue callback lead from another call** (1 connections) — `backend/app/routes/leads.py`

## Relationships

- [[Telecaller Assignment Engine]] (3 shared connections)
- [[Operator Console & Audit]] (2 shared connections)
- [[Leads API]] (2 shared connections)
- [[Notify Service]] (2 shared connections)
- [[Assignment Service]] (1 shared connections)

## Source Files

- `backend/app/routes/leads.py`
- `backend/app/services/assignment.py`

## Audit Trail

- EXTRACTED: 23 (77%)
- INFERRED: 7 (23%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*