-- 196_manual_deal_entry.sql
-- A sale with no WhatsApp trail (a phone call, a walk-in, cash) is invisible
-- to everything built so far -- catalog_quotes only ever gets a row from the
-- AI quoting a price in chat. This adds the human-entered path, reusing the
-- same table rather than adding a new one: same shape (one row per lead,
-- tenant-scoped, RLS already in place).
--
-- amount_is_estimate defaults differently by source: an AI catalog quote is
-- genuinely a guess about purchase intent (existing default true); a manual
-- entry is a human typing a real number, so false is correct there --
-- callers must set it explicitly rather than relying on the column default.

ALTER TABLE catalog_quotes
  ADD COLUMN IF NOT EXISTS source text NOT NULL DEFAULT 'ai_catalog',
  ADD COLUMN IF NOT EXISTS created_by uuid;

ALTER TABLE catalog_quotes DROP CONSTRAINT IF EXISTS catalog_quotes_source_check;
ALTER TABLE catalog_quotes ADD CONSTRAINT catalog_quotes_source_check
  CHECK (source IN ('ai_catalog', 'manual'));
