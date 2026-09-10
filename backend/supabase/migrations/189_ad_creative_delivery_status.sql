-- 189_ad_creative_delivery_status.sql
-- The Meta Ads "Delivery" column used to show the *campaign's* effective_status
-- (ad_performance.py) with the *ad set's* status as fallback (ad_creatives.
-- effective_status is written from adset_meta). The ad's own status was never
-- fetched, so an ad deleted in Ads Manager kept rendering as Active forever:
-- Meta stops returning deleted objects, the sync only ever UPDATEs what it
-- sees, and nothing reconciled the rows that disappeared.
--
-- ad_effective_status  -- the ad's own effective_status from the /ads edge.
-- last_seen_at         -- stamped every sync Meta still returns this ad; the
--                         reconciler marks anything older than the current
--                         run's cutoff as DELETED.
--
-- NULL on all existing rows: ad_effective_status falls back to the old
-- campaign/ad-set behaviour until the next sync fills it in, so no backfill.

ALTER TABLE ad_creatives
  ADD COLUMN IF NOT EXISTS ad_effective_status text,
  ADD COLUMN IF NOT EXISTS last_seen_at timestamptz;

CREATE INDEX IF NOT EXISTS idx_ad_creatives_account_last_seen
  ON ad_creatives (tenant_id, meta_ad_account_id, last_seen_at);
