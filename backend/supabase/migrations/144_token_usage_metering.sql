-- 142: Per-tenant LLM token consumption metering.
-- One row per (tenant, day, purpose, provider, model). Written only via
-- increment_token_usage() from the backend (service role); tenants read their
-- own rows, system admins read/write all (same policy pattern as
-- tenant_usage_counters). Day bucket is IST so operator-facing daily charts
-- match the business day.

CREATE TABLE public.tenant_token_usage (
  tenant_id uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
  usage_date date NOT NULL,
  purpose text NOT NULL,
  provider text NOT NULL,
  model text NOT NULL,
  calls bigint NOT NULL DEFAULT 0,
  input_tokens bigint NOT NULL DEFAULT 0,
  output_tokens bigint NOT NULL DEFAULT 0,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, usage_date, purpose, provider, model)
);

ALTER TABLE public.tenant_token_usage ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_token_usage_admin_all ON public.tenant_token_usage
  USING (EXISTS (SELECT 1 FROM system_admins WHERE system_admins.user_id = auth.uid()));

CREATE POLICY tenant_token_usage_tenant_read ON public.tenant_token_usage
  FOR SELECT
  USING (EXISTS (
    SELECT 1 FROM tenant_users tu
    WHERE tu.tenant_id = tenant_token_usage.tenant_id AND tu.user_id = auth.uid()
  ));

-- Atomic increment: INSERT ... ON CONFLICT DO UPDATE, immune to the
-- read-then-upsert race that concurrent replies would hit.
-- SECURITY INVOKER (default): the backend's service role bypasses RLS;
-- regular authenticated users have no INSERT policy, so they can't write
-- through this function either. Execute revoked from client roles anyway.
CREATE OR REPLACE FUNCTION public.increment_token_usage(
  p_tenant_id uuid,
  p_purpose text,
  p_provider text,
  p_model text,
  p_input_tokens bigint,
  p_output_tokens bigint
) RETURNS void
LANGUAGE sql
SET search_path = public
AS $$
  INSERT INTO tenant_token_usage
    (tenant_id, usage_date, purpose, provider, model, calls, input_tokens, output_tokens)
  VALUES
    (p_tenant_id, (now() AT TIME ZONE 'Asia/Kolkata')::date, p_purpose, p_provider, p_model,
     1, p_input_tokens, p_output_tokens)
  ON CONFLICT (tenant_id, usage_date, purpose, provider, model)
  DO UPDATE SET
    calls = tenant_token_usage.calls + 1,
    input_tokens = tenant_token_usage.input_tokens + EXCLUDED.input_tokens,
    output_tokens = tenant_token_usage.output_tokens + EXCLUDED.output_tokens,
    updated_at = now();
$$;

REVOKE EXECUTE ON FUNCTION public.increment_token_usage(uuid, text, text, text, bigint, bigint) FROM anon, authenticated;
