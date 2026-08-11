-- expert_handoff.py's _send_and_log() has inserted reply_source='expert_handoff'
-- since the feature shipped (migration 168), but the check constraint was never
-- extended to allow it — every expert-handoff outbound message logging insert has
-- been failing with a 23514 violation, which (uncaught in _send_and_log) propagates
-- out of route_expert_handoff() and causes webhook.py to also fall through to the
-- normal generate_reply() path for the same inbound message. Live-caught 2026-08-11.
ALTER TABLE messages DROP CONSTRAINT IF EXISTS messages_reply_source_check;
ALTER TABLE messages ADD CONSTRAINT messages_reply_source_check
  CHECK (reply_source IN ('knowledge', 'ai', 'automation', 'reengagement', 'expert_handoff'));
