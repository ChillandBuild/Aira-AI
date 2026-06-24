# CSV Upload & Bulk Send

> 25 nodes · cohesion 0.18

## Key Concepts

- **upload.py** (38 connections) — `backend/app/routes/upload.py`
- **str** (28 connections) — `backend/app/routes/upload.py`
- **bulk_send()** (17 connections) — `backend/app/routes/upload.py`
- **upload_leads()** (12 connections) — `backend/app/routes/upload.py`
- **_normalize_phone()** (7 connections) — `backend/app/routes/upload.py`
- **parse_csv()** (7 connections) — `backend/app/routes/upload.py`
- **_to_float()** (6 connections) — `backend/app/routes/upload.py`
- **_create_csv_signed_url()** (6 connections) — `backend/app/routes/upload.py`
- **get_csv_signed_url()** (6 connections) — `backend/app/routes/upload.py`
- **_clean_text()** (5 connections) — `backend/app/routes/upload.py`
- **_validate_csv_storage_path()** (5 connections) — `backend/app/routes/upload.py`
- **get_retry_timeline()** (5 connections) — `backend/app/routes/upload.py`
- **_meta_error_detail()** (4 connections) — `backend/app/routes/upload.py`
- **_value_for()** (4 connections) — `backend/app/routes/upload.py`
- **OptInRequest** (3 connections) — `backend/app/routes/upload.py`
- **BulkSendRequest** (3 connections) — `backend/app/routes/upload.py`
- **_retry_fields()** (3 connections) — `backend/app/routes/upload.py`
- **UploadFile** (2 connections) — `backend/app/routes/upload.py`
- **BulkLeadItem** (2 connections) — `backend/app/routes/upload.py`
- **_insert_scheduled_broadcast()** (2 connections) — `backend/app/routes/upload.py`
- **_insert_scheduled_broadcasts()** (2 connections) — `backend/app/routes/upload.py`
- **validate_optin()** (2 connections) — `backend/app/routes/upload.py`
- **float** (1 connections) — `backend/app/routes/upload.py`
- **Human-readable Meta error for the failed CSV — '(#code) message', else trimmed r** (1 connections) — `backend/app/routes/upload.py`
- **Per-attempt delivery metrics for a broadcast's auto-retry chain.** (1 connections) — `backend/app/routes/upload.py`

## Relationships

- [[Upload API]] (39 shared connections)
- [[Operator Console & Audit]] (12 shared connections)
- [[Growth Service]] (3 shared connections)
- [[Pydantic Schemas]] (3 shared connections)
- [[Broadcast Executor & Outbound Router]] (2 shared connections)
- [[App Entry & Schedulers]] (1 shared connections)
- [[Ai Reply Service]] (1 shared connections)
- [[Meta Cloud API Client]] (1 shared connections)

## Source Files

- `backend/app/routes/upload.py`

## Audit Trail

- EXTRACTED: 153 (89%)
- INFERRED: 19 (11%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*