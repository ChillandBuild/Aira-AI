# Meta Cloud Service

> 14 nodes · cohesion 0.22

## Key Concepts

- **UpdateTemplate** (16 connections) — `backend/app/routes/templates.py`
- **update_template()** (11 connections) — `backend/app/routes/templates.py`
- **_strip_emojis()** (9 connections) — `backend/app/services/meta_cloud.py`
- **_build_button_components()** (9 connections) — `backend/app/services/meta_cloud.py`
- **_sanitize_header_or_footer()** (7 connections) — `backend/app/services/meta_cloud.py`
- **_extract_variable_examples()** (7 connections) — `backend/app/services/meta_cloud.py`
- **Edit a REJECTED or PAUSED template. Updates local DB and pushes changes to Meta** (2 connections) — `backend/app/routes/templates.py`
- **Update a rejected/paused template on Meta.     Calls POST https://graph.facebook** (2 connections) — `backend/app/services/meta_cloud.py`
- **Drop emoji code points (and ZWJ / variation selectors) from a string.** (1 connections) — `backend/app/services/meta_cloud.py`
- **Meta rejects newlines, formatting characters, and emojis in HEADER/FOOTER     te** (1 connections) — `backend/app/services/meta_cloud.py`
- **Return placeholder example values for every {{N}} variable in the body.** (1 connections) — `backend/app/services/meta_cloud.py`
- **Shared button-component builder used by main template + carousel cards.** (1 connections) — `backend/app/services/meta_cloud.py`
- **Return placeholder example values for every {{N}} variable in the body.** (1 connections) — `backend/app/services/meta_cloud.py`
- **Shared button-component builder used by main template + carousel cards.** (1 connections) — `backend/app/services/meta_cloud.py`

## Relationships

- [[Meta Cloud API Client]] (13 shared connections)
- [[Templates API]] (10 shared connections)
- [[Operator Console & Audit]] (4 shared connections)
- [[Leads API]] (1 shared connections)
- [[Meta Cloud Service]] (1 shared connections)

## Source Files

- `backend/app/routes/templates.py`
- `backend/app/services/meta_cloud.py`

## Audit Trail

- EXTRACTED: 45 (65%)
- INFERRED: 24 (35%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*