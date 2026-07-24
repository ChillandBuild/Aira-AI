-- 148: Widen ad reporting for the Meta Ads dashboard (Plan 1, read-only).
-- Adds full-funnel Meta metrics to daily insights (impressions/reach/actions)
-- and campaign-level status/objective/budget to ad_campaigns, populated by the
-- widened services/meta_ads_insights_sync.py. Columns only — no new RLS needed
-- (existing admin-all + tenant-read policies on both tables already apply).

ALTER TABLE public.ad_insights_daily
  ADD COLUMN IF NOT EXISTS impressions bigint NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS reach bigint NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS actions jsonb NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE public.ad_campaigns
  ADD COLUMN IF NOT EXISTS objective text,
  ADD COLUMN IF NOT EXISTS effective_status text,
  ADD COLUMN IF NOT EXISTS daily_budget numeric(14,2),
  ADD COLUMN IF NOT EXISTS lifetime_budget numeric(14,2),
  ADD COLUMN IF NOT EXISTS bid_strategy text;
