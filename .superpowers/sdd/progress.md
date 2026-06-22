# SDD Progress Ledger — QA Audit Critical Fixes
Base: 6bdfeee
Branch: fix/qa-audit-criticals

## Tasks
- Task 1: Callers CRUD role checks + admin reads + /winners owner exclusion + IDOR fix (callers.py)
- Task 2: TelecallingConfigUpdate missing fields + contact_recycler config key (app_settings.py + contact_recycler.py)
- Task 3: Leads caller scope bypass (leads.py)
- Task 4: SourceType missing channels (schemas.py)
- Task 5: numbers.py stale api_key field (numbers.py)
- Task 6: Operator console wrong handover status (operator.py)
- Task 7: ai_reply.py NameError on COLLECT_DONE path (ai_reply.py)
- Task 8: Telegram webhook 500 on lead creation failure (telegram.py)
Task 1: complete (commits 6bdfeee..945a4bb, review clean)
Task 2: complete (commits 945a4bb..99cc0db, review clean)
Task 3: complete (commits 99cc0db..92a205f, review clean)
Task 4: complete (commits 92a205f..c6810c0, review clean)
Task 5: complete (commits c6810c0..de2d1e7, review clean)
Task 6: complete (commits de2d1e7..7f8e690, review clean)
Task 7: complete (commits 7f8e690..9aa8184, review clean)
Task 8: complete (commits 9aa8184..c9a1158, review clean)

## Round 2 — Remaining HIGHs
Base: c9a1158
- Task 9: Settings upsert missing on_conflict (app_settings.py)
- Task 10: reassign_backlog wrong column + no CAS guard (assignment.py)
- Task 11: Shift modes identical — common mode ignores per-caller overrides (assignment.py)
- Task 12: Register _process_callback_reassignments in APScheduler (main.py)
- Task 13: Register _sync_all_number_quality in APScheduler (main.py)
- Task 14: Register generate_all_digests in APScheduler (main.py)
- Task 15: Update CLAUDE.md — mark Bot Flow Builder as removed
Task 9: complete (commits c9a1158..0b236f2, review clean)
Task 10: complete (commits 0b236f2..bcaedbd, review clean)
Task 11: complete (commits bcaedbd..772c003, review clean)
Tasks 12-14: complete (commits 772c003..a34f67d, review clean)
Task 15: complete (commits a34f67d..2aba566, review clean)

## Round 3 — MEDIUMs
Base: 04acd35
Branch: fix/qa-audit-mediums
- Task 16: CSV export role-gate (leads.py)
- Task 17: AI Tune owner guard (ai_tune.py)
- Task 18: Inbound WhatsApp leads missing opt_in_source (webhook.py)
- Task 19: Recycled leads clear assigned_to (contact_recycler.py)
- Task 20: /next-lead shift hours check (calls.py)
- Task 21: reassign_backlog hardcoded segment (assignment.py)
- Task 22: Remove trigger E from validation (app_settings.py or ai_reply.py)
- Task 23: TeleCMI secret redaction in logs (calls.py)
- Task 24: Daily digest UTC→IST boundaries (call_digest.py)
- Task 25: Bulk-send direct API opt_in_source filter (leads.py)
- Task 26: Razorpay webhook missing-secret error message (bookings.py)
- Task 27: todos.py tenant_id filter (todos.py)
- Task 28: system.py status endpoint role-gate (system.py)
- Task 29: Reply source badge value — verify/fix (ai_reply.py + frontend)
Task 16: complete (03ef4ee)
Task 17: complete (03ef4ee)
Task 18: complete (03ef4ee)
Task 19-22: complete (03ef4ee..3949c4c)
Task 23-26: complete (3949c4c..d7ba3c0)
Task 27-29: complete (d7ba3c0..d25c492)

## Round 4 — LOWs
Base: 75d2c9b
Branch: fix/qa-audit-lows
- Task 30: Remove dead is_first_message in instagram/telegram/facebook
- Task 31: Assignment log group by caller_id not caller_name
- Task 32: Add tenant_id to coaching/summarizer/callers queries
- Task 33: Call scripts /resolve — use segment param
- Task 34: Incidents page owner guard
- Task 35: Reengagement delete_step 404 check
- Task 36: Follow-ups /run owner gate
- Task 37: Delete orphaned .pyc files
- Task 38: /winners group by caller_id not name
Task 30-33: complete (75d2c9b..eadbaa3)
