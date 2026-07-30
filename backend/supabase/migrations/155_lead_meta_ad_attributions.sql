-- Count one WhatsApp lead once per Meta ad while allowing the same lead to
-- belong to a different ad later. Meta's referral ad id is primary; the
-- per-ad pre-filled message code is a fallback handled by the webhook.

CREATE UNIQUE INDEX IF NOT EXISTS idx_ad_creatives_tracking_code
  ON public.ad_creatives (tenant_id, prefilled_message_code)
  WHERE prefilled_message_code IS NOT NULL;

CREATE TABLE IF NOT EXISTS public.lead_meta_ad_attributions (
  tenant_id uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
  lead_id uuid NOT NULL REFERENCES public.leads(id) ON DELETE CASCADE,
  meta_ad_account_id text NOT NULL,
  meta_ad_id text NOT NULL,
  ad_creative_id uuid REFERENCES public.ad_creatives(id) ON DELETE SET NULL,
  attribution_method text NOT NULL,
  first_seen_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, lead_id, meta_ad_id),
  CONSTRAINT lead_meta_ad_attributions_method_check
    CHECK (attribution_method IN ('meta_ad_id', 'prefilled_code')),
  CONSTRAINT lead_meta_ad_attributions_seen_check
    CHECK (last_seen_at >= first_seen_at)
);

CREATE INDEX IF NOT EXISTS idx_lead_meta_ad_attributions_ad_period
  ON public.lead_meta_ad_attributions
    (tenant_id, meta_ad_account_id, meta_ad_id, first_seen_at);

CREATE INDEX IF NOT EXISTS idx_lead_meta_ad_attributions_creative
  ON public.lead_meta_ad_attributions (ad_creative_id)
  WHERE ad_creative_id IS NOT NULL;

-- Preserve existing first-touch creative attribution in the new relationship
-- table so the report does not lose previously confirmed leads.
INSERT INTO public.lead_meta_ad_attributions (
  tenant_id,
  lead_id,
  meta_ad_account_id,
  meta_ad_id,
  ad_creative_id,
  attribution_method,
  first_seen_at,
  last_seen_at
)
SELECT
  l.tenant_id,
  l.id,
  c.meta_ad_account_id,
  c.meta_ad_id,
  c.id,
  'meta_ad_id',
  l.created_at,
  l.created_at
FROM public.leads l
JOIN public.ad_creatives c
  ON c.id = l.attributed_ad_creative_id
 AND c.tenant_id = l.tenant_id
WHERE c.meta_ad_account_id IS NOT NULL
  AND c.meta_ad_id IS NOT NULL
ON CONFLICT (tenant_id, lead_id, meta_ad_id) DO NOTHING;

ALTER TABLE public.lead_meta_ad_attributions ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'lead_meta_ad_attributions'
      AND policyname = 'lead_meta_ad_attributions_tenant_read'
  ) THEN
    CREATE POLICY lead_meta_ad_attributions_tenant_read
      ON public.lead_meta_ad_attributions
      FOR SELECT TO authenticated
      USING (public.is_tenant_member(tenant_id));
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'lead_meta_ad_attributions'
      AND policyname = 'lead_meta_ad_attributions_admin_all'
  ) THEN
    CREATE POLICY lead_meta_ad_attributions_admin_all
      ON public.lead_meta_ad_attributions
      FOR ALL TO authenticated
      USING (public.is_system_admin())
      WITH CHECK (public.is_system_admin());
  END IF;
END $$;

GRANT SELECT ON public.lead_meta_ad_attributions TO authenticated;
GRANT ALL ON public.lead_meta_ad_attributions TO service_role;
