"""Group and score for TeleCMI calls (CallIQ Steps 1-2).

not_connected / very_short get no AI at all. early_exit gets the basic check but
no score. real_conversation is the sum of the 10 checks out of 100 — provisional
until check 10 (the wrap-up) is marked. Recomputed from the stored row every time
an input changes, so arrival order doesn't matter.
"""
import logging

from app.services.scoring_rules import MIN_SCORED_SECONDS, RULES_VERSION

logger = logging.getLogger(__name__)

TERMINAL_STATUSES = ("completed", "no_answer", "missed", "failed")
SCORED_PROVIDERS = ("telecmi",)
_ROW_FIELDS = "id,provider,status,duration_seconds,ai_status,evaluation"


def compute_call_score(*, status: str | None, duration: int | None, ai_status: str | None, evaluation: dict | None) -> dict:
    from app.services.call_marking import total_score

    result = {"call_group": None, "score_status": "processing", "score": None, "score_final": False}
    if status not in TERMINAL_STATUSES:
        return result
    seconds = duration or 0
    if status != "completed" or seconds == 0:
        return {**result, "call_group": "not_connected", "score_status": "not_connected", "score_final": True}
    if seconds < MIN_SCORED_SECONDS:
        return {**result, "call_group": "very_short", "score_status": "very_short", "score_final": True}
    if ai_status == "failed":
        return {**result, "score_status": "failed"}
    if ai_status != "done" or not evaluation or evaluation.get("evaluation_version") != 4:
        return result
    if evaluation.get("group") == "early_exit":
        return {**result, "call_group": "early_exit", "score_status": "early_exit", "score_final": True}
    checks = evaluation.get("checks") or []
    final = bool(checks) and all(c.get("level") for c in checks)
    return {
        "call_group": "real_conversation",
        "score_status": "scored" if final else "provisional",
        "score": total_score(checks),
        "score_final": final,
    }


def finalize_call_score(db, call_log_id: str) -> dict | None:
    """Recompute and store the group/score for one call. Safe to call any number of times."""
    res = db.table("call_logs").select(_ROW_FIELDS).eq("id", call_log_id).maybe_single().execute()
    row = res.data if res else None
    if not row or row.get("provider") not in SCORED_PROVIDERS:
        return None
    result = compute_call_score(
        status=row.get("status"), duration=row.get("duration_seconds"),
        ai_status=row.get("ai_status"), evaluation=row.get("evaluation"),
    )
    db.table("call_logs").update({**result, "rules_version": RULES_VERSION}).eq("id", call_log_id).execute()
    return result
