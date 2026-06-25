# Tenant

> 8 nodes · cohesion 0.29

## Key Concepts

- **tenant.py** (5 connections) — `backend/app/dependencies/tenant.py`
- **get_tenant_id()** (4 connections) — `backend/app/dependencies/tenant.py`
- **get_tenant_and_role()** (4 connections) — `backend/app/dependencies/tenant.py`
- **get_owner_tenant_id()** (4 connections) — `backend/app/dependencies/tenant.py`
- **str** (2 connections) — `backend/app/dependencies/tenant.py`
- **require_owner()** (2 connections) — `backend/app/dependencies/tenant.py`
- **Owner-only tenant id. Use for admin-only read endpoints so a caller     cannot r** (1 connections) — `backend/app/dependencies/tenant.py`
- **Owner-only tenant id. Use for admin-only read endpoints so a caller     cannot r** (1 connections) — `backend/app/dependencies/tenant.py`

## Relationships

- [[Operator Console & Audit]] (5 shared connections)
- [[App Entry & Schedulers]] (1 shared connections)
- [[Telecaller Assignment Engine]] (1 shared connections)

## Source Files

- `backend/app/dependencies/tenant.py`

## Audit Trail

- EXTRACTED: 17 (74%)
- INFERRED: 6 (26%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*