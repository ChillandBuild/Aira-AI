-- Count what Meta counts (2026-10-17).
--
-- Meta's messaging limit is "the maximum number of unique WhatsApp user phone
-- numbers your business can deliver messages to outside of a customer service
-- window" in a moving 24-hour period, shared by every number in the business
-- portfolio. phone_numbers.daily_send_count counted every template send and
-- reset at midnight, so it drifted from Meta's number both ways.
--
-- template_send_log: one row per template that went out to someone whose
-- 24-hour window with that number was closed. Written by the backend only
-- (service role); usage = distinct recipients in the last 24 hours.
-- Rows older than 2 days are pruned by the scheduler.
--
-- Additive. Apply BEFORE deploying the backend that writes/reads it.

CREATE TABLE IF NOT EXISTS public.template_send_log (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  phone_number_id uuid REFERENCES phone_numbers(id) ON DELETE SET NULL,
  recipient text NOT NULL,
  sent_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS template_send_log_tenant_sent_at
  ON public.template_send_log (tenant_id, sent_at);

-- Backend-only: RLS on with no policies, so only the service role reads/writes.
ALTER TABLE public.template_send_log ENABLE ROW LEVEL SECURITY;

-- Per-number and whole-business usage over the moving 24 hours.
-- Row with phone_number_id NULL = the business total (distinct across numbers).
-- first_sent_at = the oldest counted send still inside the window (when a slot frees up).
CREATE OR REPLACE FUNCTION public.messaging_limit_usage(p_tenant uuid)
RETURNS TABLE (phone_number_id uuid, recipients bigint, first_sent_at timestamptz)
LANGUAGE sql STABLE
SET search_path = public
AS $$
  SELECT l.phone_number_id, count(DISTINCT l.recipient), min(l.sent_at)
  FROM template_send_log l
  WHERE l.tenant_id = p_tenant AND l.sent_at > now() - interval '24 hours'
    AND l.phone_number_id IS NOT NULL
  GROUP BY l.phone_number_id
  UNION ALL
  SELECT NULL::uuid, count(DISTINCT l.recipient), min(l.sent_at)
  FROM template_send_log l
  WHERE l.tenant_id = p_tenant AND l.sent_at > now() - interval '24 hours';
$$;

REVOKE ALL ON FUNCTION public.messaging_limit_usage(uuid) FROM PUBLIC, anon, authenticated;
