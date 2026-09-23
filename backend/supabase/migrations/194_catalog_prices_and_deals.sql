-- 194_catalog_prices_and_deals.sql
-- Catalog items get a real price, and a WhatsApp conversation that quotes one
-- gets a visible record of it -- without any manual data entry (see
-- .agents/projects/active-backlog.md, "Catalog-priced deals on the intake
-- Pipeline board", 2026-09-22).
--
-- Deliberately minimal, per that backlog note:
--   - No stage machine, no "Won" tracking: catalog items have no payment-link
--     plumbing today (that only exists for the intake package flow), so a
--     deal here can only ever mean "the AI quoted a real price" -- it never
--     progresses further on its own. Building automatic Won tracking on top
--     would need a second feature (payment collection for catalog items)
--     that hasn't been decided.
--   - No manual entry: this stays WhatsApp-only, matching the same scope
--     decision that shaped the intake Pipeline board.
--   - One open deal per lead: repeat quotes on the same lead update the same
--     row (latest item + amount win) rather than piling up duplicates.

ALTER TABLE catalog_items
  ADD COLUMN IF NOT EXISTS price_paise bigint,
  ADD COLUMN IF NOT EXISTS price_note text;

ALTER TABLE catalog_items
  DROP CONSTRAINT IF EXISTS catalog_items_price_paise_check;
ALTER TABLE catalog_items
  ADD CONSTRAINT catalog_items_price_paise_check CHECK (price_paise IS NULL OR price_paise >= 0);

-- match_catalog_items (140_catalog_disambiguation.sql) is the smart-retrieval
-- path the AI uses once a catalog is fully embedded; it must carry price
-- through too, or the vast majority of recommendations (anything that isn't
-- the zero-embedding fallback listing) would silently have no price at all.
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
    similarity       float
)
language sql
stable
as $$
    select
        ci.id, ci.name, ci.item_type, ci.description, ci.attributes, ci.variant_group_id,
        ci.price_paise, ci.price_note,
        1 - (ci.embedding <=> query_embedding::vector(512)) as similarity
    from catalog_items ci
    where ci.tenant_id = p_tenant_id
      and ci.status = 'ready'
      and ci.embedding is not null
    order by ci.embedding <=> query_embedding::vector(512)
    limit match_count;
$$;

CREATE TABLE IF NOT EXISTS catalog_quotes (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  lead_id uuid NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
  catalog_item_id uuid REFERENCES catalog_items(id) ON DELETE SET NULL,
  item_name text NOT NULL,
  amount_paise bigint NOT NULL CHECK (amount_paise >= 0),
  amount_is_estimate boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_catalog_quotes_open_per_lead ON catalog_quotes (lead_id);
CREATE INDEX IF NOT EXISTS idx_catalog_quotes_tenant ON catalog_quotes (tenant_id, created_at DESC);

DROP TRIGGER IF EXISTS catalog_quotes_updated_at ON catalog_quotes;
CREATE TRIGGER catalog_quotes_updated_at
  BEFORE UPDATE ON catalog_quotes
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- RLS: same posture as 190_knowledge_auto_sort's new tables -- members read,
-- only the backend (service role) writes. No owner-write policy: lead_id and
-- catalog_item_id foreign keys don't check tenancy, so a directly-inserted
-- row could point at another tenant's lead.
ALTER TABLE catalog_quotes ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS catalog_quotes_tenant_member_select ON catalog_quotes;
CREATE POLICY catalog_quotes_tenant_member_select ON catalog_quotes
  FOR SELECT TO authenticated USING (public.is_tenant_member(tenant_id));
