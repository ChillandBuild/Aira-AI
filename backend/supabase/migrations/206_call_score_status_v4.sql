-- Allow the v4 score statuses alongside the old ones. The old values are mapped and removed after deploy (migration 207).
ALTER TABLE call_logs DROP CONSTRAINT IF EXISTS call_logs_score_status_check;
ALTER TABLE call_logs ADD CONSTRAINT call_logs_score_status_check CHECK (score_status IS NULL OR score_status = ANY (ARRAY['pending','awaiting_outcome','scored','short_call','no_answer','no_recording','failed','processing','not_connected','very_short','early_exit','provisional']));
