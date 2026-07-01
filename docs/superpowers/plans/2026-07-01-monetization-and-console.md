# Aira AI — Monetization + Developer Console Overhaul

> **For agentic workers:** Use superpowers:subagent-driven-development or superpowers:executing-plans to implement task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Turn the operator console from an internal admin panel into a SaaS control room — with plans, entitlements, metering, a redesigned professional onboarding flow, a fleet-wide view, an expanded feature/toggle system, and a signature toggle component.

**Architecture:** One entitlement system where a "plan" is a saved preset of feature toggles + quotas. Sell simple (2 pillars × 3 tiers + AI tier), track detailed internally (7 metered events). Console shows plan/usage/margin; backend enforces entitlements on protected routes.

**Tech Stack:** FastAPI (`backend/app/`), Next.js 14 (`frontend/app/operator/`), Supabase (Postgres + RLS), Groq/OpenAI (behind an internal model map).

## Global Constraints

- Currency: INR (₹). All prices configurable in DB, never hardcoded in UI.
- Client-facing = tier labels only (AI Basic/Standard/Premium). Tokens & provider names never shown to clients.
- Global revenue/fleet views are `system_admin`-only (existing `get_system_admin` dep).
- Follow existing feature-key + cascade pattern in `operator.py:213-229`.
- Destructive actions require reason-capture written to the existing audit log.
- Meter only 7 events. Everything else is tier-gated on/off — a toggle is not a billing line.

---

# PART 0 — PRICING MODEL (the decisions, locked)

## Product structure
Two pillars, sold independently or together. A client can buy **Messaging only**, **Telecalling only**, or **both**. Tier chosen per pillar.

```
Base platform fee (per pillar/tier)
  + Channel add-ons        (messaging)
  + Messaging modules       (broadcast, templates, automation…)
  + AI tier                 (Off/Basic/Standard/Premium/BYO)
  + Telecalling mode        (SIM Basic / SIM+ / TeleCMI Pro)
  + Team seats
  + Usage overages          (metered)
  + Provider pass-through   (TeleCMI minutes, Meta)
```

## Messaging plans
| | Basic | Standard | Pro |
|---|---|---|---|
| Price/mo | ₹4,999 | ₹14,999 | ₹39,999 |
| Channels | 1 | 3 | all |
| Seats | 2 | 5 | 15 |
| Messages/mo | 1,000 | 5,000 | 25,000 |
| AI replies/mo | 500 | 2,500 | 12,000 |
| AI tier incl. | Basic | Standard | Premium |
| Broadcast/automation/adv-analytics | — | broadcast | all |

## Telecalling plans
| | Basic (SIM) | Standard (SIM+) | Pro (TeleCMI) |
|---|---|---|---|
| Price/mo | ₹2,999 | ₹9,999 | ₹19,999 |
| Engine | SIM manual | SIM + dialer | TeleCMI cloud |
| Caller seats incl. | 2 | 5 | 5 |
| Extra seat | ₹799 | ₹799 | ₹1,499 |
| Included minutes | own SIM | own SIM | 1,000 |
| Recording / AI summary / scoring | — | — | add-on |

## AI tiers (margin shield)
| Client label | Internal model | Price to client |
|---|---|---|
| Off | none | ₹0 |
| Basic | cheap Groq/open | ₹500 / 1,000 replies |
| Standard | mid model | ₹900 / 1,000 replies |
| Premium | Opus/GPT premium | ₹1,500 / 1,000 replies |
| BYO key | client key | ₹999/mo, no usage charge |

Client billed per **reply**, never per token. Tokens tracked internally for margin only.

## The 7 metered events (only these get a counter)
`message_sent`, `ai_reply`, `call_minute` (TeleCMI), `team_seat_active`, `storage_gb`, `ai_call_summary`, `ai_call_scoring`.
Everything else = tier-gated on/off.

## Overage rates
Messages ₹900/1,000 (+Meta pass-through) · AI replies per tier · TeleCMI minutes provider+30% · Msg seat ₹999 · Caller seat ₹799/₹1,499 · Storage ₹199/5 GB. Each has soft cap (80% warn) + optional hard cap.

---

# PART 1 — DATA MODEL

Four core tables (defer invoices/payment/rollups until real clients exist).

### `feature_catalog`
Every toggleable module.
```
feature_key      text pk      -- 'whatsapp', 'ai_tier', 'broadcast', 'tc_recording'…
display_name     text
category         text         -- channels|messaging|ai|telecalling|automation|ops
pillar           text         -- messaging|telecalling|shared
monthly_price    numeric      -- 0 if included/metered-only
usage_metric     text null    -- one of the 7 metered events, or null
unit_price       numeric null
included_qty     int null
depends_on       text[]       -- feature_keys required first
is_metered       boolean
sort_order       int
```

### `plans`
A named preset = bundle of catalog rows + quotas.
```
id, name, pillar, tier ('basic'|'standard'|'pro'),
monthly_price numeric, ai_tier text,
included jsonb   -- {feature_keys:[...], quotas:{messages:5000, ai_replies:2500, seats:5,...}}
active boolean
```

