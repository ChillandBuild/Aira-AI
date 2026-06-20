# Assignment Service

> 20 nodes · cohesion 0.12

## Key Concepts

- **auto_assign_lead()** (19 connections) — `backend/app/services/assignment.py`
- **telegram_webhook()** (15 connections) — `backend/app/routes/telegram.py`
- **maybe_assign_lead()** (15 connections) — `backend/app/services/assignment.py`
- **sweep_unassigned_leads()** (8 connections) — `backend/app/services/assignment.py`
- **_open_lead_count()** (5 connections) — `backend/app/services/assignment.py`
- **int** (5 connections) — `backend/app/services/assignment.py`
- **test_telegram.py** (2 connections) — `backend/tests/test_telegram.py`
- **test_telegram_webhook_new_lead()** (2 connections) — `backend/tests/test_telegram.py`
- **str** (1 connections) — `backend/app/routes/telegram.py`
- **Request** (1 connections) — `backend/app/routes/telegram.py`
- **BackgroundTasks** (1 connections) — `backend/app/routes/telegram.py`
- **Active workload for a caller = assigned leads that are still open.      Excludes** (1 connections) — `backend/app/services/assignment.py`
- **Assign lead to the active caller with the fewest OPEN leads (least-loaded     ro** (1 connections) — `backend/app/services/assignment.py`
- **Single gated entry point for auto-assignment.      Assigns iff the lead's CURREN** (1 connections) — `backend/app/services/assignment.py`
- **State-based safety net for auto-assignment.      Assigns any UNASSIGNED lead who** (1 connections) — `backend/app/services/assignment.py`
- **Single gated entry point for auto-assignment.      Assigns iff the lead's CURREN** (1 connections) — `backend/app/services/assignment.py`
- **State-based safety net for auto-assignment.      Assigns any UNASSIGNED lead who** (1 connections) — `backend/app/services/assignment.py`
- **Single gated entry point for auto-assignment.      Assigns iff the lead's CURREN** (1 connections) — `backend/app/services/assignment.py`
- **State-based safety net for auto-assignment.      Assigns any UNASSIGNED lead who** (1 connections) — `backend/app/services/assignment.py`
- **Assign lead to the active caller with fewest assigned non-disqualified leads.** (1 connections) — `backend/app/services/assignment.py`

## Relationships

- [[Telecaller Assignment Engine]] (10 shared connections)
- [[Calls API (TeleCMI dialer)]] (5 shared connections)
- [[Booking Flow]] (4 shared connections)
- [[Instagram Channel]] (3 shared connections)
- [[Notify Service]] (2 shared connections)
- [[Facebook / Webhook Verification]] (2 shared connections)
- [[AI Reply Pipeline (Groq)]] (2 shared connections)
- [[Assignment Service]] (2 shared connections)
- [[Operator Console & Audit]] (1 shared connections)
- [[Growth Service]] (1 shared connections)
- [[Ai Reply Service]] (1 shared connections)
- [[Leads API]] (1 shared connections)

## Source Files

- `backend/app/routes/telegram.py`
- `backend/app/services/assignment.py`
- `backend/tests/test_telegram.py`

## Audit Trail

- EXTRACTED: 55 (66%)
- INFERRED: 28 (34%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*