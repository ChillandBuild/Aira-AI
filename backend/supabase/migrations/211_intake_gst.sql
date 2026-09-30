-- 211_intake_gst.sql
-- Tenant-wide "GST % added on top" for Services-page packages (app_settings intake_config.gst_percent).
-- At payment-link creation the session records the GST split: amount_paise stays the amount
-- charged (GST included), gst_percent the rate applied, gst_amount_paise the GST part.
-- total_amount_paise stays the pre-GST subtotal (package + add-ons).
-- NULL = no GST recorded (every session made before this column existed). No backfill.
-- Apply BEFORE the new code deploys (the code writes these columns).

ALTER TABLE intake_sessions
  ADD COLUMN IF NOT EXISTS gst_percent numeric,
  ADD COLUMN IF NOT EXISTS gst_amount_paise integer;

NOTIFY pgrst, 'reload schema';
