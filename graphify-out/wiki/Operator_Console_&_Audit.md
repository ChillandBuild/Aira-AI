# Operator Console & Audit

> 50 nodes · cohesion 0.08

## Key Concepts

- **HTTPException** (153 connections)
- **operator.py** (26 connections) — `backend/app/routes/operator.py`
- **str** (17 connections) — `backend/app/routes/operator.py`
- **record_audit_event()** (12 connections) — `backend/app/services/audit_log.py`
- **wipe_leads()** (9 connections) — `backend/app/routes/operator.py`
- **reengagement.py** (9 connections) — `backend/app/routes/reengagement.py`
- **update_features()** (6 connections) — `backend/app/routes/operator.py`
- **update_status()** (6 connections) — `backend/app/routes/operator.py`
- **operator_me()** (5 connections) — `backend/app/routes/operator.py`
- **create_client()** (5 connections) — `backend/app/routes/operator.py`
- **reset_password()** (5 connections) — `backend/app/routes/operator.py`
- **clear_data()** (5 connections) — `backend/app/routes/operator.py`
- **get_retry_timeline()** (5 connections) — `backend/app/routes/upload.py`
- **CreateClientPayload** (4 connections) — `backend/app/routes/operator.py`
- **client_overview()** (4 connections) — `backend/app/routes/operator.py`
- **client_config()** (4 connections) — `backend/app/routes/operator.py`
- **client_health()** (4 connections) — `backend/app/routes/operator.py`
- **client_team()** (4 connections) — `backend/app/routes/operator.py`
- **client_dashboard_inbox()** (4 connections) — `backend/app/routes/operator.py`
- **client_dashboard_leads()** (4 connections) — `backend/app/routes/operator.py`
- **client_dashboard_templates()** (4 connections) — `backend/app/routes/operator.py`
- **client_dashboard_numbers()** (4 connections) — `backend/app/routes/operator.py`
- **client_dashboard_knowledge()** (4 connections) — `backend/app/routes/operator.py`
- **client_dashboard_analytics()** (4 connections) — `backend/app/routes/operator.py`
- **client_dashboard_telecalling()** (4 connections) — `backend/app/routes/operator.py`
- *... and 25 more nodes in this community*

## Relationships

- [[Calls API (TeleCMI dialer)]] (41 shared connections)
- [[Leads API]] (20 shared connections)
- [[Meta Cloud API Client]] (13 shared connections)
- [[Tenant]] (9 shared connections)
- [[CSV Upload & Bulk Send]] (8 shared connections)
- [[Team API]] (7 shared connections)
- [[Templates API]] (7 shared connections)
- [[App Settings API]] (6 shared connections)
- [[Callers CRUD & Coaching]] (6 shared connections)
- [[Meta Cloud Service]] (6 shared connections)
- [[Ai Tune API]] (4 shared connections)
- [[Call Scripts API]] (4 shared connections)

## Source Files

- `backend/app/routes/operator.py`
- `backend/app/routes/reengagement.py`
- `backend/app/routes/upload.py`
- `backend/app/services/audit_log.py`

## Audit Trail

- EXTRACTED: 166 (45%)
- INFERRED: 201 (55%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*