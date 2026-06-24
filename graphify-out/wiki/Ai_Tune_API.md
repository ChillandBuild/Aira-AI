# Ai Tune API

> 18 nodes · cohesion 0.17

## Key Concepts

- **ai_tune.py** (10 connections) — `backend/app/routes/ai_tune.py`
- **_auto_generate_rubric()** (8 connections) — `backend/app/routes/ai_tune.py`
- **save_setting()** (7 connections) — `backend/app/config_dynamic.py`
- **str** (7 connections) — `backend/app/routes/ai_tune.py`
- **update_prompt()** (7 connections) — `backend/app/routes/ai_tune.py`
- **analyze()** (6 connections) — `backend/app/routes/ai_tune.py`
- **apply_suggestion()** (5 connections) — `backend/app/routes/ai_tune.py`
- **reject_suggestion()** (4 connections) — `backend/app/routes/ai_tune.py`
- **invalidate_prompt_cache()** (4 connections) — `backend/app/services/ai_reply.py`
- **PromptUpdate** (3 connections) — `backend/app/routes/ai_tune.py`
- **list_prompts()** (3 connections) — `backend/app/routes/ai_tune.py`
- **list_suggestions()** (3 connections) — `backend/app/routes/ai_tune.py`
- **Upsert a key/value into app_settings and invalidate the local cache.** (1 connections) — `backend/app/config_dynamic.py`
- **bool** (1 connections) — `backend/app/routes/ai_tune.py`
- **int** (1 connections) — `backend/app/routes/ai_tune.py`
- **Generate a domain-appropriate scoring rubric from the tenant's system prompt.** (1 connections) — `backend/app/routes/ai_tune.py`
- **Upsert a key/value into app_settings and invalidate the local cache.** (1 connections) — `backend/app/config_dynamic.py`
- **Upsert a key/value into app_settings and invalidate the local cache.** (1 connections) — `backend/app/config_dynamic.py`

## Relationships

- [[Operator Console & Audit]] (11 shared connections)
- [[AI Reply Pipeline (Groq)]] (4 shared connections)
- [[Templates API]] (2 shared connections)
- [[Channels Page]] (1 shared connections)
- [[Config]] (1 shared connections)
- [[App Entry & Schedulers]] (1 shared connections)
- [[Pydantic Schemas]] (1 shared connections)

## Source Files

- `backend/app/config_dynamic.py`
- `backend/app/routes/ai_tune.py`
- `backend/app/services/ai_reply.py`

## Audit Trail

- EXTRACTED: 53 (73%)
- INFERRED: 20 (27%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*