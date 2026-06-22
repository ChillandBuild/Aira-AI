# P1 — Telecalling Features QA Audit

You are QA-auditing Aira AI before first client deployment. Read CLAUDE.md for full context.

## Task
Audit each telecalling feature. Read the route, service, AND frontend. Flag logic bugs, missing error handling, broken data flow, invariant violations, security gaps, race conditions.

## Features to Audit

### 12. Callers CRUD + Team Management
- Backend: backend/app/routes/callers.py + routes/team.py
- Frontend: frontend/app/dashboard/team/
- Check: create/edit/delete callers, role assignment (owner vs caller), tenant isolation

### 13. Telecaller Auto-Assignment
- Backend: backend/app/services/assignment.py
- Check: state-based assignment + sweep_unassigned_leads (2-min APScheduler), round-robin least-loaded, telecalling_config gating (enabled + segment + channel), admin exclusion (Hard Invariant #13)

### 14. Assignment Log
- Backend: backend/app/routes/assignment_log.py
- Frontend: AdminView.tsx (Assignment Log tab)
- Check: lead_stage_events 'assigned'/'reassigned' recorded correctly, audit trail completeness

### 15. Telecaller Cockpit
- Frontend: frontend/app/dashboard/telecalling/CallerView.tsx
- Backend: backend/app/routes/calls.py (/pending-wrapups + /next-lead)
- Check: mandatory wrap-up modal, Call Next atomic claim, queue tabs by call_status, no race condition on /next-lead

### 16. Admin Telecalling Monitoring
- Frontend: frontend/app/dashboard/telecalling/AdminView.tsx
- Backend: backend/app/routes/analytics.py (telecalling endpoints)
- Check: Performance tab, connect rate, idle/bunking, speed-to-lead, quality; owner-gated caller-timeline/qa-queue/export; admin excluded from metrics (Hard Invariant #13)

### 17. Manual Dial (TeleCMI Click-to-Call)
- Backend: backend/app/services/telecmi_client.py + routes/calls.py
- Check: click-to-call triggers correctly, call log created, error handling for TeleCMI API failures

### 18. Call Recording + Transcription
- Backend: backend/app/services/call_summarizer.py
- Check: 3-layer funnel (record 100% → transcribe ≥30s → evaluate ≥60s), new-caller bypass, per-tenant daily cap via telecalling_config.eval_daily_cap, recordings to Supabase Storage only (Hard Invariant #5)

### 19. AI Coaching Post-Call
- Backend: backend/app/services/call_coach.py
- Check: coaching generation logic, model used is Groq (Hard Invariant #9), handles missing transcription gracefully

### 20. Call Scoring
- Backend: backend/app/services/call_scorer.py
- Check: scoring criteria, output format, handles edge cases (very short calls, no audio)

### 21. Call-Status Pipeline + DNC
- Backend: leads.call_status field + routes/calls.py
- Check: call_status (new/in_progress/callback/converted/not_interested/dnc/unreachable) orthogonal to segment (Hard Invariant #11), do_not_call is lead-level not outcome (Hard Invariant #12), no_answer ≥ max_call_attempts → unreachable

### 22. Call Scripts
- Backend: backend/app/routes/call_scripts.py
- Frontend: ScriptPanel in CallerView cockpit
- Check: CRUD, segment-based resolution (segment script > default), branching steps with goto navigation

### 23. Callback Scheduler & Reassignment
- Backend: backend/app/routes/follow_ups.py + main.py _process_callback_reassignments
- Check: follow_up_jobs cadence=callback, 60s polling reminders, away-caller reassignment (1-min job), exclude_caller_ids logic

### 24. Contact Recycling
- Backend: backend/app/services/contact_recycler.py
- Check: re-queue no_answer leads to "new" after configurable delay, IST calling hours respected, max retries, 30-min APScheduler job

### 25. Shift Time Management
- Backend: callers.shift_start_hour/shift_end_hour (migration 112)
- Frontend: TelecallingConfigPanel + LiveAgentStatus
- Check: common vs per-caller shift hours, outside-shift amber indicator, ShiftTimeline dynamic hour range

### 26. Caller Daily Digest
- Backend: backend/app/services/call_digest.py
- Check: daily digest generation per caller, content accuracy, scheduling

## Output Format
For each feature (12-26), report:
```
### Feature N: [Name]
- **Status**: PASS | FAIL | WARN
- **Files checked**: [paths with line numbers]
- **Issues found**:
  - [CRITICAL|HIGH|MEDIUM|LOW] Description — reproduction steps — fix suggestion
- **Notes**: any observations
```

End with summary table: feature | status | critical count | high count.
