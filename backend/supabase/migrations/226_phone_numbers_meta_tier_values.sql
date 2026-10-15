-- Meta's real messaging limits (portfolio-level since Oct 2025): 250, 2,000,
-- 10,000, 100,000 and Unlimited (stored as 1000000), plus the deprecated
-- per-number 50 / 1,000. The old check (250, 1000, 10000, 100000) rejected
-- 2,000 and Unlimited, so syncs could never record the real limit.
-- Apply BEFORE deploying the backend that writes these values.
ALTER TABLE phone_numbers
  DROP CONSTRAINT IF EXISTS phone_numbers_messaging_tier_check;

ALTER TABLE phone_numbers
  ADD CONSTRAINT phone_numbers_messaging_tier_check
    CHECK (messaging_tier IN (50, 250, 1000, 2000, 10000, 100000, 1000000));
