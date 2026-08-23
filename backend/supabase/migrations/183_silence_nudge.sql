-- 183_silence_nudge.sql
-- A short contextual follow-up sent minutes after a live AI reply that went
-- unanswered. Separate from reengagement_steps: that engine dedups per
-- (lead, step) with no time bound (one send per lead forever), which is
-- structurally incompatible with a nudge that must fire again on the next lull.

-- The constraint extension comes FIRST and is not optional. expert_handoff
-- inserted an unlisted reply_source from migration 168 to 173; every insert
-- raised 23514, the exception escaped _send_and_log(), and webhook.py fell
-- through to generate_reply() -- answering the same inbound message twice.
-- Live-caught 2026-08-11. 'autopilot' is deliberately absent (dropped in 173).
ALTER TABLE messages DROP CONSTRAINT IF EXISTS messages_reply_source_check;
ALTER TABLE messages ADD CONSTRAINT messages_reply_source_check
  CHECK (reply_source IN ('knowledge','ai','automation','reengagement','expert_handoff','silence_nudge'));

CREATE TABLE IF NOT EXISTS silence_nudge_jobs (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         uuid NOT NULL,
  lead_id           uuid NOT NULL,
  -- The outbound message that started the clock. At fire time the newest
  -- message in the thread must still be this one, or the lead has replied.
  anchor_message_id uuid NOT NULL,
  step_index        int  NOT NULL DEFAULT 0,
  fire_at           timestamptz NOT NULL,
  status            text NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending','sent','cancelled','skipped','failed')),
  skip_reason       text,
  message_preview   text,
  created_at        timestamptz NOT NULL DEFAULT now(),
  sent_at           timestamptz
);

CREATE INDEX IF NOT EXISTS idx_silence_nudge_due
  ON silence_nudge_jobs (fire_at) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_silence_nudge_lead_pending
  ON silence_nudge_jobs (lead_id) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_silence_nudge_cap
  ON silence_nudge_jobs (lead_id, sent_at) WHERE status = 'sent';

-- RLS is enabled automatically by the ensure_rls event trigger (migration 175).
-- No policies by design: anon and authenticated are denied outright, and the
-- backend reaches this table only through the service-role client. The absence
-- of policies IS the security posture -- do not "fix" it with a permissive one.
