-- Migration 166: abort support + cancelled/aborted lifecycle states for scheduled_broadcasts
-- Lets "Send Now" broadcasts be stopped mid-flight and pending scheduled/drip
-- broadcasts be cancelled before they fire.

ALTER TABLE scheduled_broadcasts
  ADD COLUMN IF NOT EXISTS abort_requested boolean NOT NULL DEFAULT false;

ALTER TABLE scheduled_broadcasts
  DROP CONSTRAINT IF EXISTS scheduled_broadcasts_status_check;

ALTER TABLE scheduled_broadcasts
  ADD CONSTRAINT scheduled_broadcasts_status_check
  CHECK (status IN ('pending', 'running', 'done', 'failed', 'cancelled', 'aborted'));

ALTER TABLE broadcast_recipients
  DROP CONSTRAINT IF EXISTS broadcast_recipients_send_status_check;

ALTER TABLE broadcast_recipients
  ADD CONSTRAINT broadcast_recipients_send_status_check
  CHECK (send_status IN ('sent', 'failed', 'rejected', 'opted_out_skip', 'aborted_skip'));
