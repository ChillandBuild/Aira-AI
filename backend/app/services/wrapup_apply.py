"""Writes one saved call wrap-up (v2): the call row, the lead, reminders, the sale and the
reassign alert. The rules themselves live in services/call_wrapup.py."""
import logging
from datetime import datetime

from app.services.assignment import get_telecalling_config, maybe_assign_lead
from app.services.call_alerts import raise_reassign_alert
from app.services.call_wrapup import (
    CLOSED_LEAD_STATUSES, NO_CONNECTS, REMINDER_OUTCOMES, STOP_ALL_FOLLOW_UPS,
    consecutive_no_connects, is_no_connect, lead_status_after, reminder_note, sale_lines, suggest_retry_at,
)
from app.services.deals import create_deal
from app.services.growth import cancel_pending_follow_ups, record_stage_event, sync_follow_up_jobs

logger = logging.getLogger(__name__)
LEAD_HISTORY_LIMIT = 50


def _earlier_calls(db, tenant_id: str, lead_id: str, call_log_id: str) -> list[dict]:
    rows = (
        db.table("call_logs").select("id,manual_status,status,created_at")
        .eq("lead_id", lead_id).eq("tenant_id", tenant_id)
        .order("created_at", desc=True).limit(LEAD_HISTORY_LIMIT).execute()
    ).data or []
    return [r for r in rows if r["id"] != call_log_id]


