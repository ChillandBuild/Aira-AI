# Aira AI — Two-Clock Strategy (2026–2030)

**Status:** Approved direction (brainstorm, 2026-07-12)
**Type:** Strategy spec. Every future build/roadmap decision gets checked against this doc.
**One-line summary:** Boring loop, visionary rail, one codebase, two clocks.

---

## 1. The threat this answers

- Messaging automation is a commodity. Anyone with a Claude subscription and Meta's API can ship
  "AI replies to WhatsApp" in a weekend. That market races to ₹499/month.
- The fatal competitor is **Meta itself**: free native "Business AI" agents inside WhatsApp/Instagram.
  You cannot out-price free or out-integrate the platform owner.
- **Rule:** never build (or market) what Meta will give away. Build what Meta structurally won't:
  - Cross-platform truth (Meta will never say Google outperformed them, or that their leads were junk).
  - Off-platform events: phone calls, visits, payments.
  - The client's P&L ("stop spending here").

## 2. The asset Aira already holds

The **full funnel in one system**, already shipped: ad attribution (gclid + Meta referral) →
vernacular AI conversation (Tamil/English/Tanglish; WhatsApp/IG/FB/Telegram) → real phone calls
(TeleCMI + SIM tracking, recordings, call evaluation) → bookings.

Competitors own fragments: Wati/AiSensy/Gallabox have the chat; agencies have the ads; CRMs have
the pipeline. Nobody in the Indian SMB market closes the loop. The moat is the assembly, not any part.

## 3. The decision — two clocks, one codebase

| Clock | Horizon | Job | Wins by |
|---|---|---|---|
| **A — the loop** | Quarters | Pays the bills; becomes impossible to displace | Position + compounding data |
| **B — the rail** | Years | The genuine first-mover claim | Timing + being early with receipts |

**Discipline rule:** Clock B advances ONLY through spec choices on already-paid Clock A work until
Clock A revenue proves out. The moment the lottery ticket eats payroll, we've become a research lab
we can't afford to be.

## 4. Clock A — the loop

### 4.1 Packaging: sell employees, not software

*Honest label: sales tactic, not a moat. Copyable in a week. We do it because it converts, not
because it's novel.*

- One persona first: front-desk + telecaller (working name "Priya").
- Onboarding becomes a **hiring flow**: name her, pick languages, set shift hours (exists),
  feed her the business's knowledge (exists), test-chat "interview" before signing.
- Pricing becomes **salary**: job roles instead of feature carts; usage caps read as overtime.
- Monthly **performance review** report per employee, auto-generated from existing call
  evaluation + lead scoring + the new ledger (4.2).
- Effect: exits the Wati/AiSensy price-per-feature comparison; enters the
  "vs a ₹14,000/month receptionist who quits" comparison.

### 4.2 The moat: the receipts loop (the real bet)

The loop: **₹ ad spend → lead → AI talks to every lead (chat + call) → outcome → back to spend.**

- Unique signal nobody else has: lead quality judged from what leads **said**, not what they
  clicked. Meta grades its own homework; Aira grades it on conversations.
- **v1 — the ledger:** join campaign → lead → conversation → call → booking into one line.
  The monthly review ends with "salary ₹9,999 · attributed bookings ₹31,000."
  (Extends the existing gclid→spend backlog item.)
- **v2 — recommendations:** "Kill campaign B — I talked to all 27 leads, they were junk.
  Move budget to A." Owner approves with one tap. New ad copy drafted from winning transcripts.
- **v3 — autopilot:** approved recommendation types graduate to autonomous budget moves.
- **Attribution stance:** claim **bookings**, not revenue. Cash businesses can dispute rupees;
  they can't dispute a confirmed appointment with a recording attached.

### 4.3 Two habits that start now (near-zero cost, compound forever)

1. **Outcome label on every conversation** (booked / qualified / junk / ghosted).
   This is the data flywheel and, later, the simulator's training set. Schema column + habit.
2. **Health score on every number** (blocks, spam reports, delivery decay) with pooling +
   warm-up + early warning. Solves the open number-spam problem as infrastructure; becomes
   the trust rail's first ledger (5).

## 5. Clock B — the rail (the first-mover bet)

Claim available in 2026, gone by 2028: **"the first platform that makes Indian local businesses
transactable by AI agents."** By 2028–30, customers' own assistants do the finding and booking;
a business either speaks machine or doesn't exist in the query.

- **Agent storefront:** the planned catalog backend is built **machine-readable-first** —
  structured items, live availability, prices, a booking endpoint. Humans see a catalog;
  agents see a storefront. Same sprint, both clocks.
- **Trust rail:** number health grows into verifiable business reputation — real response rates,
  confirmed bookings, complaint rates, receipts-backed ("Aira Verified"). Exactly what another
  AI needs to choose and transact with a business. When AI spam explodes, verified reputation
  becomes the scarce resource.
