# Upload API

> 21 nodes · cohesion 0.10

## Key Concepts

- **_segment_to_flags()** (12 connections) — `backend/app/routes/upload.py`
- **_collect_successful_tag_segment_rows()** (10 connections) — `backend/app/routes/upload.py`
- **download_all_tags_csv()** (10 connections) — `backend/app/routes/upload.py`
- **download_all_tags_combined()** (9 connections) — `backend/app/routes/upload.py`
- **Rows for tag exports: successful sends only, bucketed by current lead segment.** (1 connections) — `backend/app/routes/upload.py`
- **Download successful tag segment rows grouped by tag then broadcast.** (1 connections) — `backend/app/routes/upload.py`
- **Combined CSV across all tags.      mode=all: simple concatenation of all tags (n** (1 connections) — `backend/app/routes/upload.py`
- **Return (HOT, WARM, COLD) flags. D (disqualified) → all zero.** (1 connections) — `backend/app/routes/upload.py`
- **Rows for tag exports: successful sends only, bucketed by current lead segment.** (1 connections) — `backend/app/routes/upload.py`
- **Download successful tag segment rows grouped by tag then broadcast.** (1 connections) — `backend/app/routes/upload.py`
- **Combined CSV across all tags.      mode=all: simple concatenation of all tags (n** (1 connections) — `backend/app/routes/upload.py`
- **Return (HOT, WARM, COLD) flags. D (disqualified) → all zero.** (1 connections) — `backend/app/routes/upload.py`
- **Rows for tag exports: successful sends only, bucketed by current lead segment.** (1 connections) — `backend/app/routes/upload.py`
- **Download successful tag segment rows grouped by tag then broadcast.** (1 connections) — `backend/app/routes/upload.py`
- **Combined CSV across all tags.      mode=all: simple concatenation of all tags (n** (1 connections) — `backend/app/routes/upload.py`
- **Return (HOT, WARM, COLD) flags. D (disqualified) → all zero.** (1 connections) — `backend/app/routes/upload.py`
- **Download all-tags CSV grouped by tag then broadcast: name, phone, tag, template,** (1 connections) — `backend/app/routes/upload.py`
- **Combined CSV across all tags.      mode=all: simple concatenation of all tags (n** (1 connections) — `backend/app/routes/upload.py`
- **Return (HOT, WARM, COLD) flags. D (disqualified) → all zero.** (1 connections) — `backend/app/routes/upload.py`
- **Rows for tag exports: successful sends only, bucketed by current lead segment.** (1 connections) — `backend/app/routes/upload.py`
- **Download successful tag segment rows grouped by tag then broadcast.** (1 connections) — `backend/app/routes/upload.py`

## Relationships

- [[CSV Upload & Bulk Send]] (8 shared connections)
- [[Upload API]] (4 shared connections)
- [[Calls API (TeleCMI dialer)]] (2 shared connections)

## Source Files

- `backend/app/routes/upload.py`

## Audit Trail

- EXTRACTED: 56 (97%)
- INFERRED: 2 (3%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*