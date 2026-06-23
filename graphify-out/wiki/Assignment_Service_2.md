# Assignment Service

> 13 nodes · cohesion 0.18

## Key Concepts

- **is_round_robin_enabled()** (14 connections) — `backend/app/services/assignment.py`
- **save_telecalling_config()** (12 connections) — `backend/app/services/assignment.py`
- **set_round_robin_enabled()** (7 connections) — `backend/app/services/assignment.py`
- **bool** (6 connections) — `backend/app/services/assignment.py`
- **Flip the single auto-assign switch (telecalling_config.enabled).** (2 connections) — `backend/app/services/assignment.py`
- **Whether auto-assign to telecallers is on.      Single source of truth: telecalli** (1 connections) — `backend/app/services/assignment.py`
- **Persist telecalling_config to app_settings.** (1 connections) — `backend/app/services/assignment.py`
- **Persist telecalling_config to app_settings.** (1 connections) — `backend/app/services/assignment.py`
- **Persist telecalling_config to app_settings.** (1 connections) — `backend/app/services/assignment.py`
- **Persist telecalling_config to app_settings.** (1 connections) — `backend/app/services/assignment.py`
- **Check app_settings for round_robin_enabled flag. Defaults to True.** (1 connections) — `backend/app/services/assignment.py`
- **Upsert the round_robin_enabled flag in app_settings.** (1 connections) — `backend/app/services/assignment.py`
- **Persist telecalling_config to app_settings.** (1 connections) — `backend/app/services/assignment.py`

## Relationships

- [[Assignment Service]] (8 shared connections)
- [[Telecaller Assignment Engine]] (6 shared connections)
- [[Callers API]] (3 shared connections)
- [[Operator Console & Audit]] (2 shared connections)
- [[App Settings API]] (1 shared connections)
- [[Callers CRUD & Coaching]] (1 shared connections)

## Source Files

- `backend/app/services/assignment.py`

## Audit Trail

- EXTRACTED: 42 (86%)
- INFERRED: 7 (14%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*