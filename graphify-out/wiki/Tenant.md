# Tenant

> 33 nodes · cohesion 0.07

## Key Concepts

- **FastAPI** (47 connections) — `backend/app/main.py`
- **razorpay_webhook()** (8 connections) — `backend/app/routes/bookings.py`
- **list_incidents()** (6 connections) — `/Users/prem/Documents/Aira Ai/backend/app/routes/incidents.py`
- **tenant.py** (5 connections) — `backend/app/dependencies/tenant.py`
- **onboarding.py** (5 connections) — `/Users/prem/Documents/Aira Ai/backend/app/routes/onboarding.py`
- **get_tenant_id()** (4 connections) — `backend/app/dependencies/tenant.py`
- **get_tenant_and_role()** (4 connections) — `backend/app/dependencies/tenant.py`
- **get_owner_tenant_id()** (4 connections) — `backend/app/dependencies/tenant.py`
- **bookings.py** (4 connections) — `backend/app/routes/bookings.py`
- **list_bookings()** (4 connections) — `backend/app/routes/bookings.py`
- **get_booking()** (4 connections) — `backend/app/routes/bookings.py`
- **create_tenant()** (4 connections) — `/Users/prem/Documents/Aira Ai/backend/app/routes/onboarding.py`
- **get_system_admin()** (3 connections) — `/Users/prem/Documents/Aira Ai/backend/app/dependencies/system_admin.py`
- **CreateTenantPayload** (3 connections) — `/Users/prem/Documents/Aira Ai/backend/app/routes/onboarding.py`
- **system.py** (3 connections) — `/Users/prem/Documents/Aira Ai/backend/app/routes/system.py`
- **system_admin.py** (2 connections) — `/Users/prem/Documents/Aira Ai/backend/app/dependencies/system_admin.py`
- **str** (2 connections) — `backend/app/dependencies/tenant.py`
- **require_owner()** (2 connections) — `backend/app/dependencies/tenant.py`
- **str** (2 connections) — `backend/app/routes/bookings.py`
- **incidents.py** (2 connections) — `/Users/prem/Documents/Aira Ai/backend/app/routes/incidents.py`
- **messages.py** (2 connections) — `/Users/prem/Documents/Aira Ai/backend/app/routes/messages.py`
- **tenant_status()** (2 connections) — `/Users/prem/Documents/Aira Ai/backend/app/routes/onboarding.py`
- **status()** (2 connections) — `/Users/prem/Documents/Aira Ai/backend/app/routes/system.py`
- **CtwaLead** (2 connections) — `frontend/lib/api.ts`
- **Owner-only tenant id. Use for admin-only read endpoints so a caller     cannot r** (1 connections) — `backend/app/dependencies/tenant.py`
- *... and 8 more nodes in this community*

## Relationships

- [[Calls API (TeleCMI dialer)]] (12 shared connections)
- [[Operator Console & Audit]] (9 shared connections)
- [[API Client (frontend)]] (3 shared connections)
- [[Instagram Channel]] (3 shared connections)
- [[Booking Flow]] (3 shared connections)
- [[App Entry & Schedulers]] (2 shared connections)
- [[Inbound Lead Reporting]] (2 shared connections)
- [[Facebook / Webhook Verification]] (2 shared connections)
- [[Leads API]] (2 shared connections)
- [[Telecaller Assignment Engine]] (1 shared connections)
- [[Auth]] (1 shared connections)
- [[Ai Tune API]] (1 shared connections)

## Source Files

- `/Users/prem/Documents/Aira Ai/backend/app/dependencies/system_admin.py`
- `/Users/prem/Documents/Aira Ai/backend/app/routes/incidents.py`
- `/Users/prem/Documents/Aira Ai/backend/app/routes/messages.py`
- `/Users/prem/Documents/Aira Ai/backend/app/routes/onboarding.py`
- `/Users/prem/Documents/Aira Ai/backend/app/routes/system.py`
- `backend/app/dependencies/tenant.py`
- `backend/app/main.py`
- `backend/app/routes/bookings.py`
- `backend/app/routes/incidents.py`
- `frontend/lib/api.ts`

## Audit Trail

- EXTRACTED: 113 (84%)
- INFERRED: 22 (16%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*