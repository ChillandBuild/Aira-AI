-- 210_intake_payment_link_expires_at.sql
-- When the session's Razorpay payment link dies (expire_by, 24h after creation).
-- The AI resends a stored link only while this is in the future; NULL = unknown
-- (every link made before this column existed) = treated as expired and regenerated.
-- No backfill. Apply BEFORE the new code deploys (the code writes this column).

ALTER TABLE intake_sessions ADD COLUMN IF NOT EXISTS payment_link_expires_at timestamptz;
