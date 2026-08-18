-- 180_intake_followup_counter.sql
-- Per-session follow-up counter for the AstroTamil bridge.
--
-- astro_bridge.push_followup() sends external_ref "{session_id}::f{n}", and Django
-- derives its idempotency key from that ref. A repeated n is silently swallowed on
-- their side, so n must be monotonic per session and must survive a restart —
-- hence a column rather than anything derived at send time.
--
-- NOT NULL DEFAULT 0: every existing paid session has had zero follow-ups.

ALTER TABLE intake_sessions
  ADD COLUMN IF NOT EXISTS astro_followup_count integer NOT NULL DEFAULT 0;
