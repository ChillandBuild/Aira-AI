-- Scope imported Meta Ads data to the connected ad account and mark
-- Click-to-WhatsApp creatives explicitly. Existing rows stay unscoped until
-- Meta returns them again, so stale data from a previously connected account
-- cannot be mistaken for data from the current account.

ALTER TABLE public.ad_campaigns
  ADD COLUMN IF NOT EXISTS meta_ad_account_id text;

ALTER TABLE public.ad_creatives
  ADD COLUMN IF NOT EXISTS meta_ad_account_id text,
  ADD COLUMN IF NOT EXISTS is_click_to_whatsapp boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS optimization_goal text,
  ADD COLUMN IF NOT EXISTS effective_status text;

ALTER TABLE public.ad_insights_daily
  ADD COLUMN IF NOT EXISTS meta_ad_account_id text;

UPDATE public.ad_creatives
SET is_click_to_whatsapp = true
WHERE cta_type = 'WHATSAPP_MESSAGE';

CREATE INDEX IF NOT EXISTS idx_ad_campaigns_account
  ON public.ad_campaigns (tenant_id, meta_ad_account_id);

CREATE INDEX IF NOT EXISTS idx_ad_creatives_account_ctwa
  ON public.ad_creatives (tenant_id, meta_ad_account_id, is_click_to_whatsapp);

CREATE INDEX IF NOT EXISTS idx_ad_insights_daily_account_date
  ON public.ad_insights_daily (tenant_id, meta_ad_account_id, insight_date);
