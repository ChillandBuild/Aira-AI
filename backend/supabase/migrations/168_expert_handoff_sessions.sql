-- 168_expert_handoff_sessions.sql
-- Generic per-tenant "paid expert handoff" flow: a lead opts in to pay for a
-- human consultation, details are collected in free-flowing conversation
-- (LLM slot-filling, not a rigid step order), payment happens in-chat via
-- Razorpay. One row per lead per attempt.

CREATE TABLE IF NOT EXISTS expert_handoff_sessions (
  id             uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      uuid        NOT NULL,
  lead_id        uuid        NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
  status         text        NOT NULL DEFAULT 'offer_pending'
                   CHECK (status IN (
                     'offer_pending', 'collecting', 'awaiting_confirmation',
                     'awaiting_payment', 'paid', 'resolved', 'cancelled'
                   )),
  collected_data jsonb       NOT NULL DEFAULT '{}',
  trigger_reason text,
  amount_paise   integer,
  payment_link   text,
  razorpay_payment_id text,
  paid_at        timestamptz,
  resolved_at    timestamptz,
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS expert_handoff_lead_idx   ON expert_handoff_sessions (lead_id, tenant_id);
CREATE INDEX IF NOT EXISTS expert_handoff_status_idx ON expert_handoff_sessions (status, tenant_id);

-- Backend-only table (service role), same pattern as platform_defaults
-- (migration 143): RLS enabled, no client policies, so anon/authenticated
-- clients are denied and only the service role (used by the FastAPI backend)
-- can read/write it.
ALTER TABLE expert_handoff_sessions ENABLE ROW LEVEL SECURITY;
