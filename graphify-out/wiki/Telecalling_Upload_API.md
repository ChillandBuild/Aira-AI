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

- [[Operator Console & Audit]] (5 shared connections)
- [[Telecaller Assignment Engine]] (2 shared connections)
- [[Notify Service]] (2 shared connections)
- [[App Entry & Schedulers]] (1 shared connections)

## Source Files

- `backend/app/routes/telecalling_upload.py`

## Audit Trail

- EXTRACTED: 31 (78%)
- INFERRED: 9 (22%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*