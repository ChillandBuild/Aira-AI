-- 147: Per-creative (per-ad) attribution + daily Meta Ads insights.
-- ad_creatives is auto-imported by services/meta_ads_insights_sync.py from
-- Meta's level=ad Insights response; the WhatsApp webhook stamps
-- leads.attributed_ad_creative_id from the CTWA referral ad_id. All writes are
-- service-role; RLS mirrors the tenant_token_usage pattern (admin-all + tenant-read).

CREATE TABLE public.ad_creatives (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
  campaign_id uuid REFERENCES public.ad_campaigns(id) ON DELETE SET NULL,
  meta_ad_id text NOT NULL,
  meta_adset_id text,
  meta_adset_name text,
  meta_campaign_id text,
  creative_label text NOT NULL,
  label_edited boolean NOT NULL DEFAULT false,
  prefilled_message_code text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, meta_ad_id)
);

CREATE INDEX idx_ad_creatives_tenant ON public.ad_creatives (tenant_id);
CREATE INDEX idx_ad_creatives_campaign ON public.ad_creatives (campaign_id);

CREATE TABLE public.ad_insights_daily (
  tenant_id uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
  ad_creative_id uuid NOT NULL REFERENCES public.ad_creatives(id) ON DELETE CASCADE,
  insight_date date NOT NULL,
  clicks bigint NOT NULL DEFAULT 0,
  inline_link_clicks bigint NOT NULL DEFAULT 0,
  spend numeric(14,2) NOT NULL DEFAULT 0,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, ad_creative_id, insight_date)
);

CREATE INDEX idx_ad_insights_daily_date ON public.ad_insights_daily (tenant_id, insight_date);

ALTER TABLE public.leads
  ADD COLUMN IF NOT EXISTS attributed_ad_creative_id uuid
  REFERENCES public.ad_creatives(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_leads_attributed_creative
  ON public.leads (attributed_ad_creative_id)
  WHERE attributed_ad_creative_id IS NOT NULL;

-- RLS: admin-all + tenant-read (same shape as tenant_token_usage)
ALTER TABLE public.ad_creatives ENABLE ROW LEVEL SECURITY;
CREATE POLICY ad_creatives_admin_all ON public.ad_creatives
  USING (EXISTS (SELECT 1 FROM system_admins WHERE system_admins.user_id = auth.uid()));
CREATE POLICY ad_creatives_tenant_read ON public.ad_creatives
  FOR SELECT
  USING (EXISTS (SELECT 1 FROM tenant_users tu
                 WHERE tu.tenant_id = ad_creatives.tenant_id AND tu.user_id = auth.uid()));

ALTER TABLE public.ad_insights_daily ENABLE ROW LEVEL SECURITY;
CREATE POLICY ad_insights_daily_admin_all ON public.ad_insights_daily
  USING (EXISTS (SELECT 1 FROM system_admins WHERE system_admins.user_id = auth.uid()));
CREATE POLICY ad_insights_daily_tenant_read ON public.ad_insights_daily
  FOR SELECT
  USING (EXISTS (SELECT 1 FROM tenant_users tu
                 WHERE tu.tenant_id = ad_insights_daily.tenant_id AND tu.user_id = auth.uid()));
