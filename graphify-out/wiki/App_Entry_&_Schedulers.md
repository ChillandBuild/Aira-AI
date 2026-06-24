# App Entry & Schedulers

> 42 nodes · cohesion 0.06

## Key Concepts

- **FastAPI** (46 connections) — `backend/app/main.py`
- **main.py** (18 connections) — `backend/app/main.py`
- **_check_token_health()** (8 connections) — `backend/app/main.py`
- **onboarding.py** (6 connections) — `backend/app/routes/onboarding.py`
- **segments.py** (6 connections) — `backend/app/routes/segments.py`
- **upsert_template()** (6 connections) — `backend/app/routes/segments.py`
- **_sync_all_number_quality()** (5 connections) — `backend/app/main.py`
- **_record_scheduler_event()** (5 connections) — `backend/app/main.py`
- **create_tenant()** (5 connections) — `backend/app/routes/onboarding.py`
- **broadcast_to_segment()** (5 connections) — `backend/app/routes/segments.py`
- **list_incidents()** (4 connections) — `backend/app/routes/incidents.py`
- **_ensure_templates()** (4 connections) — `backend/app/routes/segments.py`
- **str** (4 connections) — `backend/app/routes/segments.py`
- **list_templates()** (4 connections) — `backend/app/routes/segments.py`
- **_create_token_incident()** (3 connections) — `backend/app/main.py`
- **_seed_app_settings()** (3 connections) — `backend/app/routes/onboarding.py`
- **CreateTenantPayload** (3 connections) — `backend/app/routes/onboarding.py`
- **TemplateUpdate** (3 connections) — `backend/app/routes/segments.py`
- **system.py** (3 connections) — `backend/app/routes/system.py`
- **system_admin.py** (2 connections) — `/Users/prem/Documents/Aira Ai/backend/app/dependencies/system_admin.py`
- **lifespan()** (2 connections) — `backend/app/main.py`
- **health()** (2 connections) — `backend/app/main.py`
- **APScheduler job: reassign overdue callbacks from away callers.** (2 connections) — `backend/app/main.py`
- **incidents.py** (2 connections) — `backend/app/routes/incidents.py`
- **messages.py** (2 connections) — `/Users/prem/Documents/Aira Ai/backend/app/routes/messages.py`
- *... and 17 more nodes in this community*

## Relationships

- [[Operator Console & Audit]] (18 shared connections)
- [[Assignment Service]] (3 shared connections)
- [[Templates API]] (3 shared connections)
- [[Config]] (2 shared connections)
- [[App Entry & Schedulers]] (2 shared connections)
- [[Broadcast Executor & Outbound Router]] (2 shared connections)
- [[Meta Cloud API Client]] (2 shared connections)
- [[Inbound Lead Reporting]] (2 shared connections)
- [[Facebook / Webhook Verification]] (2 shared connections)
- [[Instagram Channel]] (2 shared connections)
- [[API Client (frontend)]] (2 shared connections)
- [[Pydantic Schemas]] (2 shared connections)

## Source Files

- `/Users/prem/Documents/Aira Ai/backend/app/dependencies/system_admin.py`
- `/Users/prem/Documents/Aira Ai/backend/app/routes/messages.py`
- `backend/app/main.py`
- `backend/app/routes/incidents.py`
- `backend/app/routes/onboarding.py`
- `backend/app/routes/segments.py`
- `backend/app/routes/system.py`
- `frontend/lib/api.ts`

## Audit Trail

- EXTRACTED: 156 (90%)
- INFERRED: 17 (10%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*