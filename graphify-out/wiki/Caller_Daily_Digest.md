# Caller Daily Digest

> 16 nodes · cohesion 0.20

## Key Concepts

- **generate_daily_digest()** (11 connections) — `backend/app/services/call_digest.py`
- **call_digest.py** (8 connections) — `backend/app/services/call_digest.py`
- **generate_digests_for_tenant()** (8 connections) — `backend/app/services/call_digest.py`
- **generate_all_digests()** (5 connections) — `backend/app/services/call_digest.py`
- **_build_stats_text()** (3 connections) — `backend/app/services/call_digest.py`
- **str** (3 connections) — `backend/app/services/call_digest.py`
- **_aggregate_evaluations()** (3 connections) — `backend/app/services/call_digest.py`
- **_pick_representative()** (3 connections) — `backend/app/services/call_digest.py`
- **date** (3 connections) — `backend/app/services/call_digest.py`
- **int** (1 connections) — `backend/app/services/call_digest.py`
- **Daily coaching digest — one consolidated LLM call per telecaller per day.  Inste** (1 connections) — `backend/app/services/call_digest.py`
- **Aggregate per-criterion scores and outcome-accuracy flags across a day's calls.** (1 connections) — `backend/app/services/call_digest.py`
- **Pick up to 3 distinct calls with transcripts that give the best coaching signal.** (1 connections) — `backend/app/services/call_digest.py`
- **Compute stats + AI coaching report for one caller on for_date, upsert to caller_** (1 connections) — `backend/app/services/call_digest.py`
- **Run daily digest for every active caller in a tenant. Returns count processed.** (1 connections) — `backend/app/services/call_digest.py`
- **APScheduler entry point — runs digests for all tenants.** (1 connections) — `backend/app/services/call_digest.py`

## Relationships

- [[Calls API (TeleCMI dialer)]] (3 shared connections)
- [[Config]] (1 shared connections)
- [[Callers CRUD & Coaching]] (1 shared connections)
- [[Call Coach Service]] (1 shared connections)

## Source Files

- `backend/app/services/call_digest.py`

## Audit Trail

- EXTRACTED: 49 (91%)
- INFERRED: 5 (9%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*