async def apply_wrapup(
    db, *, tenant_id: str, user_id: str | None, caller_id: str | None, call_log_id: str,
    log: dict, wrapup: dict, log_extra: dict, now: datetime,
) -> dict:
    manual_status = wrapup["manual_status"]
    outcome = wrapup.get("outcome")
    notes = (wrapup.get("notes") or "").strip() or None
    lead_id = log.get("lead_id")
    earlier = _earlier_calls(db, tenant_id, lead_id, call_log_id) if lead_id else []

    next_at = wrapup.get("next_action_at")
    if manual_status in NO_CONNECTS:
        next_at = next_at or suggest_retry_at(manual_status, consecutive_no_connects(earlier), now)
    elif outcome not in REMINDER_OUTCOMES:
        next_at = None

    status = None
    if lead_id:
        no_connects_total = sum(1 for r in earlier if is_no_connect(r)) + (1 if manual_status in NO_CONNECTS else 0)
        max_attempts = get_telecalling_config(tenant_id).get("max_call_attempts", 4)
        status = lead_status_after(manual_status, outcome, no_connects_total, max_attempts)
        if status == "unreachable":
            # Nobody should be dialled for an unreachable lead -- no more retry reminders.
            next_at = None

    # The sale first: if the deal can't be created (unknown product, no price) nothing is written.
    # A conditional update claims the conversion atomically (scoped to this call_logs row, only when
    # its outcome isn't already 'converted'), so a double-tap or a retry racing another request's
    # write can never create a second won deal or deduct stock twice.
    deal_id = None
    if outcome == "converted" and lead_id:
        claimed = (
            db.table("call_logs").update({"outcome": "converted"})
            .eq("id", call_log_id).eq("tenant_id", tenant_id)
            .or_("outcome.is.null,outcome.neq.converted")
            .execute()
        ).data or []
        if claimed:
            try:
                result = await create_deal(
                    tenant_id, lead_id, sale_lines(wrapup.get("products") or [], wrapup.get("amount_paise")), "call", "won",
                    payment_method="other", notes=notes, created_by=user_id, db=db,
                )
                deal_id = result["deal"]["id"]
            except Exception:
                db.table("call_logs").update({"outcome": log.get("outcome")}).eq("id", call_log_id).eq("tenant_id", tenant_id).execute()
                raise

    log_updates = {
        **log_extra,
        "manual_status": manual_status,
        "outcome": outcome,
        "outcome_reason": wrapup.get("reason") if outcome in ("not_interested", "disqualified") else None,
        "preferred_language": wrapup.get("preferred_language") if outcome == "language_barrier" else None,
        "next_action_at": next_at.isoformat() if next_at else None,
        "feedback_at": now.isoformat(),
    }
    if notes:
        log_updates["notes"] = notes
    if log.get("provider") == "sim_basic":
        log_updates["feedback_source"] = "manual"
        log_updates["status"] = "completed"
    db.table("call_logs").update(log_updates).eq("id", call_log_id).eq("tenant_id", tenant_id).execute()

    summary = {"call_status": None, "next_action_at": log_updates["next_action_at"], "deal_id": deal_id}
    if not lead_id:
        return summary
    rows = (
        db.table("leads").select("segment,phone,ai_enabled,converted_at,assigned_to")
        .eq("id", lead_id).eq("tenant_id", tenant_id).limit(1).execute()
    ).data or []
    if not rows:
        return summary
    lead = rows[0]

    lead_updates: dict = {"call_status": status}
    if outcome == "converted":
        lead_updates["converted_at"] = now.isoformat()
        if notes:
            lead_updates["conversion_notes"] = notes
    if outcome in STOP_ALL_FOLLOW_UPS:
        lead_updates["do_not_call"] = True
    if outcome == "do_not_call" and wrapup.get("stop_messages"):
        lead_updates["opted_out"] = True
    updated = db.table("leads").update(lead_updates).eq("id", lead_id).eq("tenant_id", tenant_id).execute().data or []
    lead_after = {**lead, **(updated[0] if updated else lead_updates)}
    summary["call_status"] = status

    record_stage_event(
        lead_id, from_segment=lead.get("segment"), to_segment=lead_after.get("segment"),
        event_type="converted" if outcome == "converted" else "call_outcome",
        metadata={
            "outcome": outcome, "manual_status": manual_status, "call_status": status,
            "reason": log_updates["outcome_reason"], "preferred_language": log_updates["preferred_language"],
            "deal_id": deal_id,
        },
        tenant_id=tenant_id, db=db,
    )

    tag = f"call_{outcome or manual_status}"
    stop_all = outcome in STOP_ALL_FOLLOW_UPS
    if stop_all:
        cancel_pending_follow_ups(lead_id, reason=f"dnc_{outcome}", db=db)
    else:
        # Re-plans the WhatsApp follow-ups and cancels every other pending reminder for the lead.
        sync_follow_up_jobs(
            lead_id, segment=lead_after.get("segment"), phone=lead_after.get("phone"),
            converted_at=lead_after.get("converted_at"), ai_enabled=lead_after.get("ai_enabled", True),
            reason=tag, tenant_id=tenant_id, db=db,
        )

    linked = log.get("follow_up_job_id")
    if linked:
        db.table("follow_up_jobs").update({
            "status": "canceled" if stop_all else "sent",
            "sent_at": None if stop_all else now.isoformat(),
            "skip_reason": f"dnc_{outcome}" if stop_all else None,
        }).eq("id", linked).eq("tenant_id", tenant_id).execute()

    if next_at:
        db.table("follow_up_jobs").insert({
            "lead_id": lead_id, "tenant_id": tenant_id, "channel": "phone", "cadence": "callback",
            "status": "pending", "scheduled_for": next_at.isoformat(),
            "message_preview": reminder_note(manual_status, outcome, notes),
            "scheduled_by_caller_id": caller_id,
        }).execute()

    if status not in CLOSED_LEAD_STATUSES and not lead.get("assigned_to"):
        maybe_assign_lead(lead_id, tenant_id, lead_after.get("segment"), None, reason=tag)

    if outcome == "language_barrier":
        try:
            raise_reassign_alert(db, tenant_id=tenant_id, call_log_id=call_log_id,
                                 caller_id=log.get("caller_id") or caller_id, language=wrapup["preferred_language"])
        except Exception as e:
            logger.error(f"reassign alert failed for call {call_log_id}: {e}")
    return summary
