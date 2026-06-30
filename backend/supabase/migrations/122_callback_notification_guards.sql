-- Guard columns so callback notifications fire exactly once per scheduled slot.
-- Reset to NULL on reschedule (see reschedule_callback) so a new slot re-arms them.
ALTER TABLE follow_up_jobs
  ADD COLUMN IF NOT EXISTS due_notified_at       timestamptz,
  ADD COLUMN IF NOT EXISTS claimable_notified_at timestamptz;

CREATE INDEX IF NOT EXISTS idx_follow_up_jobs_callback_scan
  ON follow_up_jobs(tenant_id, cadence, status, scheduled_for);
