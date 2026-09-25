-- 204_deals.sql
-- One deal model for every client (see docs/superpowers/specs/2026-09-25-deals-crm-design.md).
--
-- A deal is one sale attempt: quoted -> awaiting_payment -> won | lost. Won is
-- the final stage (no "delivered" step). Every way a sale can start writes
-- here: the AI in WhatsApp, the intake/consultation form, a telecaller after a
-- call, a walk-in, manual entry, and later IndiaMART/JustDial enquiries.
--
-- Replaces the never-applied catalog_quotes (194/196) and quotes (197) tables:
-- those kept one row per lead, so a repeat buyer's second sale overwrote the
-- first -- wrong for sales history and for the monthly auditor export.
--
-- Prices and GST rates are SNAPSHOTS on deal_items, taken when the line is
-- written. A later catalog price edit must never rewrite what a customer was
-- quoted or paid, or what the auditor export already showed.
--
-- Stock only changes through apply_stock_movement(), which updates the count
-- and writes a stock_movements row in one statement.

-- ---------------------------------------------------------------- catalog GST
ALTER TABLE catalog_items
  ADD COLUMN IF NOT EXISTS gst_rate numeric(5,2);
ALTER TABLE catalog_items DROP CONSTRAINT IF EXISTS catalog_items_gst_rate_check;
ALTER TABLE catalog_items ADD CONSTRAINT catalog_items_gst_rate_check
  CHECK (gst_rate IS NULL OR (gst_rate >= 0 AND gst_rate <= 40));

-- ---------------------------------------------------------------- deals
CREATE TABLE IF NOT EXISTS deals (
  id                       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  lead_id                  uuid NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
  deal_number              integer NOT NULL,
  stage                    text NOT NULL DEFAULT 'quoted'
                             CHECK (stage IN ('quoted', 'awaiting_payment', 'won', 'lost')),
  source                   text NOT NULL
                             CHECK (source IN ('whatsapp', 'form', 'call', 'walk_in', 'manual', 'indiamart', 'justdial')),
  total_paise              bigint NOT NULL DEFAULT 0 CHECK (total_paise >= 0),
  payment_method           text
                             CHECK (payment_method IS NULL OR payment_method IN ('razorpay', 'cash', 'upi', 'card', 'bank_transfer', 'other')),
  payment_link             text,
  razorpay_payment_link_id text,
  razorpay_payment_id      text,
  link_expires_at          timestamptz,
  lost_reason              text,
  notes                    text,
  intake_session_id        uuid REFERENCES intake_sessions(id) ON DELETE SET NULL,
  created_by               uuid,
  created_at               timestamptz NOT NULL DEFAULT now(),
  updated_at               timestamptz NOT NULL DEFAULT now(),
  won_at                   timestamptz,
  lost_at                  timestamptz,
  UNIQUE (tenant_id, deal_number)
);

