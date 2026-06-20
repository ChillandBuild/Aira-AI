# Telecalling Upload API

> 10 nodes · cohesion 0.33

## Key Concepts

- **upload_telecalling_contacts()** (8 connections) — `backend/app/routes/telecalling_upload.py`
- **telecalling_upload.py** (7 connections) — `backend/app/routes/telecalling_upload.py`
- **_round_robin_assign_leads()** (6 connections) — `backend/app/routes/telecalling_upload.py`
- **download_assignment_csv()** (5 connections) — `backend/app/routes/telecalling_upload.py`
- **_normalize_phone()** (4 connections) — `backend/app/routes/telecalling_upload.py`
- **str** (3 connections) — `backend/app/routes/telecalling_upload.py`
- **get_upload_history()** (3 connections) — `backend/app/routes/telecalling_upload.py`
- **UUID** (2 connections) — `backend/app/routes/telecalling_upload.py`
- **UploadFile** (1 connections) — `backend/app/routes/telecalling_upload.py`
- **int** (1 connections) — `backend/app/routes/telecalling_upload.py`

## Relationships

- [[Calls API (TeleCMI dialer)]] (3 shared connections)
- [[Assignment Service]] (2 shared connections)
- [[Operator Console & Audit]] (2 shared connections)
- [[Tenant]] (1 shared connections)
- [[Telecaller Assignment Engine]] (1 shared connections)
- [[Notify Service]] (1 shared connections)

## Source Files

- `backend/app/routes/telecalling_upload.py`

## Audit Trail

- EXTRACTED: 31 (78%)
- INFERRED: 9 (22%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*