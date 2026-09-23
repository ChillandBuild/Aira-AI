-- Mandatory call feedback gate (SIM telecalling).
-- All columns are nullable/additive: existing rows and old code keep working.

ALTER TABLE call_logs
  ADD COLUMN IF NOT EXISTS direction text
    CHECK (direction IN ('outgoing', 'incoming', 'missed')),
  ADD COLUMN IF NOT EXISTS feedback_at timestamptz,
  ADD COLUMN IF NOT EXISTS feedback_dismissed_at timestamptz,
  ADD COLUMN IF NOT EXISTS feedback_dismissed_by text,
  ADD COLUMN IF NOT EXISTS feedback_dismiss_reason text;

ALTER TABLE callers
  ADD COLUMN IF NOT EXISTS last_sync_at timestamptz;

-- Rows still owing feedback, looked up per telecaller on every 5s poll.
CREATE INDEX IF NOT EXISTS idx_call_logs_feedback_pending
  ON call_logs (tenant_id, caller_id)
  WHERE feedback_at IS NULL AND feedback_dismissed_at IS NULL AND provider = 'sim_basic';