### `tenant_subscriptions`
```
tenant_id fk, status ('trial'|'active'|'past_due'|'suspended'|'cancelled'),
messaging_plan_id null, telecalling_plan_id null, ai_tier text,
custom_overrides jsonb,  -- per-client toggle overrides on top of plan
mrr numeric, period_start date, period_end date, trial_ends date null
```

### `tenant_usage_counters`
```
tenant_id fk, period text ('2026-07'), metric text, used numeric,
included numeric, hard_cap numeric null,
primary key (tenant_id, period, metric)
```

`tenants.enabled_features` stays for backward-compat UI; the entitlement source of truth becomes `plan.included + custom_overrides`. A resolver merges them.

---

# PART 2 — ONBOARDING REDESIGN (professional wizard, no channel picking)

**Replace** the single modal in `operator/(console)/page.tsx:336-403`. Channels are NOT chosen here anymore — they're configured inside the client via the toggle store, driven by the chosen plan.

### 4-step wizard (`components/onboarding-wizard.tsx`)

**Step 1 — Company**
- Company name *
- Business type / industry * (dropdown: Coaching, Real Estate, Healthcare, Agency, E-commerce, Other)  ← new
- Primary contact person name *  ← new
- Contact phone *  ← new
- Billing region / GST state (optional)

**Step 2 — Plan**
- Pillar selector: Messaging / Telecalling / Both (segmented control)
- Tier per selected pillar: Basic / Standard / Pro (plan cards showing price + included)
- AI tier: Off / Basic / Standard / Premium / BYO (segmented)
- Live "New monthly estimate: ₹X,XXX" strip at the bottom

**Step 3 — Owner account**
- Owner email * · Temp password * (with generate button) · "Require change on first login" (default on)

**Step 4 — Review & create**
- Summary card: company, plan(s), AI tier, MRR, what's included. Confirm → create.

### Backend contract fix (kills the confirmed bug)
`CreateClientPayload` currently ignores `features` (`operator.py:85`). Replace with:
```python
class CreateClientPayload(BaseModel):
    company_name: str
    business_type: str
    contact_name: str
    contact_phone: str
    billing_region: str | None = None
    email: EmailStr
    password: str
    messaging_plan_id: str | None = None
    telecalling_plan_id: str | None = None
    ai_tier: Literal["off","basic","standard","premium","byo"] = "off"
```
On create: resolve plan → `enabled_features`, insert `tenant_subscriptions` row + zeroed `tenant_usage_counters` for the period. Store contact fields on `tenants`.

---

# PART 3 — SIGNATURE TOGGLE COMPONENT

Replace the basic 9×5 pill (`sidebar.tsx:82-95`) everywhere with one reusable component that has **four states** and feels premium (spring animation, gradient track, tactile knob). Memory: user expects top-grade UI.

### `components/entitlement-toggle.tsx`
```tsx
type ToggleState = "on" | "off" | "locked" | "metered";

interface EntitlementToggleProps {
  checked: boolean;
  onChange: (next: boolean) => void;
  label: string;
  priceLabel?: string;      // "+₹1,499/mo" — slides in when relevant
  state?: ToggleState;      // locked = plan-gated w/ upgrade CTA
  usage?: { used: number; included: number }; // metered variant → mini ring
  disabled?: boolean;
  size?: "sm" | "md";
}
```

**Visual spec (the "unique" part):**
- Track: 44×24 (md). Off = `bg-ink-muted/20`. On = animated left→right gradient sweep `from-primary to-violet-500`, subtle inner shadow.
- Knob: 20px, white, `shadow-md`, faint radial gradient; on enable it **overshoots then settles** (spring, `cubic-bezier(.34,1.56,.64,1)`), and a tiny check/icon cross-fades inside the knob.
- Ambient glow: on = soft `ring-2 ring-primary/15` halo pulse once.
- `priceLabel` chip slides in from the right with a fade when the feature is paid.
- **Locked state:** track shows a diagonal hatch + lock icon, click opens an "Upgrade to unlock" popover instead of toggling.
- **Metered variant:** replaces the knob-end with a 16px progress ring (used/included), amber at ≥80%, red at 100%.
- Respects `prefers-reduced-motion` (falls back to opacity fade).

**Two consumption patterns:**
- Free/included features → bare toggle inline in a list row.
- Paid features → wrapped in an **"entitlement card"** (icon + name + description + toggle + price chip + dependency note), grouped by category. This is the "Feature Store" in the Config view.

---

# PART 4 — CONSOLE FEATURE ADDITIONS

## 4.1 Expanded toggle tree (13 → ~45)
Grouped in the Config view as a **Feature Store** (categories: Channels, Messaging, AI, Telecalling, Automation, Ops). Backend `valid_features` set (`operator.py:213`) extends to include all catalog keys; keep the cascade pattern for dependencies.

