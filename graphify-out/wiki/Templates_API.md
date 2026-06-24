# Templates API

> 39 nodes · cohesion 0.08

## Key Concepts

- **get_setting()** (31 connections) — `backend/app/config_dynamic.py`
- **templates.py** (20 connections) — `backend/app/routes/templates.py`
- **telegram_webhook()** (15 connections) — `backend/app/routes/telegram.py`
- **TemplateContentExistsError** (13 connections) — `backend/app/services/meta_cloud.py`
- **str** (12 connections) — `backend/app/routes/templates.py`
- **config_dynamic.py** (11 connections) — `backend/app/config_dynamic.py`
- **CreateTemplate** (11 connections) — `backend/app/routes/templates.py`
- **create_template()** (9 connections) — `backend/app/routes/templates.py`
- **sync_template_status()** (8 connections) — `backend/app/routes/templates.py`
- **sync_templates_from_meta()** (8 connections) — `backend/app/routes/templates.py`
- **template_status_webhook()** (7 connections) — `backend/app/routes/templates.py`
- **delete_template()** (6 connections) — `backend/app/routes/templates.py`
- **update_template_variations()** (5 connections) — `backend/app/routes/templates.py`
- **VariationsPayload** (4 connections) — `backend/app/routes/templates.py`
- **get_template_variations()** (4 connections) — `backend/app/routes/templates.py`
- **test_create_template_uses_waba_id_not_phone_number_id()** (4 connections) — `/Users/prem/Documents/Aira Ai/backend/tests/test_templates.py`
- **telegram.py** (3 connections) — `backend/app/routes/telegram.py`
- **Button** (3 connections) — `backend/app/routes/templates.py`
- **CarouselCard** (3 connections) — `backend/app/routes/templates.py`
- **list_templates()** (3 connections) — `backend/app/routes/templates.py`
- **Request** (2 connections) — `backend/app/routes/templates.py`
- **test_telegram.py** (2 connections) — `backend/tests/test_telegram.py`
- **test_telegram_webhook_new_lead()** (2 connections) — `backend/tests/test_telegram.py`
- **Read from cache → app_settings table → fallback. No env-var fallback: every** (1 connections) — `backend/app/config_dynamic.py`
- **str** (1 connections) — `backend/app/routes/telegram.py`
- *... and 14 more nodes in this community*

## Relationships

- [[Operator Console & Audit]] (21 shared connections)
- [[Meta Cloud API Client]] (19 shared connections)
- [[Ai Reply Service]] (4 shared connections)
- [[Pydantic Schemas]] (4 shared connections)
- [[Calls API]] (3 shared connections)
- [[Meta Webhook Verify Service]] (3 shared connections)
- [[App Entry & Schedulers]] (3 shared connections)
- [[Channels Page]] (2 shared connections)
- [[Ai Tune API]] (2 shared connections)
- [[Facebook / Webhook Verification]] (2 shared connections)
- [[Instagram Channel]] (2 shared connections)
- [[AI Reply Pipeline (Groq)]] (2 shared connections)

## Source Files

- `/Users/prem/Documents/Aira Ai/backend/tests/test_templates.py`
- `backend/app/config_dynamic.py`
- `backend/app/routes/telegram.py`
- `backend/app/routes/templates.py`
- `backend/app/services/meta_cloud.py`
- `backend/tests/test_telegram.py`

## Audit Trail

- EXTRACTED: 139 (69%)
- INFERRED: 63 (31%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*