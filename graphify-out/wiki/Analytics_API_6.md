# Analytics API

> 5 nodes · cohesion 0.40

## Key Concepts

- **template_performance()** (6 connections) — `backend/app/routes/analytics.py`
- **TemplatePerformanceRow** (5 connections) — `frontend/lib/api.ts`
- **Per-template broadcast performance: Sent / Read / Replied / Hot leads.** (2 connections) — `backend/app/routes/analytics.py`
- **Per-template broadcast performance: Sent / Read / Replied / Hot leads.** (1 connections) — `backend/app/routes/analytics.py`
- **Per-template broadcast performance: Sent / Read / Replied / Hot leads.** (1 connections) — `backend/app/routes/analytics.py`

## Relationships

- [[Analytics API]] (4 shared connections)
- [[Operator Console & Audit]] (1 shared connections)
- [[Analytics Page]] (1 shared connections)
- [[API Client (frontend)]] (1 shared connections)

## Source Files

- `backend/app/routes/analytics.py`
- `frontend/lib/api.ts`

## Audit Trail

- EXTRACTED: 14 (93%)
- INFERRED: 1 (7%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*