"""Per-call score for recorded (TeleCMI) calls: 7 points AI + 3 points outcome.

AI part: average of the admin-selected criteria (each 0-10) scaled to 7.
Outcome part: 1 point when the marked outcome is one the AI accepts for the call,
plus the closing-move score (0-10) scaled to 2. Every outcome, including
not_interested, can earn the full 3.

Only calls of 30s+ talk time with a marked outcome other than no_answer are
scored. The one exception is the safety gate: a 30s+ call marked no_answer on
which the AI heard a real conversation is scored with 0/3 for the outcome part
and flagged to the admin and the telecaller. The score is recomputed from the
stored row every time an input changes, so arrival order doesn't matter.
"""
import logging
from datetime import datetime, timezone

from app.services.call_summarizer import SCORABLE_OUTCOMES

logger = logging.getLogger(__name__)

AI_POINTS = 7.0
ACCURACY_POINTS = 1.0
CLOSING_POINTS = 2.0
SCORE_MIN_SECONDS = 30
TERMINAL_STATUSES = ("completed", "no_answer", "missed")
SCORED_PROVIDERS = ("telecmi",)

_ROW_FIELDS = (
    "id,tenant_id,caller_id,lead_id,provider,status,duration_seconds,outcome,"
    "evaluation,ai_status,flag_status,score_status"
)


def _talk_time(seconds: int) -> str:
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}m {secs:02d}s" if minutes else f"{secs}s"


def compute_call_score(
    *,
    status: str | None,
    duration: int | None,
    outcome: str | None,
    evaluation: dict | None,
    ai_status: str | None,
    flag_status: str | None,
) -> dict:
    """Pure scoring rule. Returns score_status, score, score_breakdown and raise_flag."""
    result = {"score_status": "pending", "score": None, "score_breakdown": None, "raise_flag": False}
    if status not in TERMINAL_STATUSES:
        return result

    seconds = duration or 0
    if seconds < SCORE_MIN_SECONDS:
        result["score_status"] = "no_answer" if outcome == "no_answer" or seconds == 0 else "short_call"
        return result

    if ai_status == "failed":
        result["score_status"] = "failed"
        return result
    if ai_status is None:
        result["score_status"] = "no_recording"
        return result
    if ai_status != "done" or not evaluation or evaluation.get("evaluation_version") != 3:
        return result
    if outcome is None:
        result["score_status"] = "awaiting_outcome"
        return result

    criteria = evaluation.get("criteria") or []
    average = float(evaluation.get("ai_average") or 0)
    ai_points = average / 10 * AI_POINTS

    if outcome == "no_answer":
        if flag_status == "dismissed" or not evaluation.get("real_conversation"):
            result["score_status"] = "no_answer"
            return result
        accuracy = 0.0
        closing = 0.0
        result["raise_flag"] = flag_status is None
    elif outcome in SCORABLE_OUTCOMES:
        accuracy = ACCURACY_POINTS if outcome in (evaluation.get("acceptable_outcomes") or []) else 0.0
        closing = float(evaluation.get("closing_move") or 0) / 10 * CLOSING_POINTS
    else:
        result["score_status"] = "awaiting_outcome"
        return result

    outcome_points = accuracy + closing
    result["score_status"] = "scored"
    result["score"] = round(ai_points + outcome_points, 1)
    result["score_breakdown"] = {
        "ai_points": round(ai_points, 2),
        "ai_average": round(average, 2),
        "criteria": criteria,
        "accuracy_point": accuracy,
        "closing_points": round(closing, 2),
        "outcome_points": round(outcome_points, 2),
        "marked_outcome": outcome,
    }
    return result


def _admin_user_ids(db, tenant_id: str) -> list[str]:
    rows = (
        db.table("tenant_users")
        .select("user_id,role")
        .eq("tenant_id", tenant_id)
        .in_("role", ["owner", "admin"])
        .execute()
    )
    return [r["user_id"] for r in (rows.data or []) if r.get("user_id")]


def _notify_flag(db, row: dict, reason: str) -> None:
    from app.services.notify import notify_user

    tenant_id = row["tenant_id"]
    caller_name = "A telecaller"
    caller_user_id = None
    if row.get("caller_id"):
        caller = db.table("callers").select("name,user_id").eq("id", row["caller_id"]).maybe_single().execute()
        if caller and caller.data:
            caller_name = caller.data.get("name") or caller_name
            caller_user_id = caller.data.get("user_id")
    for user_id in _admin_user_ids(db, tenant_id):
        if user_id == caller_user_id:
            continue
        notify_user(
            tenant_id, user_id, "call_flagged", "Call flagged for review",
            f"{caller_name} marked a {_talk_time(row.get('duration_seconds') or 0)} call as No answer, but the customer spoke.",
            db=db, push_url="/dashboard/telecalling",
        )
    if caller_user_id:
        notify_user(
            tenant_id, caller_user_id, "call_flagged", "Your call was flagged",
            f"{reason} This call has been scored and sent to your admin for review.",
            db=db, push_url="/dashboard/telecalling",
        )


def finalize_call_score(db, call_log_id: str) -> dict | None:
    """Recompute and store the score for one call. Safe to call any number of times."""
    res = db.table("call_logs").select(_ROW_FIELDS).eq("id", call_log_id).maybe_single().execute()
    row = res.data if res else None
    if not row or row.get("provider") not in SCORED_PROVIDERS:
        return None

    result = compute_call_score(
        status=row.get("status"),
        duration=row.get("duration_seconds"),
        outcome=row.get("outcome"),
        evaluation=row.get("evaluation"),
        ai_status=row.get("ai_status"),
        flag_status=row.get("flag_status"),
    )
    updates = {
        "score_status": result["score_status"],
        "score": result["score"],
        "score_breakdown": result["score_breakdown"],
    }
    reason = None
    if result["raise_flag"]:
        reason = f"Marked No answer, but the customer spoke for {_talk_time(row.get('duration_seconds') or 0)}."
        updates.update({
            "flag_status": "open",
            "flag_reason": reason,
            "flagged_at": datetime.now(timezone.utc).isoformat(),
        })
    db.table("call_logs").update(updates).eq("id", call_log_id).execute()

    if reason:
        logger.info(f"Call {call_log_id} flagged: {reason}")
        try:
            _notify_flag(db, row, reason)
        except Exception as e:
            logger.warning(f"Flag notification failed for call {call_log_id}: {e}")
    return result
