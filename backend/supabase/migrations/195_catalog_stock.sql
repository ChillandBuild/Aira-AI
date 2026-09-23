-- 195_catalog_stock.sql
-- Inventory count per catalog item, for physical products only. NULL means
-- "not tracked" -- a service or course (item_type != 'product') has no stock
-- concept and stays NULL forever; the AI treats NULL as "always available".
--
-- Deducting stock happens on a CONFIRMED sale only (a paid quote, or a human
-- logging a manual sale) -- never when the AI merely quotes a price in chat.
-- A customer asking "how much is this" is not a sale, and decrementing stock
-- on every quote would drain inventory counts for pure browsing interest.
-- See decrement_catalog_stock() below for the race-safe deduction path.

ALTER TABLE catalog_items
  ADD COLUMN IF NOT EXISTS stock_quantity integer;

ALTER TABLE catalog_items
  DROP CONSTRAINT IF EXISTS catalog_items_stock_quantity_check;
ALTER TABLE catalog_items
  ADD CONSTRAINT catalog_items_stock_quantity_check CHECK (stock_quantity IS NULL OR stock_quantity >= 0);

-- match_catalog_items must carry stock through too, same lesson as
-- price_paise in 194: this is the path most recommendations actually take
-- once a catalog is embedded, not the zero-embedding fallback listing.
create or replace function match_catalog_items(
    query_embedding text,
    p_tenant_id     uuid,
    match_count     int default 5
) returns table (
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
language sql
stable
as $$
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

-- Atomic, race-safe decrement: two simultaneous sales of the last unit must
-- not both succeed. The WHERE clause is the guard -- it only matches (and
-- only decrements) when enough stock is actually there, so a losing caller's
-- UPDATE affects zero rows instead of taking stock negative.
create or replace function decrement_catalog_stock(
    p_item_id   uuid,
    p_tenant_id uuid,
    p_qty       integer
) returns integer
language sql
as $$
    update catalog_items
    set stock_quantity = stock_quantity - p_qty
    where id = p_item_id
      and tenant_id = p_tenant_id
      and stock_quantity is not null
      and stock_quantity >= p_qty
    returning stock_quantity;
$$;
