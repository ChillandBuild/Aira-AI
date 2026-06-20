# Team API

> 16 nodes · cohesion 0.20

## Key Concepts

- **team.py** (13 connections) — `backend/app/routes/team.py`
- **get_team_attendance()** (8 connections) — `backend/app/routes/team.py`
- **get_caller_attendance()** (7 connections) — `backend/app/routes/team.py`
- **_active_team_callers()** (5 connections) — `backend/app/routes/team.py`
- **str** (5 connections) — `backend/app/routes/team.py`
- **mark_holiday()** (5 connections) — `backend/app/routes/team.py`
- **mark_attendance()** (5 connections) — `backend/app/routes/team.py`
- **invite_member()** (4 connections) — `backend/app/routes/team.py`
- **remove_member()** (4 connections) — `backend/app/routes/team.py`
- **InvitePayload** (3 connections) — `backend/app/routes/team.py`
- **AttendancePayload** (3 connections) — `backend/app/routes/team.py`
- **MarkHolidayPayload** (3 connections) — `backend/app/routes/team.py`
- **list_team()** (3 connections) — `backend/app/routes/team.py`
- **get_me()** (2 connections) — `backend/app/routes/team.py`
- **int** (1 connections) — `backend/app/routes/team.py`
- **Active, non-owner callers for a tenant (mirrors list_callers filtering).** (1 connections) — `backend/app/routes/team.py`

## Relationships

- [[Calls API (TeleCMI dialer)]] (8 shared connections)
- [[Operator Console & Audit]] (7 shared connections)
- [[Attendance Service]] (5 shared connections)
- [[Leads API]] (3 shared connections)
- [[Tenant]] (1 shared connections)

## Source Files

- `backend/app/routes/team.py`

## Audit Trail

- EXTRACTED: 52 (72%)
- INFERRED: 20 (28%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*