# Ai Tune API

> 14 nodes · cohesion 0.24

## Key Concepts

- **ai_tune.py** (10 connections) — `backend/app/routes/ai_tune.py`
- **_auto_generate_rubric()** (8 connections) — `backend/app/routes/ai_tune.py`
- **str** (7 connections) — `backend/app/routes/ai_tune.py`
- **update_prompt()** (7 connections) — `backend/app/routes/ai_tune.py`
- **analyze()** (6 connections) — `backend/app/routes/ai_tune.py`
- **apply_suggestion()** (5 connections) — `backend/app/routes/ai_tune.py`
- **reject_suggestion()** (4 connections) — `backend/app/routes/ai_tune.py`
- **invalidate_prompt_cache()** (4 connections) — `backend/app/services/ai_reply.py`
- **PromptUpdate** (3 connections) — `backend/app/routes/ai_tune.py`
- **list_prompts()** (3 connections) — `backend/app/routes/ai_tune.py`
- **list_suggestions()** (3 connections) — `backend/app/routes/ai_tune.py`
- **bool** (1 connections) — `backend/app/routes/ai_tune.py`
- **int** (1 connections) — `backend/app/routes/ai_tune.py`
- **Generate a domain-appropriate scoring rubric from the tenant's system prompt.** (1 connections) — `backend/app/routes/ai_tune.py`

## Relationships

- [[Operator Console & Audit]] (10 shared connections)
- [[Ai Reply Service]] (4 shared connections)
- [[Config Dynamic]] (2 shared connections)
- [[Call Coach Service]] (1 shared connections)
- [[App Entry & Schedulers]] (1 shared connections)
- [[Leads API]] (1 shared connections)

## Source Files

- `backend/app/routes/ai_tune.py`
- `backend/app/services/ai_reply.py`

## Audit Trail

- EXTRACTED: 45 (71%)
- INFERRED: 18 (29%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*