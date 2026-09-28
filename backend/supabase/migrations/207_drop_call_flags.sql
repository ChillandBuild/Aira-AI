-- 207_drop_call_flags.sql
-- TeleCMI call scoring v4 clean-up. Apply ONLY AFTER the v4 code is deployed.
-- The old no-answer safety-gate flag and the 7+3 breakdown are replaced by
-- call_alerts and evaluation v4. Fold the pre-v4 score_status values into the v4
-- set, re-queue any call still scored on v3, then narrow the check (206 widened
-- it to old ∪ new only so pre-deploy writes wouldn't fail).

UPDATE call_logs SET score_status = 'very_short' WHERE score_status = 'short_call';
UPDATE call_logs SET score_status = 'not_connected' WHERE score_status = 'no_answer';
UPDATE call_logs SET score_status = 'processing' WHERE score_status IN ('pending', 'awaiting_outcome', 'no_recording');

-- Calls still carrying a v3 evaluation: clear the old score and hand them back to
-- the AI sweep (ai_status pending, backdated past RETRY_AFTER) so they are re-scored on v4.
UPDATE call_logs
SET score = NULL,
    score_status = 'processing',
    ai_status = 'pending',
    ai_attempts = 0,
    ai_updated_at = now() - interval '5 minutes'
WHERE provider = 'telecmi'
  AND evaluation IS NOT NULL
  AND (evaluation->>'evaluation_version') IS DISTINCT FROM '4';

ALTER TABLE call_logs
  DROP COLUMN IF EXISTS flag_status,
  DROP COLUMN IF EXISTS flag_reason,
  DROP COLUMN IF EXISTS flagged_at,
  DROP COLUMN IF EXISTS flag_resolved_by,
  DROP COLUMN IF EXISTS flag_resolved_at,
  DROP COLUMN IF EXISTS score_breakdown;

ALTER TABLE call_logs DROP CONSTRAINT IF EXISTS call_logs_score_status_check;
ALTER TABLE call_logs ADD CONSTRAINT call_logs_score_status_check
  CHECK (score_status IS NULL OR score_status = ANY (ARRAY['processing','not_connected','very_short','early_exit','provisional','scored','failed']));
