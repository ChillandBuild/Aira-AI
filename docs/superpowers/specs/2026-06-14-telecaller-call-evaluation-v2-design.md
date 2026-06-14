# Telecaller Call Evaluation v2 — Design

**Date:** 2026-06-14
**Status:** Approved → implementation

## Problem

The current per-call AI evaluation (`call_logs.evaluation`, 5 keys: `talk_ratio`,
`objection_handling`, `outcome_clarity`, `overall_score`, `coaching_tip`) is a thin
pass/fail-ish snapshot. It's never displayed anywhere in the UI, doesn't check
product-knowledge accuracy against real tenant content, and doesn't flag when a
telecaller's recorded disposition (`call_logs.outcome`) doesn't match what actually
happened on the call.

We want a fuller QA scorecard (13 criteria, grouped below) that:
- Grades product-knowledge against the tenant's actual knowledge base (RAG-grounded).
- Flags outcome/disposition mismatches for QA review.
- Surfaces AI insights (sentiment, purchase intent, missed opportunities).
- Gives a per-call "why" (reasons), and a per-caller score history/trend.

## Current state (for reference)

- `call_logs.evaluation` (jsonb, migration 045) — written by `analyze_call()` in
  [call_summarizer.py](../../../backend/app/services/call_summarizer.py), called from
  `_run_summarization` in [calls.py](../../../backend/app/routes/calls.py#L444).
- `evaluation.overall_score` (1-10) feeds `call_scorer._effective_score()` — 50/50
  blend with the outcome-based score, rolled into `callers.overall_score`
  ([call_scorer.py](../../../backend/app/services/call_scorer.py)).
- `evaluate_call`/`summarize_call` (older 2-call functions, same `_EVAL_KEYS`) are dead
  code — `analyze_call` (single-pass) is the only one wired in.
- Nothing in the frontend reads per-call `evaluation` fields today. `QaReviewFeed.tsx`
  only renders `ai_summary` (brief, course, sentiment, next_action, budget).
- `caller_digests` (migration 065, jsonb `stats`) already runs daily per caller with
  `avg_score` + an LLM coaching report ([call_digest.py](../../../backend/app/services/call_digest.py)).

## v2 evaluation schema

Replaces the v1 shape entirely (no DB migration — `evaluation` is jsonb).

```jsonc
{
  "evaluation_version": 2,

  // LLM-graded, 1-10
  "greeting_quality": 8,
  "communication_clarity": 7,
  "product_knowledge": 6,          // graded against KB excerpts (see below)
  "requirement_understanding": 8,
  "conversation_engagement": 7,
  "objection_handling": 5,
  "professionalism": 9,

  // Derived in Python, NOT LLM-graded directly
  "overall_score": 7.1,            // mean of the 7 scores above, round(1)
  "quality_label": "Good",         // Excellent >=9 / Good >=7 / Average >=5 / Bad <5

  // Binary + explanation, LLM-graded
  "clear_next_step": true,
  "next_step_summary": "Scheduled demo call for Friday",
  "outcome_match": false,
  "outcome_match_reason": "Caller marked 'converted' but customer said they'd think about it",

  // AI insights, LLM-graded
  "purchase_intent": "medium",     // high / medium / low
  "missed_opportunity": true,
  "missed_opportunity_note": "Customer asked about pricing tiers — caller didn't offer the premium plan",
  "coaching_tip": "Acknowledge the price objection before pivoting to value."
}
```

Mapping to the original 13 criteria:

| # | Criterion | Field(s) |
|---|---|---|
| 1 | Greeting Quality | `greeting_quality` |
| 2 | Communication Clarity | `communication_clarity` |
| 3 | Product/Service Knowledge | `product_knowledge` (KB-grounded) |
| 4 | Understanding Customer Requirement | `requirement_understanding` |
| 5 | Conversation Engagement | `conversation_engagement` |
| 6 | Objection Handling | `objection_handling` |
| 7 | Follow-up Commitment | `clear_next_step`, `next_step_summary` |
| 8 | Professionalism | `professionalism` |
| 9 | Call Outcome Accuracy | `outcome_match`, `outcome_match_reason` |
| 10 | Overall Call Quality Score | `overall_score`, `quality_label` (derived) |
| 11 | Customer Sentiment | already covered by `ai_summary.sentiment` — not duplicated |
| 12 | Purchase Intent | `purchase_intent` |
| 13 | Missed Opportunity Detection | `missed_opportunity`, `missed_opportunity_note` |

### Backward compatibility
- `overall_score` keeps its name/type → `call_scorer.py` needs **zero changes**.
- Old rows (no `evaluation_version`) keep working for scoring; the UI simply renders
  no scorecard panel for them (see below).

## Prompt rewrite + KB grounding

In `_run_summarization` ([calls.py:464](../../../backend/app/routes/calls.py#L464)),
before calling `analyze_call`:

```python
from app.services.knowledge_service import get_knowledge_context

kb_context = await get_knowledge_context(tenant_id, query=transcript[:1500])
```

`get_knowledge_context` already falls back to full-text / empty string on any error
(North Star: never blocks the pipeline). One extra retrieval call, **no extra LLM call**.

`analyze_call` signature becomes:

```python
async def analyze_call(
    transcript: str,
    lead_name: str | None = None,
    outcome: str | None = None,
    kb_context: str | None = None,
) -> tuple[dict, dict]:
```

`calls.py` passes `outcome=call_data.get("outcome")` (already fetched in `call_data`).

Prompt additions to `_ANALYZE_USER`:
- A "Knowledge base reference" block containing `kb_context`, used to grade
  `product_knowledge` — if empty, instruct the model to grade leniently / return a
  neutral score rather than guessing.
- `"Caller-recorded outcome: {outcome}"` — basis for `outcome_match` /
  `outcome_match_reason`.
- Full list of new v2 fields requested (excluding `overall_score`/`quality_label`,
  which are derived).

`_EVAL_KEYS` updated to the v2 field set (minus derived fields). Remove dead
`evaluate_call` / `summarize_call` functions and old `_EVALUATE_PROMPT`.

## Derivation logic

After parsing the LLM JSON, in `analyze_call`:

```python
_SCORE_KEYS = [
    "greeting_quality", "communication_clarity", "product_knowledge",
    "requirement_understanding", "conversation_engagement",
    "objection_handling", "professionalism",
]

def _quality_label(score: float) -> str:
    if score >= 9: return "Excellent"
    if score >= 7: return "Good"
    if score >= 5: return "Average"
    return "Bad"

scores = [evaluation[k] for k in _SCORE_KEYS if k in evaluation]
if scores:
    overall = round(sum(scores) / len(scores), 1)
    evaluation["overall_score"] = overall
    evaluation["quality_label"] = _quality_label(overall)
evaluation["evaluation_version"] = 2
```

Deriving `overall_score`/`quality_label` in Python (rather than asking the LLM)
guarantees internal consistency — sub-scores and the headline score/label can't
contradict each other.

## QaReviewFeed scorecard UI

[QaReviewFeed.tsx](../../../frontend/app/dashboard/telecalling/components/sections/QaReviewFeed.tsx)
gains a scorecard panel under the existing `ai_summary` block, rendered only when
`evaluation.evaluation_version === 2` (older rows render nothing extra — no broken UI):

- 7 criteria as compact score chips (e.g. "Greeting 8/10")
- `overall_score` + `quality_label` badge (color-coded: Excellent=emerald, Good=blue,
  Average=amber, Bad=rose)
- `clear_next_step` / `next_step_summary`
- `outcome_match === false` → red "⚠ Outcome Mismatch" badge next to the existing
  outcome badge, with `outcome_match_reason` as title/tooltip
- `purchase_intent` badge
- `missed_opportunity === true` → callout with `missed_opportunity_note`
- `coaching_tip`

`CallLog["evaluation"]` type in [api.ts](../../../frontend/lib/api.ts) updated to the
v2 shape, all fields optional (covers legacy rows).

## Digest enrichment (score history + trend "why")

[call_digest.py](../../../backend/app/services/call_digest.py) `generate_daily_digest`:
- Also selects `evaluation` from `call_logs`.
- Computes per-criterion daily averages across the 7 scored criteria.
- Finds the weakest criterion (lowest average) for the day.
- Counts `outcome_match === false` occurrences.
- New keys in `caller_digests.stats` (already jsonb, no migration):
  `criteria_avg` (dict), `weakest_criterion` (string), `outcome_mismatches` (int).
- `_DIGEST_PROMPT` gets one more line naming the weakest criterion so the generated
  coaching report addresses it directly, e.g. "Today's weakest area: objection_handling
  (avg 4.2/10)."

This gives per-caller score history with explanations via `caller_digests` (existing
`GET /{caller_id}/digest` endpoint, no new table) without re-reading transcripts.

## Out of scope / future work

- No new caller-facing "self view" of scores (admin/QA-only for now, via
  `qa-queue` + `QaReviewFeed`, both `require_owner`-gated).
- `ShiftTimeline` / caller-timeline enrichment with scores — not included; can be a
  follow-up once v2 data has accumulated.
- `talk_ratio` is dropped (unused elsewhere, not in the 13 criteria) — can be re-added
  later if needed.
