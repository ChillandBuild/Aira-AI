# Aira Business Kit (Stage 1) — design

Date: 2026-09-24. Approved in conversation (mockup: https://claude.ai/artifact/1iNYCSoTZtbo8wmoFZerbL).

## Problem
Clients from any industry sign up alone (self-serve) and must fill Aira's knowledge. A blank upload box
gives them no idea what to write, and what they upload varies wildly. Auto-Sort already routes any file to
Description / facts / handover, but it can only sort what the client provides. Missing basics (prices,
buying steps, handover number) silently degrade replies and the scoring rubric.

## Decision
One document shape for every business — the **Aira Business Kit**, 8 headings — and three ways to get it:

1. **Copy AI prompt** — the client pastes it into ChatGPT/Gemini/Claude, which writes the Kit or
   interviews them. Unknowns become `[OWNER TO CHECK]`, never guesses.
2. **Download template** — a Word file per industry: blank Kit with `[WRITE ...]` hints on top, a
   made-up filled example below a delete-me marker. All examples are invented businesses; no client's
   real material is ever reused.
3. **Upload what you have** — unchanged.

| # | Kit heading | Lands in |
|---|---|---|
| 1 | About your business | Description · ABOUT US |
| 2 | Who your customers are | Description · WHO WE TALK TO |
| 3 | How a customer buys from you (+ "Aira's goal") | Description · HOW CUSTOMERS BUY / YOUR JOB — feeds the rubric's Hot rule |
| 4 | How Aira should sound (optional) | Description · HOW TO SOUND |
| 5 | What Aira must never say or promise | Description · WHAT YOU MUST NEVER DO |
| 6 | When to hand over to a person | handover_line (verified against the file) |
| 7 | Products, services, prices | facts |
| 8 | Customer questions and policies | facts |

Industries (12): coaching & education, loans & finance, retail & grocery, clinic & healthcare,
real estate, interiors & home services, salon & spa, gym & fitness, restaurant & food, travel & tours,
astrology & spiritual services, general.

## Placement (keep it quiet)
- Everything lives in the existing upload card on the Documents tab. No new tab, page or banner.
- No documents yet: "Nothing written yet?" + two buttons (Copy AI prompt, Download template ▾).
- After the first document: one small link that reopens those two buttons.
- The Description status row above the drop zone becomes the **readiness line**:
  `Aira readiness 6/8 · Refund policy missing [Add]`, or "Aira is ready" when all must-haves exist.
- The RAG explainer card and the old guide/template panels are removed (done 2026-09-24).

## Readiness (deterministic, no AI call)
`GET /api/v1/knowledge/readiness` → 8 items `{key, label, level, ok}`:
- must: about, how_to_buy (Description sections), prices (price-like text in any indexed document's
  facts), handover (handover_line setting).
- nice: who, never (Description sections), questions (Q:/A: lines or policy words in facts).
- optional: voice.
Served under the knowledge router (knowledge.read), so managers get a true answer too — unlike
`/ai-tune/description`, which is owner-only and reads as empty for managers.

"Add" on a missing item: Description items open the Description tab; fact items open a small box whose
text is uploaded as a `.txt` document through the normal upload → sort → review → Apply path (no new write
path); handover opens the Description tab where the handover line is edited.

## Sorting changes (backend/app/services/knowledge_kit.py, pure + unit-tested)
- `strip_example()` — cuts everything from the template's example marker line on, so a client who
  uploads the whole Word file never publishes the invented example business.
- `scrub_placeholders()` — drops lines holding `[OWNER TO CHECK]` or an unfilled `[WRITE ...]` hint (and
  the `Q:` line of an unanswered `A:`), returning them as gaps. `run_sort` runs both before splitting and
  shows gaps in the review's "left out" list as "You left this blank". A placeholder can never become a
  fact, a rule or a handover line.
- `split_kit()` + `knowledge_sort.label_document()` — a file with at least 4 Kit headings is cut on
  those headings and each heading gets a fixed label (1–6 RULE, 7–8 FACT); only text outside them goes
  to the AI labeller. Headings match on letters only, so `## 1. Who your customers are:` still counts.
  **Why it exists (measured, not assumed):** without it `evals/knowledge_sort/run_kit_eval.py` sorted
  3/12 industry files cleanly — the splitter packed the short "About" section together with the title,
  the chunk was labelled FACT, and 9/12 Descriptions had no ABOUT US. With it: 12/12, twice.

## Verification
- Unit tests for knowledge_kit (example cut, placeholder scrub incl. Q/A pairs, readiness rules).
- `evals/knowledge_sort/run_kit_eval.py` (real model, read-only) on the 12 filled examples, each with an
  [OWNER TO CHECK] Q&A and a decoy example block appended: every price and Q&A line in facts verbatim,
  handover number in the handover line and not the Description, ABOUT US + HOW CUSTOMERS BUY present,
  0 placeholder/decoy leaks, all 4 must-haves ready. Result 2026-09-24: 12/12 on two runs.
- Frontend typecheck + lint.

## Out of scope (Stage 2, only if data shows need)
In-app question form; non-English Kit.
