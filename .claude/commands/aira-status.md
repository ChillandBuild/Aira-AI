---
name: aira-status
description: Session-end checklist — save memories, audit stale files, show backlog and session starter
---

When this skill is invoked, do the following in order:

## Step 1 — Save session memories
Review this conversation and save anything worth remembering:
- New decisions, architectural choices, fixes
- Corrections to previously wrong memory
- Patterns or rules learned
Write to memory/ directory.

## Step 2 — Audit all memory files
Check every file in memory/:
- Delete anything no longer true
- Update stale facts
- Merge duplicates
- Update MEMORY.md index to match

## Step 3 — Print remaining backlog
```
AIRA AI — REMAINING BACKLOG
════════════════════════════
RECENTLY COMPLETED
  [x] WhatsApp Insights page — Meta API, DB snapshots, sync button, CSS trends
  [x] Pin contacts — fixed 204 PostgREST error via toggle_lead_pin RPC
  [x] FAQ removed — replaced with RAG-only pipeline (Groq + knowledge base)
  [x] Language detection — _detect_lang, [Respond in X] hint injection
  [x] .txt file support — knowledge document uploads
  [x] Conversation page default to "All" platform filter
  [x] pinned_at added to Lead Pydantic model

TECH DEBT
  [ ] RLS on 18 tables — app-layer tenant filter is only guard
  [ ] Booking dynamic pricing — amount hardcoded at Rs.500

PENDING DB MIGRATIONS (run in Supabase SQL Editor)
  [ ] 064: alter table leads add pinned_at timestamptz
  [ ] 066: whatsapp_insights_snapshots table
  [ ] 067: get_conversation_leads RPC (pinned + sort)
  [ ] 068: toggle_lead_pin RPC function
  [ ] 070: drop faqs cascade, alter reply_source CHECK constraint

CRITICAL CONTEXT
  - Supabase project ref: tovmebyyjhvszwgvyfdm
  - Backend on Render: https://aira-ai-5tfr.onrender.com
  - Frontend on Vercel (auto-deploys from main)
  - postgrest-py 1.1.1 throws APIError on 204 — use RPC or catch exception
  - reply_source CHECK allows 'knowledge', 'ai', 'automation' (no 'faq')
```
