# AI-native conversations: one Aira for services and products

Status: BUILT in the working tree as the DEFAULT engine (no per-tenant switch, decided 2026-09-26). Not committed, not deployed. See section 5c.
Written 2026-09-25. Facts below were read from the code or the live DB this session; anything unverified is marked.

## 1. Why change (evidence)

1. **Empty confirmation (2026-09-25, Astro Tamil).** Tenant has no required details (`intake_config.fields = []`). After the lead tapped "49 Rs" the flow jumped to "confirm your details", printed an empty list, and asked "are all details correct?". Cause: `_finalize_leaf` -> `_summary_block` in `backend/app/services/intake.py`.
2. **Angry paying customer (2026-09-24, Astro Tamil).** A lead said they paid and got no answer. For 5 minutes Aira replied with the fixed package menu, the same empty confirmation, and "contact app support" three times. A human handover only opened at 13:18, after "Worst customer support". It was resolved 18 hours later (chat_handovers table).
3. **Stuck sessions.** Last 60 days across the three Astro Tamil tenants: 14 cancelled, 5 stuck in awaiting_confirmation, 1 offer_pending, 7 resolved (paid and handled).
4. **Two engines.** Products already work the AI way: inside `generate_reply` the model calls tools `recommend_catalog_item` and `send_quote` (ai_reply.py ~L1849), and prices come from the catalog. Services (consultations) use a separate state machine, `route_intake`, that runs BEFORE the AI (webhook.py ~L398) and, when it "consumes" a turn, the AI never sees the message. Every bug above lives in that second engine.

## 2. What is different from today

| | Today (services) | Proposed |
|---|---|---|
| Who decides the next step | A status machine: offer_pending, awaiting_package_choice, awaiting_addon_choice, collecting, awaiting_confirmation, awaiting_payment | The AI, from the conversation and a "deal state" note |
| When the flow starts | An LLM yes/no check on the message (`detect_intake_intent`) starts a session and sends a fixed offer message | No trigger. The AI offers packages when it makes sense in the conversation |
| Who sends menus | Python, at fixed moments | The AI calls `send_packages` when a choice is really needed |
| Side question mid-flow | Consumed or bounced: re-shows the menu, or falls out to a generic reply | Answered first, then the AI steers back |
| Collecting details | Fixed order, 2 attempts then skip | Any order, several at once, from the client's list. Same skip-with-marker rule kept |
| Payment link | Python after a "yes" to a summary | The AI calls `create_payment_link`. Code refuses unless the rules are met |
| Human handoff | Triggers A to F in code | Same triggers, plus a `hand_to_human` tool and a payment-complaint rule |
| Products | Already tool-based | Same engine, same tools. Nothing new to learn |
| Settings | Packages page + Intake config panel, two places | One "Offerings" page (later phase) |

Kept exactly as is: the intake_sessions table (Deals board sync, Razorpay confirmation, Astro bridge push, staleness sweep all depend on it), `confirm_intake_payment`, `create_payment_link` with its idempotency key, `_trigger_chat_escalation`, business hours, language mode, opt-out handling, catalog rules and quick-reply blocks.

Unverified: the 24-hour WhatsApp window is checked in the segments and leads routes (grep, this session). I did not confirm the reply path itself blocks free text outside the window. P1 must check this before the AI is trusted to send anything.

## 3. Architecture

```
inbound WhatsApp message
  -> webhook (typing indicator, tamil-lock, opt-out)      [unchanged]
  -> tenant flag conversation_engine == "ai_native" ?
        no  -> route_intake (legacy)                      [unchanged, until removed]
        yes -> generate_reply with offering tools + DEAL STATE
```

There is no pre-AI interception in the new path. The AI always sees the message.

### 3.1 One config: Offerings

Read-only adapter first. It reads today's stores and presents one shape, with no data migration:

