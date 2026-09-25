# Deals & Products — mini-CRM design (2026-09-25)

Status: approved in conversation with Prem, 2026-09-25. Database part (migrations 192–195, 204) is LIVE.

## Decisions (from the user — do not re-litigate)
- Generic for ALL tenants. AstroTamil bridge stays a per-tenant add-on, untouched.
- One deal model (option A): `deals` + `deal_items` + `stock_movements` (migration 204). Old `catalog_quotes` / `quotes` never went live and are deleted.
- Stages: `quoted → awaiting_payment → won | lost`. **Won is the last stage** (no Delivered/Resolved column).
- Sources: `whatsapp` (AI chat), `form` (intake/consultation flow), `call`, `walk_in`, `manual`, `indiamart`, `justdial`.
- **Automation choice B**: when the customer clearly confirms item + qty in WhatsApp, the AI's `send_quote` tool creates an `awaiting_payment` deal and sends the Razorpay link immediately — no staff confirmation. If item/qty/stock is ambiguous the AI asks instead.
- Stock deducts only on **won**; a won deal later marked lost returns stock. "Held" quantity = sum of qty on `awaiting_payment` deals (computed, never stored). Available = stock − held.
- Product with no image: violet initials tile in UI; AI simply doesn't send an image.
- GST optional: `catalog_items.gst_rate` nullable. Tax columns appear in the export only when business profile has a GSTIN **and** at least one exported line has a gst_rate. Each tenant chooses `prices_include_gst` (default **true**).
- Monthly auditor export: Excel (.xlsx, openpyxl already in requirements) with the TENANT's business name/address/GSTIN header, never Aira branding. Won deals only, won_at inside the month (IST). Won-then-lost (refund) appears as a negative row in the month it was lost.
- Names: sidebar **Intake → Deals** (`/dashboard/deals`), **Catalog → Products** (route stays `/dashboard/catalog`). `/dashboard/intake` redirects to `/dashboard/deals?tab=forms`.
- Deals page tabs: **Board | List | Insights | Form answers** (Form answers only when the tenant's intake is enabled; it renders the existing intake table).
- IndiaMART/JustDial: no current client uses them — fix and test with sample payloads. On a new enquiry: send WhatsApp template (tenant-configured) + put the lead on the call queue.

## Permissions
Deals read: `leads.view`. Deals write: `leads.manage`. Products: existing `catalog.view` / `catalog.manage`. Business profile write: `settings.manage`, read: `settings.view`.

## Money & time conventions
All money in paise (int). `line_total_paise = qty * unit_price_paise`. `total_paise = sum(line_total_paise)`. Deal number displayed as `D-` + zero-padded 4 digits (`D-0041`). Month boundaries in Asia/Kolkata.

GST maths (export only, per line, rate r%):
- prices_include_gst=true: taxable = round(line_total * 100 / (100 + r)); tax = line_total − taxable.
- prices_include_gst=false: taxable = line_total; tax = round(line_total * r / 100); the customer total shown in the export = taxable + tax. (The payment link charges `total_paise` as stored, so when prices exclude GST, `create_deal` must add tax into `unit_price_paise`-derived totals: deal `total_paise` = sum(line_total + tax). Store `line_total_paise` pre-tax; store tax-inclusive total on the deal.)
- Tax split: if the customer's state (not collected today) is unknown, treat as intra-state → CGST = SGST = tax/2 (CGST gets the odd paisa). IGST column present but 0.

## Backend contract

### services/deals.py (single owner of deal + stock logic)
```python
DealLine = {"catalog_item_id": str | None, "name": str, "qty": int, "unit_price_paise": int | None, "gst_rate": float | None}

async def create_deal(tenant_id, lead_id, lines: list[DealLine], source, stage="quoted", *,
                      payment_method=None, notes=None, created_by=None, intake_session_id=None,
                      send_link=False, db=None) -> dict
    # Resolves missing unit_price_paise / gst_rate from catalog_items (tenant-scoped).
    # Allocates deal_number via rpc next_deal_number. Inserts deal + deal_items.
    # stage="won": sets won_at, payment_method, deducts stock (apply_stock_movement reason 'sale').
    # send_link=True (stage becomes awaiting_payment): calls send_payment_link.
    # Returns {"deal": row, "items": [...], "payment_link": str|None,
    #          "message_sent": bool, "stock_warnings": [{"catalog_item_id","name","available"}]}

async def send_payment_link(tenant_id, deal_id, *, send_whatsapp_message=True, db=None) -> dict
    # payment_razorpay.create_payment_link(idempotency_key=f"deal:{id}:payment_link",
    #   notes={"deal_id": id}, ...). Sets stage awaiting_payment, payment_link,
    #   razorpay_payment_link_id, link_expires_at (+24h). Sends summary + link via WhatsApp
    #   (freeform; if outside the 24h window the send fails -> message_sent False, link
    #   still returned so staff can share it). Returns {"payment_link", "message_sent"}.

def mark_won(tenant_id, deal_id, *, payment_method, razorpay_payment_id=None, created_by=None, db=None) -> dict | None
    # Claim: update ... .neq("stage","won") -- exactly one concurrent caller wins.
    # Deduct stock per line with catalog_item_id. Never fails the sale on stock.
    # Returns {"deal", "stock_warnings"} or None if unknown/already won.

def mark_lost(tenant_id, deal_id, reason: str, *, created_by=None, db=None) -> dict | None
    # If it was won: return stock (reason 'return'). Sets lost_at, lost_reason.

def upsert_quoted_deal(tenant_id, lead_id, line: DealLine, db=None) -> None
    # AI recommended a priced item: one open 'quoted' deal (source whatsapp) per lead --
    # replace its single line + total. Never raises (log warning).

def sync_intake_session(session: dict, db=None) -> None
    # Form flow mirror, keyed by deals.intake_session_id (unique). Never raises.
    # awaiting_payment -> deal awaiting_payment (lines = package + add-ons, payment_link copied)
    # paid -> mark_won(payment_method 'razorpay'); cancelled -> mark_lost('Link expired' or 'Cancelled')
    # resolved -> no change. offer_pending/collecting -> nothing.

def adjust_stock(tenant_id, item_id, delta, reason, *, note=None, created_by=None, deal_id=None, db=None) -> dict
    # thin wrapper over rpc apply_stock_movement -> {"ok","tracked","quantity_after"}

def held_quantities(tenant_id, item_ids: list[str], db=None) -> dict[str, int]
def get_deal_tenant_id(deal_id, db=None) -> str | None
def quote_summary_block(lines, total_paise) -> str   # moved from quotes.py, Python-rendered prices
def format_deal_number(n: int) -> str                # "D-0041"
```

### routes/deals.py — prefix `/api/v1/deals` (authed)
| Method | Path | Body / query | Returns |
|---|---|---|---|
| GET | `/board` | — | `{columns: {quoted, awaiting_payment, won, lost: {count, total_paise, deals: DealSummary[], has_more}}}` — won/lost limited to last 30 days; 100 cards per column |
| GET | `` | `stage, source, q (name/phone/deal no), month=YYYY-MM, cursor, limit≤100` | `{data: DealSummary[], next_cursor}` |
| GET | `/{deal_id}` | — | `Deal` (with `items`, `lead`, `intake_answers` when linked) |
| POST | `` | `NewDealPayload` | `{deal: Deal, payment_link, message_sent, stock_warnings}` |
| PATCH | `/{deal_id}/stage` | `{stage: "won"|"lost", payment_method?, lost_reason?}` | `{deal: Deal, stock_warnings}` |
| POST | `/{deal_id}/send-link` | — | `{payment_link, message_sent}` |
| GET | `/by-lead/{lead_id}` | — | `{data: DealSummary[]}` |
| GET | `/stats` | `month=YYYY-MM` | `DealStats` |
| GET | `/export` | `month=YYYY-MM, format=xlsx|csv` | file download |

`NewDealPayload = {lead_id?: str, phone?: str, name?: str, items: [{catalog_item_id?, name, qty, unit_price_paise?}], source: "call"|"walk_in"|"manual", stage: "won"|"awaiting_payment"|"quoted", payment_method?, notes?}` — exactly one of lead_id / phone; a new phone creates a lead (source `manual`, normalized via `routes/upload._normalize_phone`, dedupe on tenant+phone).

`DealSummary = {id, deal_number, deal_label, stage, source, total_paise, payment_method, payment_link, created_at, won_at, lost_at, lost_reason, lead: {id, name, phone}, item_summary: "Earbuds ×2, Charger ×1", item_count}`
`Deal = DealSummary + {items: DealItem[], notes, link_expires_at, razorpay_payment_id, intake_session_id, intake_answers: dict|null}`
`DealItem = {id, catalog_item_id, name, qty, unit_price_paise, gst_rate, line_total_paise}`
`DealStats = {month, won_count, won_total_paise, lost_count, open_count, open_total_paise, by_source: {source: {count,total_paise}}, by_day: [{date, total_paise, count}], top_items: [{name, qty, total_paise}], low_stock: [{id, name, stock_quantity, held_quantity}]}` (low stock = tracked items with available ≤ 5)

### routes/business_details.py — prefix `/api/v1/business-details`
GET / PUT `BusinessProfile = {legal_name, address, city, state, pincode, gstin, email, phone, prices_include_gst: bool}` stored as JSON in app_settings key `business_details`. GSTIN validated (15 chars, regex `^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$`) when non-empty. Defaults: legal_name = tenants.name, phone = tenants.contact_phone, prices_include_gst = true.

### routes/catalog.py additions
- `GET /items`: each item adds `held_quantity: int` and `thumbnail_url: str|null` (first media by sort_order).
- create/update accept `gst_rate`. On update, a changed `stock_quantity` is applied as an `adjustment` movement (delta = new − current); on create a non-null stock is set directly and logged as `restock`.
- `POST /items/{id}/stock` `{delta, reason: "restock"|"adjustment"|"return", note?}` → `{ok, tracked, quantity_after}` (`catalog.manage`). Setting stock on an untracked item (NULL) via restock initialises it.
- `GET /items/{id}/stock-movements` → `{data: StockMovement[]}` newest first, limit 100.

### Integrations
- Razorpay webhook (`routes/intake.py` `/razorpay-webhook`): new `notes.deal_id` branch — tenant via `get_deal_tenant_id`, signature per tenant as today; `payment_link.paid` → `mark_won(payment_method="razorpay")` + WhatsApp receipt; `payment_link.expired`/`payment_link.cancelled` → `mark_lost("Link expired")`; `payment.failed` → ignore. Drop the `quote_id` branch. Intake `booking_id` branch unchanged, plus `sync_intake_session`.
- `ai_reply.py`: `send_quote` → `create_deal(stage="awaiting_payment", source="whatsapp", send_link=False)` then reply text = summary + link (the reply itself carries it, so no second WhatsApp message). Respect available = stock − held. `recommend_catalog_item` → `upsert_quoted_deal`.
- `services/intake.py`: call `sync_intake_session` after each status write (awaiting_payment, paid, expire, sweep cancel, package change).
- `routes/intake.py`: remove `/board`. `routes/leads.py`: remove `POST /{id}/quote` and `GET /{id}/quotes`.
- `ask.py`: add a sales tool (today/week/month won totals, top items, unpaid awaiting deals, low stock).

## Frontend contract
- `lib/api.ts` owns types + `api.deals.*`, `api.businessProfile.*`, `api.catalog.adjustStock/stockMovements` (written first, by the lead).
- `frontend/app/dashboard/deals/` page; shared components in `frontend/components/deals/` — `NewDealDialog` is exported and reused by the lead side panel and the call-feedback flow.
- Design system: violet `#5b21b6` primary on cream; reuse existing tailwind tokens (`bg-primary`, `text-ink`, `text-ink-muted`, `border-border`, `bg-surface-subtle`, `font-display`, `font-label`, `font-body`). Stage colours: quoted slate, awaiting amber, won emerald, lost rose.
