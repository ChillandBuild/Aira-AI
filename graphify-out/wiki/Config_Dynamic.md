# Config Dynamic

> 14 nodes · cohesion 0.16

## Key Concepts

- **get_setting()** (31 connections) — `backend/app/config_dynamic.py`
- **config_dynamic.py** (11 connections) — `backend/app/config_dynamic.py`
- **save_setting()** (7 connections) — `backend/app/config_dynamic.py`
- **str** (4 connections) — `backend/app/config_dynamic.py`
- **invalidate_cache()** (4 connections) — `backend/app/config_dynamic.py`
- **telegram.py** (3 connections) — `backend/app/routes/telegram.py`
- **groq_client.py** (3 connections) — `backend/app/services/groq_client.py`
- **saveSettings()** (3 connections) — `frontend/app/dashboard/channels/page.tsx`
- **Read from cache → app_settings table → fallback. No env-var fallback: every** (1 connections) — `backend/app/config_dynamic.py`
- **Upsert a key/value into app_settings and invalidate the local cache.** (1 connections) — `backend/app/config_dynamic.py`
- **Read from cache → app_settings table → env var → fallback.** (1 connections) — `backend/app/config_dynamic.py`
- **Upsert a key/value into app_settings and invalidate the local cache.** (1 connections) — `backend/app/config_dynamic.py`
- **Read from cache → app_settings table → env var → fallback.** (1 connections) — `backend/app/config_dynamic.py`
- **Upsert a key/value into app_settings and invalidate the local cache.** (1 connections) — `backend/app/config_dynamic.py`

## Relationships

- [[Templates API]] (5 shared connections)
- [[Operator Console & Audit]] (4 shared connections)
- [[Ai Reply Service]] (4 shared connections)
- [[Facebook / Webhook Verification]] (2 shared connections)
- [[Instagram Channel]] (2 shared connections)
- [[Meta Cloud API Client]] (2 shared connections)
- [[Meta Webhook Verify Service]] (2 shared connections)
- [[Ai Tune API]] (2 shared connections)
- [[Calls API]] (2 shared connections)
- [[AI Reply Pipeline (Groq)]] (2 shared connections)
- [[Calls API (TeleCMI dialer)]] (1 shared connections)
- [[App Settings API]] (1 shared connections)

## Source Files

- `backend/app/config_dynamic.py`
- `backend/app/routes/telegram.py`
- `backend/app/services/groq_client.py`
- `frontend/app/dashboard/channels/page.tsx`

## Audit Trail

- EXTRACTED: 58 (81%)
- INFERRED: 14 (19%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*