New toggles to expose: channel switches (WhatsApp/IG/FB/Telegram) in the detail view; messaging modules (broadcast, templates, template-sync, auto-retry, re-engagement, human-handover, media, advanced-analytics); AI group (AI tier selector, auto-reply, KB-AI, sentiment, multi-language, custom-prompt); telecalling (scripts, attendance, performance, QA, AI summary, AI scoring, recording); automation (business-hours, escalation, lead-assignment, callbacks, push, DNC, webhook-health, token-expiry-alerts); ops (maintenance-mode, read-only-mode, feature-freeze, sandbox/trial).

Paid toggles show a **quote-preview confirm** (reuse the calling-provider dialog pattern, `config.tsx:195`) with "New monthly estimate: ₹X → ₹Y" and Apply now / next cycle / 7-day trial.

## 4.2 Per-client insight cards (Dashboard upgrade)
- **Usage meter card** — 7 metrics vs included, progress bars, 80% amber / 100% red.
- **Billing card** — plan(s), MRR, status, renewal date, forecast bill, overage estimate.
- **Trends** — 30-day sparklines + WoW deltas on the existing 6 metrics (`overview.tsx`).
- **Health rollup badge** — one green/amber/red from credentials + channel + webhook + scheduler.
- **Activity timeline** — last inbound / broadcast / call / login.

## 4.3 Global fleet cockpit (new page `operator/fleet/page.tsx`)
- **All-clients matrix**: row per tenant × status, plan, health, msgs 30d, AI usage, last activity, MRR. Sortable/filterable.
- **Revenue strip**: MRR, active/trial/suspended counts, clients near cap (`system_admin` only).
- **Fleet health board**: tenants with broken creds / failing webhooks / stale schedulers.
- **Attention queue**: auto-flags ("92% quota by day 15", "no activity 14d", "cred expired").
- **Cross-tenant search**.

## 4.4 Safety upgrades
- Reason-capture text field on wipe/delete/suspend → audit metadata.
- Read-only operator role (split from `get_system_admin`) so support can view without delete power.
- Second-confirm for production tenants on destructive ops.

---

# PART 5 — UI DESIGN SYSTEM PASS

- Unify on the existing token set (`ink`, `primary`, `surface-mid`, `rounded-card`). Fix any mojibake (`â€"`) via UTF-8 normalization pass on operator views.
- Introduce a shared `<Card>`, `<StatTile>`, `<SectionHeader>`, `<Segmented>`, `<EntitlementToggle>`, `<UsageBar>`, `<QuoteConfirm>` component set under `operator/(console)/components/` so every view is consistent.
- Motion: standard 150–200ms ease for hovers; spring only for the toggle knob and price-chip slide.
- Density: fleet matrix = compact table; client cards = generous. Skeletons already exist — reuse.

---

# EXECUTION PHASES (build order)

**Phase 0 — Bug + polish (½ day)**
- [ ] Fix create-client `features`→plan contract (Part 2 backend).
- [ ] UTF-8/mojibake sweep on operator views.

**Phase 1 — Onboarding wizard + toggle component (2–3 days)**
- [ ] Build `EntitlementToggle` (Part 3) with tests for each state.
- [ ] Build 4-step onboarding wizard (Part 2), remove channel picker.

**Phase 2 — Data model + entitlement resolver (3–4 days)**
- [ ] Migrations: `feature_catalog`, `plans`, `tenant_subscriptions`, `tenant_usage_counters` (+ RLS).
- [ ] Seed catalog + plans (Part 0 numbers).
- [ ] Resolver: `plan.included + custom_overrides → enabled_features/quotas`.

**Phase 3 — Feature Store + backend enforcement (3–4 days)**
- [ ] Config view = categorized Feature Store using entitlement cards + quote-preview.
- [ ] Backend checks entitlement/quota on protected send/reply/call routes.

**Phase 4 — Metering counters (3 days)**
- [ ] Increment the 7 counters on send/reply/call-minute/seat/storage/summary/scoring.
- [ ] Soft/hard cap enforcement + usage meter card.

**Phase 5 — Fleet cockpit + insight cards (3–4 days)**
- [ ] Global fleet matrix, revenue strip, health board, attention queue.
- [ ] Per-client billing/usage/trend/timeline cards.

**Phase 6 — Safety + later (defer)**
- [ ] Reason-capture, read-only role, prod second-confirm.
- [ ] (Later, only at scale) invoices, payment gateway, rollups, margin analytics.

---

## Self-review notes
- Every pricing number is sourced to Part 0 and stored in DB, not hardcoded (Global Constraints ✓).
- Onboarding removes channel selection; channels move to in-client toggle store (Part 2 + 4.1 ✓).
- Toggle component covers on/off/locked/metered with concrete visual spec (Part 3 ✓).
- Metering limited to 7 events; other toggles are on/off (Part 0 + 4.1 ✓).
- Create-client bug has an explicit fix task in Phase 0 (✓).
