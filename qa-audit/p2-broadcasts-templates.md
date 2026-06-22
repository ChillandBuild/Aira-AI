# P2 — Broadcasts & Templates QA Audit

You are QA-auditing Aira AI before first client deployment. Read CLAUDE.md for full context.

## Task
Audit each broadcast/template feature. Read the route, service, AND frontend. Flag logic bugs, missing error handling, broken data flow, invariant violations, security gaps, race conditions.

## Features to Audit

### 27. Message Templates CRUD
- Backend: backend/app/routes/templates.py
- Frontend: frontend/app/dashboard/templates/
- Check: create/read/update/delete templates, Quick Reply buttons (up to 3), validation

### 28. Template Submission to Meta API
- Backend: routes/templates.py + services/meta_cloud.py
- Check: MUST use meta_waba_id NOT meta_phone_number_id (Hard Invariant #8), correct Meta API payload format

### 29. Template Approval Webhook
- Endpoint: POST /api/v1/templates/webhook-status
- Check: handles approved/rejected status updates, updates local template status

### 30. Template Sync
- Endpoint: POST /api/v1/templates/{id}/sync
- Check: fetches current status from Meta, updates local record, handles Meta API errors

### 31. Carousel Templates
- Frontend: frontend/app/dashboard/templates/carousel/
- Check: 2-10 cards validation, carousel_cards JSONB structure, Meta API submission format

### 32. 7-Step CSV Upload
- Backend: backend/app/routes/upload.py
- Frontend: frontend/app/dashboard/(upload path)
- Check: all 7 steps complete, opt_in_source set on leads, multi-variable template personalization (variable_mapping + extra_cols), dedup logic

### 33. Bulk Send
- Backend: routes/upload.py
- Check: rejects leads with null opt_in_source (Hard Invariant #7), rate limiting, error handling per recipient

### 34. Scheduled Broadcasts
- Backend: scheduled_broadcasts table + main.py _process_scheduled_broadcasts (1-min job)
- Check: scheduling accuracy, timezone handling, APScheduler job fires correctly

### 35. Drip Broadcasts
- Backend: schedule_type=drip in upload.py
- Check: leads correctly split over N days, daily send logic, handles remainder leads

### 36. Broadcast History + Fail Reason
- Backend: broadcast_recipients table
- Check: fail_reason column populated on failures, queryable history, no silent drops

### 37. Broadcast Tags
- Backend: backend/app/routes/tags.py
- Frontend: frontend/app/dashboard/(tags area)
- Check: colored tags CRUD, tag assignment to broadcasts/leads, CSV export with tags

### 38. Per-Broadcast Lead Scoring
- Backend: broadcast_lead_scores table + services/scoring_engine.py
- Check: context-aware arc scoring, finalized_at freeze logic, tenant isolation

### 39. Broadcast Negative Reply + Sentiment
- Backend: broadcast_recipients.negative_reply + sentiment columns
- Check: negative reply detection, sentiment classification, data stored correctly

### 40. Broadcast Auto-Retry
- Backend: backend/app/services/broadcast_retry.py
- Check: re-sends 131049 (marketing cap) failures next day, attempt cap, per-attempt metrics

## Output Format
For each feature (27-40), report:
```
### Feature N: [Name]
- **Status**: PASS | FAIL | WARN
- **Files checked**: [paths with line numbers]
- **Issues found**:
  - [CRITICAL|HIGH|MEDIUM|LOW] Description — reproduction steps — fix suggestion
- **Notes**: any observations
```

End with summary table: feature | status | critical count | high count.
