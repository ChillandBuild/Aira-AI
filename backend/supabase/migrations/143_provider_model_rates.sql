-- 143: Admin-set cost rates per (provider, model), used to estimate ₹ spend
-- from tenant_token_usage's raw token counts (migration 142). No tenant reads
-- this table -- it's pure internal pricing config, admin-only, since Aira
-- (not the tenant) funds every provider account and sets its own rates.
-- A missing row for a (provider, model) pair means "no rate configured yet";
-- callers must treat that as an unknown cost, never silently zero.

CREATE TABLE public.provider_model_rates (
  provider text NOT NULL,
  model text NOT NULL,
  input_rate_per_1k_inr numeric NOT NULL,
  output_rate_per_1k_inr numeric NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (provider, model)
);

ALTER TABLE public.provider_model_rates ENABLE ROW LEVEL SECURITY;

CREATE POLICY provider_model_rates_admin_all ON public.provider_model_rates
  USING (EXISTS (SELECT 1 FROM system_admins WHERE system_admins.user_id = auth.uid()));
