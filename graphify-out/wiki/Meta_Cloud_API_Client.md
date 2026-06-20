# Meta Cloud API Client

> 30 nodes · cohesion 0.13

## Key Concepts

- **meta_cloud.py** (29 connections) — `backend/app/services/meta_cloud.py`
- **str** (26 connections) — `backend/app/services/meta_cloud.py`
- **_creds()** (23 connections) — `backend/app/services/meta_cloud.py`
- **send_media_message()** (8 connections) — `backend/app/services/meta_cloud.py`
- **send_text_message()** (7 connections) — `backend/app/services/meta_cloud.py`
- **download_media_from_meta()** (7 connections) — `backend/app/services/meta_cloud.py`
- **send_template_message()** (7 connections) — `backend/app/services/meta_cloud.py`
- **send_list_message()** (6 connections) — `backend/app/services/meta_cloud.py`
- **send_catalog_message()** (6 connections) — `backend/app/services/meta_cloud.py`
- **list_all_templates()** (6 connections) — `backend/app/services/meta_cloud.py`
- **delete_template_from_meta()** (6 connections) — `backend/app/services/meta_cloud.py`
- **update_template_on_meta()** (6 connections) — `backend/app/services/meta_cloud.py`
- **send_location_message()** (5 connections) — `backend/app/services/meta_cloud.py`
- **send_audio_message()** (5 connections) — `backend/app/services/meta_cloud.py`
- **get_number_quality()** (5 connections) — `backend/app/services/meta_cloud.py`
- **send_cta_url_message()** (4 connections) — `backend/app/services/meta_cloud.py`
- **send_interactive_buttons()** (4 connections) — `backend/app/services/meta_cloud.py`
- **Send an audio message. WhatsApp does not support captions on audio.** (2 connections) — `backend/app/services/meta_cloud.py`
- **float** (1 connections) — `backend/app/services/meta_cloud.py`
- **Send a media message via Meta Cloud API.     wa_type: 'image' | 'document' | 'au** (1 connections) — `backend/app/services/meta_cloud.py`
- **Send a WhatsApp interactive list message (up to 10 rows across sections).** (1 connections) — `backend/app/services/meta_cloud.py`
- **Send a WhatsApp product catalog message (product_list interactive type).** (1 connections) — `backend/app/services/meta_cloud.py`
- **Download media from Meta by media_id.     Returns: (bytes, mime_type, url)** (1 connections) — `backend/app/services/meta_cloud.py`
- **Fetch all templates from Meta for a WABA, handling pagination.     Returns list** (1 connections) — `backend/app/services/meta_cloud.py`
- **Delete a template from Meta by name.     Calls DELETE https://graph.facebook.com** (1 connections) — `backend/app/services/meta_cloud.py`
- *... and 5 more nodes in this community*

## Relationships

- [[Meta Cloud Service]] (26 shared connections)
- [[Operator Console & Audit]] (13 shared connections)
- [[Templates API]] (4 shared connections)
- [[Calls API (TeleCMI dialer)]] (3 shared connections)
- [[Booking Flow]] (3 shared connections)
- [[Instagram Channel]] (1 shared connections)
- [[Tenant]] (1 shared connections)
- [[CSV Upload & Bulk Send]] (1 shared connections)
- [[Broadcast Executor & Outbound Router]] (1 shared connections)
- [[Reengagement Service]] (1 shared connections)
- [[Phone Numbers Pool]] (1 shared connections)

## Source Files

- `backend/app/services/meta_cloud.py`

## Audit Trail

- EXTRACTED: 163 (94%)
- INFERRED: 11 (6%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*