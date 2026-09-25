-- TeleCMI call scoring v4 (CallIQ Steps 1-2). Additive only; drops live in 206.
ALTER TABLE call_logs
  ADD COLUMN IF NOT EXISTS call_group text
    CHECK (call_group IN ('not_connected','very_short','early_exit','real_conversation')),
  ADD COLUMN IF NOT EXISTS talk_share numeric(5,2),
  ADD COLUMN IF NOT EXISTS interruption_count integer,
  ADD COLUMN IF NOT EXISTS interruptions_per_5min numeric(6,2),
  ADD COLUMN IF NOT EXISTS score_final boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS rules_version text,
  ADD COLUMN IF NOT EXISTS wrapup_callback_at timestamptz;

CREATE TABLE IF NOT EXISTS call_alerts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  call_log_id uuid REFERENCES call_logs(id) ON DELETE CASCADE,
  caller_id uuid REFERENCES callers(id) ON DELETE SET NULL,
  type text NOT NULL CHECK (type IN (
    'rude','wrong_info','crm_mismatch','no_proof','transcript_failed',
    'language_barrier','lead_source_quality','tracks_swapped'
  )),
  quote text,
  detail jsonb NOT NULL DEFAULT '{}'::jsonb,
  notified_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  seen_at timestamptz,
  seen_by uuid
);

CREATE UNIQUE INDEX IF NOT EXISTS call_alerts_call_type_uniq
  ON call_alerts (call_log_id, type) WHERE call_log_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS call_alerts_tenant_unseen_idx
  ON call_alerts (tenant_id, seen_at, created_at DESC);
CREATE INDEX IF NOT EXISTS call_alerts_caller_notified_idx
  ON call_alerts (caller_id, notified_at);

ALTER TABLE call_alerts ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS call_alerts_tenant_member_select ON call_alerts;
CREATE POLICY call_alerts_tenant_member_select ON call_alerts
  FOR SELECT TO authenticated USING (is_tenant_member(tenant_id));
