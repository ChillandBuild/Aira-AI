# Contact Recycler Service

> 8 nodes · cohesion 0.39

## Key Concepts

- **recycle_leads_for_tenant()** (6 connections) — `backend/app/services/contact_recycler.py`
- **recycle_all_tenants()** (5 connections) — `backend/app/services/contact_recycler.py`
- **_get_recycle_config()** (4 connections) — `backend/app/services/contact_recycler.py`
- **_recycle_contacts()** (3 connections) — `backend/app/main.py`
- **contact_recycler.py** (3 connections) — `backend/app/services/contact_recycler.py`
- **APScheduler job: re-queue no_answer leads within calling hours.** (2 connections) — `backend/app/main.py`
- **str** (2 connections) — `backend/app/services/contact_recycler.py`
- **int** (2 connections) — `backend/app/services/contact_recycler.py`

## Relationships

- [[Calls API (TeleCMI dialer)]] (3 shared connections)
- [[App Entry & Schedulers]] (1 shared connections)
- [[Assignment Service]] (1 shared connections)

## Source Files

- `backend/app/main.py`
- `backend/app/services/contact_recycler.py`

## Audit Trail

- EXTRACTED: 22 (81%)
- INFERRED: 5 (19%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*