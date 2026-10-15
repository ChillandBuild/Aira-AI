-- Meta Ads: which ads a tenant tracks, decided when they connect.
--
-- meta_ad_registry holds one row per Meta ad of ANY type (WhatsApp, lead form,
-- website, ...). `eligible` is the join rule: ads running when the tenant
-- connected, plus ads created after, are eligible; once eligible an ad stays
-- eligible even after it is paused or deleted. Written by
-- services/meta_ads_insights_sync.py (service role). The All ads page and the
-- insight sync both read it.
--
-- ad_creatives.tracked_in_anril is the tenant's per-ad switch for the Anril
-- report (attribution keeps recording when it is off).

CREATE TABLE IF NOT EXISTS public.meta_ad_registry (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
  meta_ad_account_id text NOT NULL,
  meta_ad_id text NOT NULL,
  meta_adset_id text,
  meta_campaign_id text,
  destination_type text,
  ad_created_time timestamptz,
  status_at_join text,
  eligible boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, meta_ad_id)
);

CREATE INDEX IF NOT EXISTS idx_meta_ad_registry_account
  ON public.meta_ad_registry (tenant_id, meta_ad_account_id, eligible);

ALTER TABLE public.meta_ad_registry ENABLE ROW LEVEL SECURITY;
CREATE POLICY meta_ad_registry_admin_all ON public.meta_ad_registry
  USING (EXISTS (SELECT 1 FROM system_admins WHERE system_admins.user_id = auth.uid()));
CREATE POLICY meta_ad_registry_tenant_read ON public.meta_ad_registry
  FOR SELECT
  USING (EXISTS (SELECT 1 FROM tenant_users tu
                 WHERE tu.tenant_id = meta_ad_registry.tenant_id AND tu.user_id = auth.uid()));

ALTER TABLE public.ad_creatives
  ADD COLUMN IF NOT EXISTS destination_type text,
  ADD COLUMN IF NOT EXISTS tracked_in_anril boolean NOT NULL DEFAULT true;

-- Every creative synced before this migration came from a WHATSAPP-only ad set.
UPDATE public.ad_creatives
SET destination_type = 'WHATSAPP'
WHERE is_click_to_whatsapp AND destination_type IS NULL;

-- Existing tenants keep every ad they already see: seed the registry with their
-- current creatives as eligible. Their first sync after this then snapshots the
-- ads running now (meta_ads_join_snapshot_account is unset for them).
INSERT INTO public.meta_ad_registry
  (tenant_id, meta_ad_account_id, meta_ad_id, meta_adset_id, meta_campaign_id,
   destination_type, eligible)
SELECT tenant_id, meta_ad_account_id, meta_ad_id, meta_adset_id, meta_campaign_id,
       destination_type, true
FROM public.ad_creatives
WHERE meta_ad_account_id IS NOT NULL AND meta_ad_id IS NOT NULL
ON CONFLICT (tenant_id, meta_ad_id) DO NOTHING;

-- "Connected at" for tenants that connected before this existed: now.
INSERT INTO public.app_settings (tenant_id, key, value, is_secret, updated_at)
SELECT tenant_id, 'meta_ads_connected_at', to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"+00:00"'), false, now()
FROM public.app_settings
WHERE key = 'meta_ads_account_id' AND coalesce(value, '') <> ''
ON CONFLICT (tenant_id, key) DO NOTHING;
