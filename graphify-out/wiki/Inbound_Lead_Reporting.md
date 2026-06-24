# Inbound Lead Reporting

> 37 nodes · cohesion 0.10

## Key Concepts

- **InboundLead** (19 connections) — `frontend/lib/api.ts`
- **inbound_leads.py** (10 connections) — `backend/app/routes/inbound_leads.py`
- **list_inbound_leads()** (10 connections) — `backend/app/routes/inbound_leads.py`
- **export_inbound_leads()** (10 connections) — `backend/app/routes/inbound_leads.py`
- **str** (8 connections) — `backend/app/routes/inbound_leads.py`
- **aggregate_inbound()** (8 connections) — `backend/app/services/inbound_leads_logic.py`
- **_fetch_inbound_leads()** (7 connections) — `backend/app/routes/inbound_leads.py`
- **_fetch_campaign_names()** (6 connections) — `backend/app/routes/inbound_leads.py`
- **_fetch_first_keywords()** (6 connections) — `backend/app/routes/inbound_leads.py`
- **_enrich()** (6 connections) — `backend/app/routes/inbound_leads.py`
- **_fmt_ist()** (5 connections) — `backend/app/routes/inbound_leads.py`
- **list_campaigns()** (5 connections) — `backend/app/routes/inbound_leads.py`
- **inbound_leads_logic.py** (5 connections) — `backend/app/services/inbound_leads_logic.py`
- **is_inbound_lead()** (5 connections) — `backend/app/services/inbound_leads_logic.py`
- **lead_origin()** (5 connections) — `backend/app/services/inbound_leads_logic.py`
- **test_inbound_leads_logic.py** (5 connections) — `backend/tests/test_inbound_leads_logic.py`
- **int** (2 connections) — `backend/app/routes/inbound_leads.py`
- **Inbound Leads — all leads that arrived through a messaging channel.  Inbound uni** (2 connections) — `backend/app/routes/inbound_leads.py`
- **bool** (2 connections) — `backend/app/services/inbound_leads_logic.py`
- **str** (2 connections) — `backend/app/services/inbound_leads_logic.py`
- **True when the lead arrived through a messaging channel (not upload/manual).** (2 connections) — `backend/app/services/inbound_leads_logic.py`
- **test_is_inbound_lead_excludes_upload_and_manual()** (2 connections) — `backend/tests/test_inbound_leads_logic.py`
- **test_lead_origin_is_ad_when_campaign_present_else_organic()** (2 connections) — `backend/tests/test_inbound_leads_logic.py`
- **test_aggregate_inbound_splits_organic_vs_ad_and_buckets_by_utc_day()** (2 connections) — `backend/tests/test_inbound_leads_logic.py`
- **Format UTC ISO timestamp to IST string.** (1 connections) — `backend/app/routes/inbound_leads.py`
- *... and 12 more nodes in this community*

## Relationships

- [[Operator Console & Audit]] (3 shared connections)
- [[Conversation List UI]] (3 shared connections)
- [[App Entry & Schedulers]] (2 shared connections)
- [[Analytics API]] (1 shared connections)
- [[Shared Component]] (1 shared connections)
- [[API Client (frontend)]] (1 shared connections)

## Source Files

- `backend/app/routes/inbound_leads.py`
- `backend/app/services/inbound_leads_logic.py`
- `backend/tests/test_inbound_leads_logic.py`
- `frontend/lib/api.ts`

## Audit Trail

- EXTRACTED: 139 (93%)
- INFERRED: 10 (7%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*