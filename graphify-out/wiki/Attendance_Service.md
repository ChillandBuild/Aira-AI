# Attendance Service

> 30 nodes · cohesion 0.10

## Key Concepts

- **resolve_day_status()** (10 connections) — `backend/app/services/attendance.py`
- **date_range()** (9 connections) — `backend/app/services/attendance.py`
- **build_attendance_map()** (9 connections) — `backend/app/services/attendance.py`
- **compute_team_summary()** (6 connections) — `backend/app/services/attendance.py`
- **attendance.py** (5 connections) — `backend/app/services/attendance.py`
- **test_attendance_service.py** (5 connections) — `backend/tests/test_attendance_service.py`
- **TestResolveDayStatus** (5 connections) — `backend/tests/test_attendance_service.py`
- **date** (3 connections) — `backend/app/services/attendance.py`
- **str** (3 connections) — `backend/app/services/attendance.py`
- **TestDateRange** (3 connections) — `backend/tests/test_attendance_service.py`
- **.test_combines_overrides_and_activity()** (3 connections) — `backend/tests/test_attendance_service.py`
- **.test_future_date_returns_future()** (2 connections) — `backend/tests/test_attendance_service.py`
- **.test_override_wins_over_activity()** (2 connections) — `backend/tests/test_attendance_service.py`
- **.test_derives_present_from_activity()** (2 connections) — `backend/tests/test_attendance_service.py`
- **.test_derives_absent_without_activity()** (2 connections) — `backend/tests/test_attendance_service.py`
- **.test_inclusive_range()** (2 connections) — `backend/tests/test_attendance_service.py`
- **.test_single_day()** (2 connections) — `backend/tests/test_attendance_service.py`
- **TestBuildAttendanceMap** (2 connections) — `backend/tests/test_attendance_service.py`
- **TestComputeTeamSummary** (2 connections) — `backend/tests/test_attendance_service.py`
- **.test_summary_counts_and_rate()** (2 connections) — `backend/tests/test_attendance_service.py`
- **bool** (1 connections) — `backend/app/services/attendance.py`
- **Attendance resolution: admin overrides win, else derive from caller_status_logs** (1 connections) — `backend/app/services/attendance.py`
- **Resolve a single day's attendance status.      Priority: holiday override > futu** (1 connections) — `backend/app/services/attendance.py`
- **Inclusive list of dates from start to end.** (1 connections) — `backend/app/services/attendance.py`
- **Build {date_iso: status} for one caller given pre-fetched overrides/activity.** (1 connections) — `backend/app/services/attendance.py`
- *... and 5 more nodes in this community*

## Relationships

- [[Team API]] (5 shared connections)

## Source Files

- `backend/app/services/attendance.py`
- `backend/tests/test_attendance_service.py`

## Audit Trail

- EXTRACTED: 66 (74%)
- INFERRED: 23 (26%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*