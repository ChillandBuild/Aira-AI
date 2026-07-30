-- Store ad-set budgets for accounts using ad-set budget optimization.
-- The existing ad_sets RLS policies continue to protect these additive fields.

ALTER TABLE public.ad_sets
  ADD COLUMN IF NOT EXISTS meta_ad_account_id text,
  ADD COLUMN IF NOT EXISTS daily_budget numeric(14,2),
  ADD COLUMN IF NOT EXISTS lifetime_budget numeric(14,2);

CREATE INDEX IF NOT EXISTS idx_ad_sets_account
  ON public.ad_sets (tenant_id, meta_ad_account_id, meta_adset_id);
