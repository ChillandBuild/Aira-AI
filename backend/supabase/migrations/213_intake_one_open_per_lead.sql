-- 213_intake_one_open_per_lead.sql
-- One open deal per lead, enforced by the database instead of code alone.
-- Checked 2026-09-30: 0 leads have more than one open row.
-- Apply AFTER the R3 "start fresh closes the old deal first" code is live.

CREATE UNIQUE INDEX IF NOT EXISTS uq_intake_one_open_per_lead
  ON intake_sessions (tenant_id, lead_id)
  WHERE status NOT IN ('paid', 'cancelled', 'resolved');
