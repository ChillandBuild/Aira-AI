# Upload API

> 10 nodes · cohesion 0.20

## Key Concepts

- **download_tag_csv()** (10 connections) — `backend/app/routes/upload.py`
- **download_broadcast_scores_csv()** (7 connections) — `backend/app/routes/upload.py`
- **Download per-lead interest CSV for a specific broadcast (product-specific scorin** (2 connections) — `backend/app/routes/upload.py`
- **Download per-lead interest CSV for a specific broadcast (product-specific scorin** (1 connections) — `backend/app/routes/upload.py`
- **Per-tag CSV grouped by broadcast.      Normal segment exports include only succe** (1 connections) — `backend/app/routes/upload.py`
- **Per-tag CSV grouped by broadcast.      Normal segment exports include only succe** (1 connections) — `backend/app/routes/upload.py`
- **Download per-lead interest CSV for a specific broadcast (product-specific scorin** (1 connections) — `backend/app/routes/upload.py`
- **Per-tag CSV grouped by broadcast.      Normal segment exports include only succe** (1 connections) — `backend/app/routes/upload.py`
- **Download per-lead interest CSV for a specific broadcast (product-specific scorin** (1 connections) — `backend/app/routes/upload.py`
- **Per-tag CSV grouped by broadcast: name, phone, template, broadcast_id, HOT, WARM** (1 connections) — `backend/app/routes/upload.py`

## Relationships

- [[CSV Upload & Bulk Send]] (4 shared connections)
- [[Operator Console & Audit]] (2 shared connections)
- [[Upload API]] (2 shared connections)

## Source Files

- `backend/app/routes/upload.py`

## Audit Trail

- EXTRACTED: 24 (92%)
- INFERRED: 2 (8%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*