- kind: service or product
- packages (with add-ons, amounts, button labels, descriptions) from `intake_config.packages`; products and images from the catalog
- required_details (key, label, type, options) from `intake_config.fields`
- payment_rule: link only after all required details are saved (default), or link right after selection
- handover_line, service_noun, and rules in plain language (client's own text)

The settings UI merge (packages + details on one page) is a separate, later phase. The adapter means the AI does not care where the data lives.

### 3.2 Deal state note

A short block injected on every turn, built from the intake_sessions row. Example:

```
DEAL STATE
selected: One Question, Rs 49 (add-ons: none)
required details: name = Ravi, birth date = 12-03-1994, birth time = MISSING
payment: not sent
```

The AI reads this instead of guessing from chat history. After a break of days, the note is how it resumes. It replaces the two hand-written prompt blocks `_intake_in_progress_prompt_block` and `_intake_paid_prompt_block` with one generated block (paid text kept).

### 3.3 Tools (the AI asks, the code does)

| Tool | What it does | Code refuses when |
|---|---|---|
| send_packages(level) | Sends buttons (up to 3) or a list (up to 10 rows) from config | No active packages |
| get_offering_details(key) | Returns price, description, required details | Unknown key |
| select_offering(key, addons) | Writes the choice to the session, returns missing details | Package inactive or not in config |
| save_details(fields) | Validates against the client's schema, saves, returns what is still missing | Key not in schema |
| skip_detail(key, reason) | Marks a detail as not provided (lead cannot answer) | Key not in schema |
| create_payment_link() | Creates the Razorpay link from the SESSION amount. The AI never passes an amount | No selection, required details missing (unless skipped), link already sent for this selection |
| hand_to_human(reason) | Opens a chat_handover | Handover already pending (no duplicate) |
| recommend_catalog_item, send_quote, quick reply blocks | Already exist | Existing rules |

The link text and price come from tool output. The AI writes the words around them and never types a price or URL from memory.

### 3.4 Who decides what

| Decided by the AI | Enforced by code (never trusts the AI) |
|---|---|
| When to show packages, what to say, order of questions | Prices, links, amounts |
| Answering side questions and steering back | Required details before the link |
| Tone, language, length | 24-hour WhatsApp window, business hours, opt-out |
| Whether the lead sounds ready to pay | Paid status (Razorpay webhook only) |
| When to offer a human | Tenant scoping (every tool takes tenant_id from the session, never from the model) |

### 3.5 Human handoff

Keep triggers A (fallback), B (LLM error), C (asked for human), D (repeated question), F (AI said team will follow up). Add:

- **Payment complaint:** the lead says they paid and got nothing, or asks about payment status. Aira must not answer from knowledge or point to the app. It hands to a human on the FIRST such message and says what will happen, using the client's handover line.
- **Unknown twice:** Aira does not know the answer to the same thing twice. Escalate (as the user asked).
- **Tool or model failure:** never silence. Trigger B already exists; the new path must route to it.

### 3.6 Human feel (prompt rules, all measurable)

- Answer the question first. Only then, if it helps, move the deal forward.
- Never send the same menu twice in a row. Never send the same sentence twice.
- One question per message, unless the lead gave several details at once.
- Use the lead's name once known. Short messages. No "select an option" boilerplate.
- Never say bot-like phrases ("I did not understand", "please choose from the options below").

### 3.7 What can be plain text vs what needs a tool

- **Text the client writes (knowledge and description):** persona, who each package suits, FAQs, refund policy, objection answers, what to say when unsure.
- **Live data or actions (tools):** packages and prices, product catalog and images, required details, saving details, payment link, payment status, handoff, business hours.

## 4. Rollout (nothing changes in production without your approval)

1. Per-tenant setting `conversation_engine` = legacy (default) or ai_native. Off everywhere at first.
2. Offline first: run the scenario set (section 5) against the new engine with the production prompt builder and a stubbed DB, like `backend/evals/replies/run_eval.py`. Compare with the legacy engine on the same scenarios.
3. Pilot on ONE tenant you choose, with a rollback flag flip. Watch handovers, paid conversions, and complaints for a week.
4. Only after that: move the rest, then remove `route_intake`.

Small fix meanwhile (separate, your call): in legacy, when a tenant has no required details, skip the confirmation step and go straight to the payment link. It stops today's empty message while the new engine is built.

## 5. How we will measure it

Scenario file: `backend/evals/conversations/scenarios.json` (16 scenarios: today's bug, the 09-24 complaint, side questions, injection, language, products, stale return).

- **Hard checks, must pass 100%:** no price or link that did not come from a tool; no link before required details; handover on payment complaint within 1 message; no empty block; no repeated identical reply; nothing sent outside the 24-hour window; opt-out respected.
- **Judge score (LLM, strict, like the reply eval):** sounds human, answered the question first, stayed on the deal, right language.
- **Numbers to report for legacy vs new:** hard-check pass rate, judge score, LLM calls per turn, latency per turn, cost per turn.

## 5b. Baseline on the legacy flow (P1, run 2026-09-25)

Harness: `cd backend && .venv/bin/python -m evals.conversations.run_eval --key-tenant <tenant_uuid>`. It runs the real `route_intake` and real LLM calls (Astro Tamil's keys) with an in-memory DB and captured sends. Nothing is written or sent. Product scenarios are skipped (that path is not route_intake). Only trigger C (asked for a human) is simulated on the fallback path, so the handover checks under-count legacy.

Result, 14 scenarios, hard checks only: 24 pass, 5 fail, 2 skipped. The judge score has not been run.

| Scenario | Check | What legacy did |
|---|---|---|
| empty-details-tap-package | no_empty_block FAIL | Empty "confirm your details" after the 49 Rs tap (reproduces the live bug) |
| payment-complaint-angry | handover_on_payment_complaint FAIL | Lead says "I paid". Aira replies with a consultation sales offer, then says "payment confirm aagala" and "app-la endha problem-um illa" without checking anything. Handover only at turn 6 of 7 |
| closed-hours-human-request | handover_on_human_request FAIL | "I want to talk to a person now" was read as buying intent. Aira sent the consultation offer and no handover. The human-request check in route_intake only runs when a session already exists |
| price-haggle-and-discount | no_invented_price FAIL | Aira quoted "starts at Rs 29". The configured packages are Rs 49 and Rs 99. Where the 29 comes from (knowledge or old config) is not verified |
| unknown_twice_escalates | handover_on_unknown_twice FAIL | Not a fair fail: trigger D is not simulated |

## 5c. The new engine, as built (2026-09-26)

Decision: it replaces the old flow for every tenant that has offerings configured. There is no per-tenant switch. Rollback = revert the commit; `route_intake` and the rest of the old flow are left in intake.py, unused, until phase P5.

Files: `backend/app/services/deal_engine.py` (prompt blocks, tool schemas, price check), `deal_actions.py` (guarded tool executors), `deal_turn.py` (model round-trip, guards, menu sender). Wiring: `ai_reply.py` (`build_reply_system_prompt`, `generate_reply`) and `routes/webhook.py` (no more `route_intake` before the AI; the tapped button id is passed through).

Differences from the plan above:
- Six tools, not seven. `check_payment_status` is folded into the DEAL STATE note (payment: not sent, link sent, PAID) plus a code guard: a message saying "I paid" or asking payment status opens a handover before the model runs.
- Code guards added after live testing: any rupee figure outside the offerings is sent back for a rewrite; a reply nearly identical to the last one is sent back; the client's "I can't help" line said twice in a row opens a handover; a "[Payment Link]" placeholder is stripped; the same menu is never shown twice in a row; required details in a message are saved by code (`capture_details`, the old extractor) before the model runs.
- Live finding: this provider writes NO text on any turn where it calls a tool. So a selling turn can take 2 to 3 model calls (tool call, tool call, then one tool-free call that writes the words). Plain chat turns stay at 1.

Numbers (Astro Tamil keys, same 14 scenarios, hard checks only, single run each, no judge):

| | Old flow | New engine |
|---|---|---|
| Hard checks | 24 pass, 5 fail, 2 skipped | 29 pass, 0 fail, 2 skipped |
| Avg time per turn | 5.4 s | 8.1 s (max 18.2 s) |

Read these with care: the fixes were tuned against these same scenarios, so 29/29 is a training-set number, not a prediction. The old flow is under-counted on the handover checks (see 5b). The judge score (sounds human) is not built.

Update 2026-09-26 (later): products, orders, business details and the judge are in. Current harness: `backend/evals/conversations/run_aira.py` over 63 scenarios (16 base + 47 out-of-the-box: angry, grieving, typos, Hindi/Tamil script, injection, refunds, UPI, impossible dates, stock limits, order status, wrong number, spam...). Final run on the tenant's own reply model (gemini-3.1-flash-lite): fixed checks 94/94, judge 53 pass / 3 weak / 7 fail, 7.7 s average per turn. Live test on the owner's own Astro Tamil lead (5 real WhatsApp messages) found two bugs the offline runs could not: Astro Tamil's Razorpay keys are rejected (401), and a failed link produced a "team will send it" promise with no handover (fixed: a failed link now opens one).

Data findings, independent of the engine:
- Astro Tamil's knowledge base still quotes "consultations start at Rs 29". The packages are Rs 49 and Rs 99. Both engines quoted it until the new price guard.
- Astro Tamil's handover line tells the customer to "contact app support". For a payment complaint that sends a paying customer away from a person.

## 6. Risks and unknowns

- **Tamil, Tanglish tool-calling reliability on the current reply model is unverified.** This is the biggest risk. The eval decides.
- **More work per turn:** one bigger call replaces several small ones (trigger check, package match, field extraction, wording). Cost and latency must be measured, not assumed.
- **In-flight sessions:** a lead mid-flow when a tenant is switched. Plan: the new engine reads the same session row, so it resumes from the deal state.
- **Wrong-tool calls:** the AI may call `send_packages` too often. Covered by the never-repeat-a-menu check.
- **Which tenant pilots:** to be chosen by the user.

## 6b. Phases

- P0 (optional, small): legacy empty-fields fix above.
- P1: scenarios + harness, run on legacy for the baseline numbers.
- P2: Offerings adapter, deal state note, the 7 new tools, behind the flag.
- P3: pilot on one tenant.
- P4: single Offerings settings page.
- P5: remove the legacy state machine.
