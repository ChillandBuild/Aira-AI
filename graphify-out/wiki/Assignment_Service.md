# Assignment Service

> 21 nodes · cohesion 0.11

## Key Concepts

- **auto_assign_lead()** (20 connections) — `backend/app/services/assignment.py`
- **maybe_assign_lead()** (16 connections) — `backend/app/services/assignment.py`
- **sweep_unassigned_leads()** (9 connections) — `backend/app/services/assignment.py`
- **_sweep_unassigned_leads()** (6 connections) — `backend/app/main.py`
- **int** (6 connections) — `backend/app/services/assignment.py`
- **_open_lead_count()** (5 connections) — `backend/app/services/assignment.py`
- **APScheduler job: state-based safety net that assigns any unassigned lead     who** (1 connections) — `backend/app/main.py`
- **Active workload for a caller = assigned leads that are still open.      Excludes** (1 connections) — `backend/app/services/assignment.py`
- **Assign lead to the active caller with the fewest OPEN leads (least-loaded     ro** (1 connections) — `backend/app/services/assignment.py`
- **Single gated entry point for auto-assignment.      Assigns iff the lead's CURREN** (1 connections) — `backend/app/services/assignment.py`
- **State-based safety net for auto-assignment.      Assigns any UNASSIGNED lead who** (1 connections) — `backend/app/services/assignment.py`
- **APScheduler job: state-based safety net that assigns any unassigned lead     who** (1 connections) — `backend/app/main.py`
- **Single gated entry point for auto-assignment.      Assigns iff the lead's CURREN** (1 connections) — `backend/app/services/assignment.py`
- **State-based safety net for auto-assignment.      Assigns any UNASSIGNED lead who** (1 connections) — `backend/app/services/assignment.py`
- **Single gated entry point for auto-assignment.      Assigns iff the lead's CURREN** (1 connections) — `backend/app/services/assignment.py`
- **State-based safety net for auto-assignment.      Assigns any UNASSIGNED lead who** (1 connections) — `backend/app/services/assignment.py`
- **APScheduler job: state-based safety net that assigns any unassigned lead     who** (1 connections) — `backend/app/main.py`
- **APScheduler job: state-based safety net that assigns any unassigned lead     who** (1 connections) — `backend/app/main.py`
- **Single gated entry point for auto-assignment.      Assigns iff the lead's CURREN** (1 connections) — `backend/app/services/assignment.py`
- **State-based safety net for auto-assignment.      Assigns any UNASSIGNED lead who** (1 connections) — `backend/app/services/assignment.py`
- **Assign lead to the active caller with fewest assigned non-disqualified leads.** (1 connections) — `backend/app/services/assignment.py`

## Relationships

- [[Telecaller Assignment Engine]] (8 shared connections)
- [[Assignment Service]] (4 shared connections)
- [[Notify Service]] (3 shared connections)
- [[Ai Reply Service]] (3 shared connections)
- [[Operator Console & Audit]] (2 shared connections)
- [[Facebook / Webhook Verification]] (2 shared connections)
- [[Instagram Channel]] (2 shared connections)
- [[Templates API]] (2 shared connections)
- [[WhatsApp Inbound Webhook]] (2 shared connections)
- [[App Entry & Schedulers]] (1 shared connections)
- [[Calls API]] (1 shared connections)
- [[Leads API]] (1 shared connections)

## Source Files

- `backend/app/main.py`
- `backend/app/services/assignment.py`

## Audit Trail

- EXTRACTED: 59 (77%)
- INFERRED: 18 (23%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*