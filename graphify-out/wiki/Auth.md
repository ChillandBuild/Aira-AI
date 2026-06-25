# Auth

> 13 nodes · cohesion 0.22

## Key Concepts

- **auth.py** (7 connections) — `backend/app/dependencies/auth.py`
- **_verify_remote()** (6 connections) — `backend/app/dependencies/auth.py`
- **get_current_user()** (6 connections) — `backend/app/dependencies/auth.py`
- **_is_connection_error()** (5 connections) — `backend/app/dependencies/auth.py`
- **_verify_local()** (5 connections) — `backend/app/dependencies/auth.py`
- **_user_from_claims()** (2 connections) — `backend/app/dependencies/auth.py`
- **str** (2 connections) — `backend/app/dependencies/auth.py`
- **Exception** (1 connections) — `backend/app/dependencies/auth.py`
- **bool** (1 connections) — `backend/app/dependencies/auth.py`
- **HTTPAuthorizationCredentials** (1 connections) — `backend/app/dependencies/auth.py`
- **True for transient transport/connection failures (not bad credentials).      Cov** (1 connections) — `backend/app/dependencies/auth.py`
- **Verify the JWT signature locally (no network). Returns the user on     success,** (1 connections) — `backend/app/dependencies/auth.py`
- **Validate via Supabase auth, retrying once on transient connection drops.     Con** (1 connections) — `backend/app/dependencies/auth.py`

## Relationships

- [[Operator Console & Audit]] (3 shared connections)
- [[Call Coach Service]] (1 shared connections)
- [[App Entry & Schedulers]] (1 shared connections)

## Source Files

- `backend/app/dependencies/auth.py`

## Audit Trail

- EXTRACTED: 36 (92%)
- INFERRED: 3 (8%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*