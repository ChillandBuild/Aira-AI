-- Migration 165: exact-match detection for ad-prefilled messages.
--
-- via_ad_referral (migration 150) only tells us a message arrived via a
-- Click-to-WhatsApp ad -- it says nothing about whether the lead sent Meta's
-- pre-filled text untouched or deleted it and typed their own words. Meta lets
-- leads freely edit/erase the pre-fill before sending, so scoring must not
-- treat every via_ad_referral message the same way.
--
-- ad_creatives.prefilled_greeting_text stores the KNOWN original pre-fill text
-- (synced from Meta's object_story_spec.link_data.page_welcome_message for
-- Meta-native ads, or the tenant's own greeting for Aira's tracking-code flow).
-- messages.attributed_ad_creative_id ties a specific inbound message to the
-- creative it came from, so scoring can compare "what was sent" against
-- "what was supposed to be there" for that exact ad -- not whatever ad the
-- lead is currently (possibly stale-)attributed to at the lead level.
ALTER TABLE ad_creatives ADD COLUMN IF NOT EXISTS prefilled_greeting_text text;

ALTER TABLE messages ADD COLUMN IF NOT EXISTS attributed_ad_creative_id uuid
  REFERENCES ad_creatives(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_messages_attributed_ad_creative
  ON messages (attributed_ad_creative_id)
  WHERE attributed_ad_creative_id IS NOT NULL;