CREATE INDEX IF NOT EXISTS idx_deals_tenant_stage_created ON deals (tenant_id, stage, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_deals_tenant_lead ON deals (tenant_id, lead_id);
-- Monthly auditor export and revenue stats read won deals by won_at.
CREATE INDEX IF NOT EXISTS idx_deals_tenant_won_at ON deals (tenant_id, won_at) WHERE stage = 'won';
-- One deal per intake session: the form flow re-uses its deal on package change.
CREATE UNIQUE INDEX IF NOT EXISTS uq_deals_intake_session ON deals (intake_session_id) WHERE intake_session_id IS NOT NULL;

DROP TRIGGER IF EXISTS deals_updated_at ON deals;
CREATE TRIGGER deals_updated_at BEFORE UPDATE ON deals
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ---------------------------------------------------------------- deal_items
CREATE TABLE IF NOT EXISTS deal_items (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  deal_id           uuid NOT NULL REFERENCES deals(id) ON DELETE CASCADE,
  tenant_id         uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  catalog_item_id   uuid REFERENCES catalog_items(id) ON DELETE SET NULL,
  name              text NOT NULL,
  qty               integer NOT NULL DEFAULT 1 CHECK (qty > 0),
  unit_price_paise  bigint NOT NULL CHECK (unit_price_paise >= 0),
  gst_rate          numeric(5,2) CHECK (gst_rate IS NULL OR (gst_rate >= 0 AND gst_rate <= 40)),
  line_total_paise  bigint NOT NULL CHECK (line_total_paise >= 0),
  created_at        timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_deal_items_deal ON deal_items (deal_id);
CREATE INDEX IF NOT EXISTS idx_deal_items_tenant_item ON deal_items (tenant_id, catalog_item_id);

-- ---------------------------------------------------------------- stock_movements
CREATE TABLE IF NOT EXISTS stock_movements (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  catalog_item_id  uuid NOT NULL REFERENCES catalog_items(id) ON DELETE CASCADE,
  delta            integer NOT NULL CHECK (delta <> 0),
  quantity_after   integer NOT NULL,
  reason           text NOT NULL CHECK (reason IN ('sale', 'restock', 'adjustment', 'return')),
  deal_id          uuid REFERENCES deals(id) ON DELETE SET NULL,
  note             text,
  created_by       uuid,
  created_at       timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_stock_movements_item ON stock_movements (tenant_id, catalog_item_id, created_at DESC);

-- ---------------------------------------------------------------- deal numbering
-- Human-facing D-0001 numbers, per tenant, gap-free under concurrency: the
-- upsert's row lock serialises two simultaneous deals for the same tenant.
CREATE TABLE IF NOT EXISTS deal_counters (
  tenant_id    uuid PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
  last_number  integer NOT NULL DEFAULT 0
);

CREATE OR REPLACE FUNCTION next_deal_number(p_tenant_id uuid)
RETURNS integer
LANGUAGE sql
SET search_path = public, pg_temp
AS $$
  INSERT INTO deal_counters (tenant_id, last_number) VALUES (p_tenant_id, 1)
  ON CONFLICT (tenant_id) DO UPDATE SET last_number = deal_counters.last_number + 1
  RETURNING last_number;
$$;

-- ---------------------------------------------------------------- stock movement
-- Applies a signed change to an item's stock and logs it, atomically.
-- Returns one row: ok=false when the item is missing, belongs to another
-- tenant, or the change would take stock below zero (the WHERE clause is the
-- race guard: of two simultaneous sales of the last unit, one matches zero
-- rows). tracked=false when the item has no stock count (NULL = not tracked,
-- e.g. a service) -- nothing is changed or logged, and ok stays true because
-- an untracked item can always be sold.
CREATE OR REPLACE FUNCTION apply_stock_movement(
  p_tenant_id  uuid,
  p_item_id    uuid,
  p_delta      integer,
  p_reason     text,
  p_deal_id    uuid DEFAULT NULL,
  p_note       text DEFAULT NULL,
  p_created_by uuid DEFAULT NULL
) RETURNS TABLE (ok boolean, tracked boolean, quantity_after integer)
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
DECLARE
  v_current integer;
  v_exists  boolean;
  v_after   integer;
BEGIN
  SELECT true, ci.stock_quantity INTO v_exists, v_current
  FROM catalog_items ci
  WHERE ci.id = p_item_id AND ci.tenant_id = p_tenant_id;

  IF NOT FOUND THEN
    RETURN QUERY SELECT false, false, NULL::integer;
    RETURN;
  END IF;

  IF v_current IS NULL THEN
    RETURN QUERY SELECT true, false, NULL::integer;
    RETURN;
  END IF;

  UPDATE catalog_items
  SET stock_quantity = stock_quantity + p_delta
  WHERE id = p_item_id
    AND tenant_id = p_tenant_id
    AND stock_quantity IS NOT NULL
    AND stock_quantity + p_delta >= 0
  RETURNING stock_quantity INTO v_after;

  IF v_after IS NULL THEN
    RETURN QUERY SELECT false, true, v_current;
    RETURN;
  END IF;

  INSERT INTO stock_movements (tenant_id, catalog_item_id, delta, quantity_after, reason, deal_id, note, created_by)
  VALUES (p_tenant_id, p_item_id, p_delta, v_after, p_reason, p_deal_id, p_note, p_created_by);

  RETURN QUERY SELECT true, true, v_after;
END;
$$;

-- Backend (service role) only: both functions take a tenant id as an argument,
-- so letting a signed-in user call them directly would let them write into
-- another tenant. Invariant 6: no anon EXECUTE.
REVOKE EXECUTE ON FUNCTION next_deal_number(uuid) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION apply_stock_movement(uuid, uuid, integer, text, uuid, text, uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION next_deal_number(uuid) TO service_role;
GRANT EXECUTE ON FUNCTION apply_stock_movement(uuid, uuid, integer, text, uuid, text, uuid) TO service_role;

-- ---------------------------------------------------------------- RLS
-- Members read their own tenant's rows; only the backend (service role) writes.
-- No member write policies: lead_id / catalog_item_id don't check tenancy on
-- their own, so a directly-inserted row could point at another tenant's data.
ALTER TABLE deals ENABLE ROW LEVEL SECURITY;
ALTER TABLE deal_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE stock_movements ENABLE ROW LEVEL SECURITY;
ALTER TABLE deal_counters ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS deals_tenant_member_select ON deals;
CREATE POLICY deals_tenant_member_select ON deals
  FOR SELECT TO authenticated USING (is_tenant_member(tenant_id));

DROP POLICY IF EXISTS deal_items_tenant_member_select ON deal_items;
CREATE POLICY deal_items_tenant_member_select ON deal_items
  FOR SELECT TO authenticated USING (is_tenant_member(tenant_id));

DROP POLICY IF EXISTS stock_movements_tenant_member_select ON stock_movements;
CREATE POLICY stock_movements_tenant_member_select ON stock_movements
  FOR SELECT TO authenticated USING (is_tenant_member(tenant_id));
-- deal_counters: no policy at all -> no access except service role.
