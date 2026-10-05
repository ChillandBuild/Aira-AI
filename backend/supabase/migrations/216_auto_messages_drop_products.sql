-- 216_auto_messages_drop_products.sql
-- Auto-Messages no longer match products: one message per event, sent to
-- everyone. Drops the per-product rule column, the product fields on the send
-- log and catalog_items.aliases (only Auto-Messages used it).
-- Apply AFTER the backend that stops reading these columns is deployed.
-- Live state when written (2026-10-05): 0 rules, 0 aliases, so nothing is lost.

SET LOCAL lock_timeout = '5s';

DROP INDEX IF EXISTS auto_message_rules_one_per_product;
-- Keep the oldest rule per event if any product rules slipped in before this ran.
DELETE FROM auto_message_rules r
 USING auto_message_rules keep
 WHERE r.tenant_id = keep.tenant_id AND r.event = keep.event
   AND (keep.created_at, keep.id) < (r.created_at, r.id);
ALTER TABLE auto_message_rules DROP COLUMN IF EXISTS catalog_item_id;
CREATE UNIQUE INDEX IF NOT EXISTS auto_message_rules_one_per_event
  ON auto_message_rules (tenant_id, event);

ALTER TABLE auto_message_sends DROP COLUMN IF EXISTS product_raw;
ALTER TABLE auto_message_sends DROP COLUMN IF EXISTS catalog_item_id;

ALTER TABLE catalog_items DROP COLUMN IF EXISTS aliases;

-- "Page they came from" was stored as a product_url variable source; it is page_url now.
UPDATE auto_message_rules
   SET variables = REPLACE(variables::text, '"product_url"', '"page_url"')::jsonb,
       button_param = REPLACE(button_param::text, '"product_url"', '"page_url"')::jsonb
 WHERE variables::text LIKE '%product_url%' OR button_param::text LIKE '%product_url%';
