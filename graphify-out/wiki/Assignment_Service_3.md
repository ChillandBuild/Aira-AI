# Assignment Service

> 7 nodes · cohesion 0.29

## Key Concepts

- **get_inbox_config()** (13 connections) — `backend/app/services/assignment.py`
- **get_inbox_config_route()** (2 connections) — `backend/app/routes/app_settings.py`
- **Return inbox_config from app_settings, merged with defaults.** (1 connections) — `backend/app/services/assignment.py`
- **Return inbox_config from app_settings, merged with defaults.** (1 connections) — `backend/app/services/assignment.py`
- **Return inbox_config from app_settings, merged with defaults.** (1 connections) — `backend/app/services/assignment.py`
- **Return inbox_config from app_settings, merged with defaults.** (1 connections) — `backend/app/services/assignment.py`
- **Return inbox_config from app_settings, merged with defaults.** (1 connections) — `backend/app/services/assignment.py`

## Relationships

- [[App Settings API]] (4 shared connections)
- [[Telecaller Assignment Engine]] (2 shared connections)
- [[Operator Console & Audit]] (1 shared connections)
- [[AI Reply Pipeline (Groq)]] (1 shared connections)

## Source Files

- `backend/app/routes/app_settings.py`
- `backend/app/services/assignment.py`

## Audit Trail

- EXTRACTED: 15 (75%)
- INFERRED: 5 (25%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*