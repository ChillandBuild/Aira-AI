# Templates API

> 20 nodes · cohesion 0.17

## Key Concepts

- **templates.py** (20 connections) — `backend/app/routes/templates.py`
- **TemplateContentExistsError** (13 connections) — `backend/app/services/meta_cloud.py`
- **str** (12 connections) — `backend/app/routes/templates.py`
- **CreateTemplate** (11 connections) — `backend/app/routes/templates.py`
- **submit_template()** (10 connections) — `backend/app/services/meta_cloud.py`
- **create_template()** (9 connections) — `backend/app/routes/templates.py`
- **template_status_webhook()** (7 connections) — `backend/app/routes/templates.py`
- **delete_template()** (6 connections) — `backend/app/routes/templates.py`
- **update_template_variations()** (5 connections) — `backend/app/routes/templates.py`
- **VariationsPayload** (4 connections) — `backend/app/routes/templates.py`
- **test_create_template_uses_waba_id_not_phone_number_id()** (4 connections) — `/Users/prem/Documents/Aira Ai/backend/tests/test_templates.py`
- **Button** (3 connections) — `backend/app/routes/templates.py`
- **CarouselCard** (3 connections) — `backend/app/routes/templates.py`
- **list_templates()** (3 connections) — `backend/app/routes/templates.py`
- **Request** (2 connections) — `backend/app/routes/templates.py`
- **Meta calls this when template status changes (APPROVED/REJECTED). No auth.** (1 connections) — `backend/app/routes/templates.py`
- **Raised when Meta rejects template creation because name+language already exists.** (1 connections) — `backend/app/services/meta_cloud.py`
- **create_template must read meta_waba_id, not meta_phone_number_id.** (1 connections) — `/Users/prem/Documents/Aira Ai/backend/tests/test_templates.py`
- **Meta calls this when template status changes (APPROVED/REJECTED). No auth.** (1 connections) — `backend/app/routes/templates.py`
- **Raised when Meta rejects template creation because name+language already exists.** (1 connections) — `backend/app/services/meta_cloud.py`

## Relationships

- [[Operator Console & Audit]] (15 shared connections)
- [[Meta Cloud Service]] (13 shared connections)
- [[Meta Cloud API Client]] (5 shared connections)
- [[Config Dynamic]] (4 shared connections)
- [[Leads API]] (4 shared connections)
- [[Analytics Page]] (2 shared connections)
- [[Templates API]] (2 shared connections)
- [[App Entry & Schedulers]] (1 shared connections)
- [[Templates Page]] (1 shared connections)
- [[Meta Webhook Verify Service]] (1 shared connections)

## Source Files

- `/Users/prem/Documents/Aira Ai/backend/tests/test_templates.py`
- `backend/app/routes/templates.py`
- `backend/app/services/meta_cloud.py`

## Audit Trail

- EXTRACTED: 80 (68%)
- INFERRED: 37 (32%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*