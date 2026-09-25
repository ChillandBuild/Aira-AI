-- 195_catalog_stock.sql
-- Inventory count per catalog item, for physical products only. NULL means
-- "not tracked" -- a service or course (item_type != 'product') has no stock
-- concept and stays NULL forever; the AI treats NULL as "always available".
--
-- Stock only ever changes through apply_stock_movement() (204_deals.sql), which
-- writes a stock_movements row in the same statement, so every change to this
-- number has a reason attached. A sale deducts on a WON deal only -- never when
-- the AI merely quotes a price in chat.

ALTER TABLE catalog_items
  ADD COLUMN IF NOT EXISTS stock_quantity integer;

ALTER TABLE catalog_items
  DROP CONSTRAINT IF EXISTS catalog_items_stock_quantity_check;
ALTER TABLE catalog_items
  ADD CONSTRAINT catalog_items_stock_quantity_check CHECK (stock_quantity IS NULL OR stock_quantity >= 0);

-- match_catalog_items (140) is the path most AI recommendations take once a
-- catalog is embedded, so it must carry price and stock too. Postgres refuses
-- CREATE OR REPLACE when the returned columns change, hence DROP first. The
-- search_path pin from 174_advisor_hardening.sql is restored explicitly --
-- dropping the function discards it.
DROP FUNCTION IF EXISTS match_catalog_items(text, uuid, integer);

CREATE FUNCTION match_catalog_items(
    query_embedding text,
    p_tenant_id     uuid,
    match_count     int default 5
) RETURNS TABLE (
    id               uuid,
    name             text,
    item_type        text,
    description      text,
    attributes       jsonb,
    variant_group_id uuid,
    price_paise      bigint,
    price_note       text,
    stock_quantity   integer,
    similarity       float
)
LANGUAGE sql
STABLE
SET search_path = public, pg_temp
AS $$
    select
        ci.id, ci.name, ci.item_type, ci.description, ci.attributes, ci.variant_group_id,
        ci.price_paise, ci.price_note, ci.stock_quantity,
        1 - (ci.embedding <=> query_embedding::vector(512)) as similarity
    from catalog_items ci
    where ci.tenant_id = p_tenant_id
      and ci.status = 'ready'
      and ci.embedding is not null
    order by ci.embedding <=> query_embedding::vector(512)
    limit match_count;
$$;
