-- 194_catalog_prices_and_deals.sql
-- Catalog items get a real price, so Aira can quote it in WhatsApp replies.
--
-- Rewritten 2026-09-25 before it was ever applied to production: the original
-- also created a catalog_quotes table (one "deal" row per lead, upserted on
-- lead_id). That design overwrote a repeat buyer's earlier sale and is
-- replaced by the deals / deal_items / stock_movements model in 204_deals.sql.
-- The match_catalog_items redefinition that used to live here moved to 195,
-- which needs the price columns below to exist first.

ALTER TABLE catalog_items
  ADD COLUMN IF NOT EXISTS price_paise bigint,
  ADD COLUMN IF NOT EXISTS price_note text;

ALTER TABLE catalog_items
  DROP CONSTRAINT IF EXISTS catalog_items_price_paise_check;
ALTER TABLE catalog_items
  ADD CONSTRAINT catalog_items_price_paise_check CHECK (price_paise IS NULL OR price_paise >= 0);
