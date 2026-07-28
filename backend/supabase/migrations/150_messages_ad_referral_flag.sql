-- Flag inbound messages that arrived via a Meta click-to-WhatsApp ad referral
-- (Meta's own pre-filled CTA text, sent by tapping the ad -- not composed by the lead).
-- Lets scoring_engine.py tell the arc-scoring LLM which lines are ad boilerplate
-- vs the lead's own words, so a pre-filled opener isn't scored as composed intent.
ALTER TABLE messages ADD COLUMN IF NOT EXISTS via_ad_referral boolean NOT NULL DEFAULT false;
