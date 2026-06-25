# Templates API

> 6 nodes · cohesion 0.33

## Key Concepts

- **sync_templates_from_meta()** (8 connections) — `backend/app/routes/templates.py`
- **list_all_templates()** (6 connections) — `backend/app/services/meta_cloud.py`
- **Pull all templates from Meta and upsert into local DB. Returns added/updated cou** (1 connections) — `backend/app/routes/templates.py`
- **Fetch all templates from Meta for a WABA, handling pagination.     Returns list** (1 connections) — `backend/app/services/meta_cloud.py`
- **Pull all templates from Meta and upsert into local DB. Returns added/updated cou** (1 connections) — `backend/app/routes/templates.py`
- **Fetch all templates from Meta for a WABA, handling pagination.     Returns list** (1 connections) — `backend/app/services/meta_cloud.py`

## Relationships

- [[Meta Cloud API Client]] (3 shared connections)
- [[Operator Console & Audit]] (2 shared connections)
- [[Templates API]] (2 shared connections)
- [[Config Dynamic]] (1 shared connections)

## Source Files

- `backend/app/routes/templates.py`
- `backend/app/services/meta_cloud.py`

## Audit Trail

- EXTRACTED: 14 (78%)
- INFERRED: 4 (22%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*