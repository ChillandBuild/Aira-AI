-- Remove the old midnight send counter (2026-10-17).
--
-- Replaced by template_send_log + messaging_limit_usage (migration 230), which
-- count what Meta counts: unique people outside their 24h window, moving 24h.
-- Nothing in the backend or frontend reads or writes these any more.
--
-- APPLY ONLY AFTER the backend that stopped using them is deployed -- the
-- previous backend increments daily_send_count on every broadcast send and
-- would fail without these.

DROP FUNCTION IF EXISTS public.increment_phone_daily_send_count(uuid);
DROP FUNCTION IF EXISTS public.increment_phone_daily_send_count(uuid, integer);

ALTER TABLE phone_numbers
  DROP COLUMN IF EXISTS daily_send_count,
  DROP COLUMN IF EXISTS last_reset_at;
