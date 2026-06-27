import logging

logger = logging.getLogger(__name__)

OUTCOME_SCORES: dict[str, float] = {
    "converted": 10.0,
    "callback": 7.5,
    "not_interested": 3.5,
    "no_answer": 2.0,
}

DEFAULT_BASELINE = 7.0
ROLLING_WINDOW = 10
MIN_MONTHLY_CALLS = 20

# Weight split between outcome-based score and AI evaluation score.
# When AI evaluation is not available, outcome score carries 100%.
_OUTCOME_WEIGHT = 0.5
_AI_WEIGHT = 0.5


def score_from_outcome(outcome: str | None, duration_seconds: int | None) -> float:
    base = OUTCOME_SCORES.get(outcome or "", 5.0)
    if duration_seconds and duration_seconds >= 60:
        base = min(10.0, base + 0.5)
    return round(base, 1)


def _effective_score(outcome_score: float, evaluation: dict | None) -> float:
    """Blend outcome score with AI overall_score when available.

    With AI: 50% outcome + 50% AI evaluation score
    Without AI: 100% outcome score (no penalty for missing evaluation)
    """
    if not evaluation:
        return outcome_score
    ai_score = evaluation.get("overall_score")
    if ai_score is None:
        return outcome_score
    return round(_OUTCOME_WEIGHT * outcome_score + _AI_WEIGHT * float(ai_score), 1)


def recompute_caller_score(caller_id: str, db) -> float:
    rows = (
        db.table("call_logs")
        .select("score,evaluation")
        .eq("caller_id", caller_id)
        .not_.is_("score", "null")
        .order("created_at", desc=True)
        .limit(ROLLING_WINDOW)
        .execute()
    )
    scores = []
    for r in (rows.data or []):
        raw = r.get("score")
        if raw is None:
            continue
        scores.append(_effective_score(float(raw), r.get("evaluation")))

    if not scores:
        return DEFAULT_BASELINE
    avg = round(sum(scores) / len(scores), 1)
    db.table("callers").update({"overall_score": avg}).eq("id", caller_id).execute()
    logger.info(f"Caller {caller_id} score recomputed: {avg} over last {len(scores)} calls")
    return avg
