-- When the campaign was created in Meta Ads Manager (Meta's created_time), filled by the
-- campaign sync. The Segments campaign list shows its month to tell same-named campaigns apart.
ALTER TABLE public.ad_campaigns ADD COLUMN IF NOT EXISTS meta_created_at timestamptz;
