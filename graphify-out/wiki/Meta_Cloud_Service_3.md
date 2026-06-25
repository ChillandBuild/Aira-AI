# Meta Cloud Service

> 7 nodes · cohesion 0.43

## Key Concepts

- **upload_template_media()** (13 connections) — `backend/app/routes/templates.py`
- **upload_media_for_template()** (8 connections) — `backend/app/services/meta_cloud.py`
- **bytes** (4 connections) — `backend/app/services/meta_cloud.py`
- **int** (3 connections) — `backend/app/services/meta_cloud.py`
- **UploadFile** (2 connections) — `backend/app/routes/templates.py`
- **Upload media for template headers using Meta's Resumable Upload API.      Step 1** (2 connections) — `backend/app/services/meta_cloud.py`
- **Upload a media file for use in template headers. Returns the Meta header_handle.** (1 connections) — `backend/app/routes/templates.py`

## Relationships

- [[Meta Cloud API Client]] (8 shared connections)
- [[Templates API]] (3 shared connections)
- [[Operator Console & Audit]] (2 shared connections)
- [[Config Dynamic]] (1 shared connections)
- [[Meta Cloud Service]] (1 shared connections)

## Source Files

- `backend/app/routes/templates.py`
- `backend/app/services/meta_cloud.py`

## Audit Trail

- EXTRACTED: 29 (88%)
- INFERRED: 4 (12%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*