# Operator API

> 12 nodes · cohesion 0.18

## Key Concepts

- **record_audit_event()** (12 connections) — `backend/app/services/audit_log.py`
- **wipe_leads()** (10 connections) — `backend/app/routes/operator.py`
- **_sanitize()** (3 connections) — `backend/app/services/audit_log.py`
- **audit_log.py** (2 connections) — `backend/app/services/audit_log.py`
- **Delete all leads and lead-related data for a tenant. Irreversible.** (1 connections) — `backend/app/routes/operator.py`
- **Any** (1 connections) — `backend/app/services/audit_log.py`
- **str** (1 connections) — `backend/app/services/audit_log.py`
- **Best-effort append-only audit log.      Audit logging should never break the use** (1 connections) — `backend/app/services/audit_log.py`
- **Delete all leads and lead-related data for a tenant. Irreversible.** (1 connections) — `backend/app/routes/operator.py`
- **Delete all leads and lead-related data for a tenant. Irreversible.** (1 connections) — `backend/app/routes/operator.py`
- **Delete all leads and lead-related data for a tenant. Irreversible.** (1 connections) — `backend/app/routes/operator.py`
- **Delete all leads and lead-related data for a tenant. Irreversible.** (1 connections) — `backend/app/routes/operator.py`

## Relationships

- [[Operator Console & Audit]] (9 shared connections)
- [[App Settings API]] (2 shared connections)

## Source Files

- `backend/app/routes/operator.py`
- `backend/app/services/audit_log.py`

## Audit Trail

- EXTRACTED: 24 (69%)
- INFERRED: 11 (31%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*