-- Number health comes from Meta only (2026-10-16).
--
-- meta_status / meta_code_verification mirror Meta's phone-number `status`
-- (CONNECTED, PENDING, ...) and `code_verification_status` (VERIFIED,
-- NOT_VERIFIED, EXPIRED). A number is only allowed to send or take over as
-- primary when Meta says CONNECTED.
--
-- warm_up_started_at: the 14-day warm-up counts from the first sync that saw
-- the number CONNECTED, not from when it was added. Existing rows keep the
-- day they had reached.
--
-- rested_since: set when a number turns Red. It stops broadcasting, keeps
-- answering chats, and recovers after 7 days once Meta reports it Green.
--
-- quality_rating / messaging_tier lose their invented defaults ('green',
-- 1000): NULL now means Meta has not reported one yet.
--
-- leads.last_inbound_phone_number_id: which of the tenant's numbers the lead
-- last messaged, so astrologer replies land in the lead's existing thread
-- after a failover.
--
-- Additive and compatible with the backend before this change. Apply BEFORE
-- deploying the backend that reads these columns.

ALTER TABLE phone_numbers
  ADD COLUMN IF NOT EXISTS meta_status text,
  ADD COLUMN IF NOT EXISTS meta_code_verification text,
  ADD COLUMN IF NOT EXISTS warm_up_started_at timestamptz,
  ADD COLUMN IF NOT EXISTS rested_since timestamptz;

ALTER TABLE phone_numbers
  ALTER COLUMN quality_rating DROP NOT NULL,
  ALTER COLUMN quality_rating DROP DEFAULT,
  ALTER COLUMN messaging_tier DROP NOT NULL,
  ALTER COLUMN messaging_tier DROP DEFAULT;

UPDATE phone_numbers
  SET warm_up_started_at = now() - make_interval(days => warm_up_day)
  WHERE warm_up_day > 0 AND warm_up_started_at IS NULL;

ALTER TABLE leads
  ADD COLUMN IF NOT EXISTS last_inbound_phone_number_id text;

ALTER TABLE incidents
  DROP CONSTRAINT IF EXISTS incidents_type_check;

ALTER TABLE incidents
  ADD CONSTRAINT incidents_type_check CHECK (type IN (
    'quality_yellow', 'quality_red', 'failover', 'migration_sent', 'appeal_filed',
    'standby_promoted', 'warm_up_complete', 'token_invalid', 'webhook_unhealthy',
    'number_recovered'
  ));
