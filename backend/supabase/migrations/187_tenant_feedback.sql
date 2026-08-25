-- 187_tenant_feedback.sql
-- Free-text product feedback from the dashboard's account menu.
--
-- Backend-only table (service role), same pattern as quick_reply_blocks
-- (migration 184): RLS enabled, no client policies, so anon/authenticated
-- clients are denied and only the FastAPI backend can read/write it.

CREATE TABLE IF NOT EXISTS tenant_feedback (
  id         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id  uuid        NOT NULL,
  user_id    uuid        NOT NULL,
  message    text        NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS tenant_feedback_tenant_idx
  ON tenant_feedback (tenant_id, created_at DESC);

ALTER TABLE tenant_feedback ENABLE ROW LEVEL SECURITY;
