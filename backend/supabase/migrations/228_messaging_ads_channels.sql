-- Messaging ads: credit Instagram and Messenger chats to the Meta ad they came from.
--
-- lead_meta_ad_attributions.channel: the chat app the lead used (whatsapp |
-- instagram | messenger). Every row before this came from the WhatsApp webhook.
--
-- ad_creatives.messaging_channels: which chat apps the ad opens, derived from the
-- ad set's destination_type by services/meta_ads_insights_sync.py. Non-empty means
-- the ad belongs in the Messaging ads report. is_click_to_whatsapp keeps its own
-- meaning ("WhatsApp is one of them"): WhatsApp attribution and tracking codes use it.

ALTER TABLE public.lead_meta_ad_attributions
  ADD COLUMN IF NOT EXISTS channel text NOT NULL DEFAULT 'whatsapp';

ALTER TABLE public.lead_meta_ad_attributions
  DROP CONSTRAINT IF EXISTS lead_meta_ad_attributions_channel_check;
ALTER TABLE public.lead_meta_ad_attributions
  ADD CONSTRAINT lead_meta_ad_attributions_channel_check
  CHECK (channel IN ('whatsapp', 'instagram', 'messenger'));

ALTER TABLE public.ad_creatives
  ADD COLUMN IF NOT EXISTS messaging_channels text[] NOT NULL DEFAULT '{}';

UPDATE public.ad_creatives
SET messaging_channels = array_remove(ARRAY[
  CASE WHEN upper(coalesce(destination_type, '')) LIKE '%WHATSAPP%' THEN 'whatsapp' END,
  CASE WHEN upper(coalesce(destination_type, '')) LIKE '%INSTAGRAM_DIRECT%' THEN 'instagram' END,
  CASE WHEN upper(coalesce(destination_type, '')) LIKE '%MESSENGER%' THEN 'messenger' END
], NULL)
WHERE messaging_channels = '{}';

-- Creatives synced before destination_type existed are WhatsApp-only.
UPDATE public.ad_creatives
SET messaging_channels = ARRAY['whatsapp']
WHERE messaging_channels = '{}' AND is_click_to_whatsapp;

CREATE INDEX IF NOT EXISTS idx_ad_creatives_messaging
  ON public.ad_creatives (tenant_id, meta_ad_account_id)
  WHERE messaging_channels <> '{}';
