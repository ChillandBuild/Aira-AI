-- 188_precall_brief_cache.sql
-- Caches the AI pre-call brief (leads.py::pre_call_brief) so opening a lead
-- repeatedly is free. precall_brief_fingerprint is the latest message + call
-- timestamp the brief was built from; a mismatch means new activity happened
-- since and the brief is regenerated. NULL fingerprint (all existing rows)
-- always misses, so nothing needs backfilling.

ALTER TABLE leads
  ADD COLUMN IF NOT EXISTS precall_brief jsonb,
  ADD COLUMN IF NOT EXISTS precall_brief_fingerprint text;
