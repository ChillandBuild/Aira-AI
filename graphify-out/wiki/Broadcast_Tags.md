# Broadcast Tags

> 11 nodes · cohesion 0.29

## Key Concepts

- **tags.py** (8 connections) — `backend/app/routes/tags.py`
- **str** (5 connections) — `backend/app/routes/tags.py`
- **create_tag()** (5 connections) — `backend/app/routes/tags.py`
- **update_tag()** (5 connections) — `backend/app/routes/tags.py`
- **get_tag_stats()** (5 connections) — `backend/app/routes/tags.py`
- **delete_tag()** (4 connections) — `backend/app/routes/tags.py`
- **TagCreate** (3 connections) — `backend/app/routes/tags.py`
- **TagUpdate** (3 connections) — `backend/app/routes/tags.py`
- **list_tags()** (3 connections) — `backend/app/routes/tags.py`
- **Per-tag stats: total_sent, hot, warm, cold, disqualified, opted_out, failed.** (1 connections) — `backend/app/routes/tags.py`
- **Return per-tag stats: total_sent, hot, warm, cold counts.** (1 connections) — `backend/app/routes/tags.py`

## Relationships

- [[Operator Console & Audit]] (8 shared connections)
- [[Leads API]] (2 shared connections)
- [[App Entry & Schedulers]] (1 shared connections)

## Source Files

- `backend/app/routes/tags.py`

## Audit Trail

- EXTRACTED: 35 (81%)
- INFERRED: 8 (19%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*