-- 149: Meta Ads Create + Management (Plan 2). Adds an ad_sets table (Aira must
-- persist what it wrote to Meta at ad-set level) plus create-provenance columns
-- on ad_campaigns/ad_creatives. Columns are additive; existing admin-all +
-- tenant-read RLS on ad_campaigns/ad_creatives already covers the new columns.

CREATE TABLE public.ad_sets (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
  campaign_id uuid REFERENCES public.ad_campaigns(id) ON DELETE CASCADE,
  meta_adset_id text,
  adset_name text,
  targeting jsonb NOT NULL DEFAULT '{}'::jsonb,
  optimization_goal text,
  effective_status text,
  created_via text NOT NULL DEFAULT 'imported',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, meta_adset_id)
);

CREATE INDEX idx_ad_sets_tenant ON public.ad_sets (tenant_id);
CREATE INDEX idx_ad_sets_campaign ON public.ad_sets (campaign_id);

ALTER TABLE public.ad_campaigns
  ADD COLUMN IF NOT EXISTS special_ad_category text,
  ADD COLUMN IF NOT EXISTS created_via text NOT NULL DEFAULT 'imported',
  ADD COLUMN IF NOT EXISTS page_id text;

ALTER TABLE public.ad_creatives
  ADD COLUMN IF NOT EXISTS created_by_aira boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS prefilled_greeting text,
  ADD COLUMN IF NOT EXISTS media_asset_ref text,
  ADD COLUMN IF NOT EXISTS cta_type text;

-- RLS for the new table: admin-all + tenant-read (mirrors ad_creatives, migration 147)
ALTER TABLE public.ad_sets ENABLE ROW LEVEL SECURITY;
CREATE POLICY ad_sets_admin_all ON public.ad_sets
  USING (EXISTS (SELECT 1 FROM system_admins WHERE system_admins.user_id = auth.uid()));
CREATE POLICY ad_sets_tenant_read ON public.ad_sets
  FOR SELECT
  USING (EXISTS (SELECT 1 FROM tenant_users tu
                 WHERE tu.tenant_id = ad_sets.tenant_id AND tu.user_id = auth.uid()));
