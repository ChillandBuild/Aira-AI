-- 176_astro_bridge_session_links.sql
-- Links a paid expert_handoff_sessions row to the records the AstroTamil Django
-- backend creates for it, so the astrologer's reply callback can be matched back
-- to the session (astro_question_id) and a redelivered reply dropped instead of
-- re-sent to WhatsApp (astro_last_reply_id).
--
-- All nullable: only sessions pushed across the bridge ever carry these, and the
-- push is deliberately allowed to fail without blocking the paid transition.
-- RLS is already enabled on this table by migration 168.

ALTER TABLE expert_handoff_sessions ADD COLUMN IF NOT EXISTS astro_question_id   bigint;
ALTER TABLE expert_handoff_sessions ADD COLUMN IF NOT EXISTS astro_horoscope_id  text;
ALTER TABLE expert_handoff_sessions ADD COLUMN IF NOT EXISTS astro_user_id       bigint;
ALTER TABLE expert_handoff_sessions ADD COLUMN IF NOT EXISTS astro_last_reply_id bigint;
