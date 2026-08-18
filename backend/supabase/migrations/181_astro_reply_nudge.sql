-- 181_astro_reply_nudge.sql
-- The astrologer's answer is no longer delivered over WhatsApp: the customer is
-- nudged into the AstroTamil app and reads it there. Two consequences.
--
-- 1. astro_followup_count goes. Follow-up questions now happen inside the app,
--    so nothing calls push_followup any more. Added yesterday (migration 180),
--    never used in anger — verified zero rows with a non-default value before
--    dropping.
--
-- 2. astro_last_reply_text arrives. Aira stops sending the answer but still
--    keeps it, so support can see what the astrologer actually wrote when a
--    customer says they cannot find it in the app. Deliberately NOT written to
--    `messages`: that table is what the customer received, and the answer is
--    precisely what they did not receive.

ALTER TABLE intake_sessions DROP COLUMN IF EXISTS astro_followup_count;

ALTER TABLE intake_sessions ADD COLUMN IF NOT EXISTS astro_last_reply_text text;