- **Later, in order:** negotiation as an employee skill within owner-set rules (dynamic pricing
  already on main); synthetic-customer simulator once outcome-labeled data has real mass (year 2+).

## 6. The example that explains everything (Ravi, condensed)

Ravi, astrologer, Madurai. ₹1,000 consultations, ₹12,000/month Meta ads, misses evening leads.

- **Old pitch:** "Subscribe to Aira, ₹6,999/month, automation features." Compared against Wati at ₹2,499.
- **New pitch:** "Hire Priya — Tamil/English, answers in 5 seconds, calls every lead in 5 minutes,
  books into your calendar, works Sundays. Salary ₹9,999. Interview her on your phone right now."
- **One lead:** Tue 9:43 PM ad click (campaign captured) → Tanglish chat answered in 4s →
  qualified → Thursday 6 PM booked + paid at 9:51 PM while Ravi slept. Ledger row:
  `Campaign "Marriage-Matching" → lead → booked ₹1,000`. Cold lead? Priya calls next morning
  in Tamil; call recorded, transcribed, scored.
- **Month-end review:** 412 conversations, 31 bookings = ₹31,000. "Marriage-Matching: ₹190/booking —
  keep. Broad-Awareness: 27 leads, I spoke to all 27, price-shoppers — kill it, move the ₹6,000."
  Salary ₹9,999 vs ₹31,000 attributed.
- **Renewal:** not "is this software worth it" but "do I fire a worker with 3x ROI who knows my
  customers?"
- **2028:** a customer's assistant asks for "good astrologer, Tamil, under ₹1,500, this week."
  Ravi's Aira storefront answers machine-to-machine with slots, prices, and a verified track
  record; the agent books and pays. Zero ad spend, zero human attention on either side.

## 7. Build sequence

| When | What | Notes |
|---|---|---|
| **Q3 2026** | Employee reframe: hiring flow, salary pricing, monthly review report | ~3–4 weeks on top of existing features |
| **Q3 2026** | Outcome labels + number health scores | Schema + small UI, ~1 week; habits start now |
| **Q3 2026** | Fix Tamil script-switch bug | Was a backlog item; an "employee" breaking language mid-chat gets fired → launch blocker |
| **Q4 2026** | Receipts v1: the ledger + review ends with salary-vs-bookings | Extends gclid→spend "big version" backlog item |
| **Q4 2026** | 3 case studies from live tenants | This is the entire marketing plan |
| **H1 2027** | Recommendations with one-tap approval; catalog ships machine-readable-first | Catalog serves both clocks |
| **H2 2027–2028** | Autopilot budget moves; "Aira Verified" agent-readiness marketed publicly; negotiation skill; simulator when data justifies | Say "the rail" out loud early — the first-mover claim is taken by claiming it with receipts |

## 8. The no-list (this is the actual strategy)

- **No white-label / agency channel** for 12 months — they'd own the client relationship first.
- **No horizontal spread.** Verticals: spiritual services, clinics, coaching institutes.
  South India first. Prove ROI per vertical before adding one.
- **No marketing of anything Meta will give away.** Auto-replies stay as table stakes in the
  product and exit the pitch entirely.
- **No enterprise, no custom builds, no US.**
- **No dedicated Clock B headcount** until Clock A revenue proves out.

## 9. Honest assessment (recorded so we don't fool ourselves later)

| Piece | Verdict | What it actually is |
|---|---|---|
| AI-employee framing | Not novel (11x, Artisan, "digital labor" all exist) | Sales tactic; copyable; do it for conversion |
| Receipts loop | The real bet | Position-defensible: requires owning ads+chat+calls+bookings at once |
| Outcome-labeled vernacular data | Compounds | The year-3 unfair advantage no entrant can buy |
| Storefront + trust rail | Timing lottery tickets | Genuinely early; built only as side effects of paid work |

- Even the loop isn't new on Earth — Invoca/CallRail do conversation-driven ad optimization for
  US enterprises in English at enterprise prices. Our version wins on **place, price, language,
  and being one native system instead of five stitched tools**. Novelty is not the win condition;
  position is.
- **Risks:** the employee metaphor raises the quality bar (language bugs become firing offenses);
  attribution will be disputed (hold the bookings-with-recordings line); two-person capacity
  (the sequence above IS the capacity plan — one layer per quarter, nothing parallel).

## 10. The five-year arc

**2026** — hire an AI employee. **2027** — she proves her salary with receipts.
**2028** — she's a growth department that negotiates. **2030** — Aira is the rail that connects
Indian SMBs to the agent economy.

**USP in one sentence:** *Aira is the only AI that spends your marketing money, answers every lead
it creates, calls them in their language, and shows you exactly which rupee became revenue.*
