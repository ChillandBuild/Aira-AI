import asyncio
import hmac
import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Literal
from uuid import UUID
import httpx
from fastapi import Depends, Query
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response
from pydantic import BaseModel, Field
from app.config_dynamic import get_setting
from app.db.supabase import get_supabase
from app.dependencies.tenant import get_tenant_id, get_tenant_and_role
from app.services.call_scorer import score_from_outcome, recompute_caller_score
from app.services.call_summarizer import transcribe_recording, analyze_call
from app.services.knowledge_service import get_knowledge_context
from app.services.growth import record_stage_event, sync_follow_up_jobs
from app.services.telecmi_client import initiate_click2call
from app.services.voice_router import get_best_voice_number, increment_voice_call_count
from app.services.assignment import get_telecalling_config, record_assignment_event


logger = logging.getLogger(__name__)
router = APIRouter()
public_router = APIRouter()  # No auth — TeleCMI calls these directly

Outcome = Literal["converted", "callback", "not_interested", "no_answer"]
Disposition = Literal["answered", "no_answer", "busy", "switched_off", "followup_required"]

# Map a connection-state disposition to the business outcome that drives scoring/segments.
# "answered" alone implies no business result (caller may set outcome separately), so it
# maps to None — disposition + notes are still recorded, but scoring stays untouched.
_DISPOSITION_TO_OUTCOME: dict[str, str | None] = {
    "answered": None,
    "no_answer": "no_answer",
    "busy": "no_answer",
    "switched_off": "no_answer",
    "followup_required": "callback",
}


class InitiateCall(BaseModel):
    lead_id: UUID | None = None
    phone: str | None = None      # manual dial — provide either lead_id or phone
    caller_id: UUID | None = None
    callback_job_id: UUID | None = None



class OutcomeUpdate(BaseModel):
    outcome: str | None = None
    disposition: Disposition | None = None
    notes: str | None = None
    callback_time: datetime | None = None
    quality_rating: int | None = Field(default=None, ge=1, le=5)


@router.post("/initiate")
async def initiate_call(payload: InitiateCall, ctx: dict = Depends(get_tenant_and_role)):
    tenant_id = ctx["tenant_id"]
    role = ctx.get("role")

    telecmi_secret = get_setting("telecmi_secret", tenant_id=tenant_id)
    if not telecmi_secret:
        raise HTTPException(status_code=400, detail="TeleCMI App Secret not configured. Set it in Settings.")

    if not payload.lead_id and not payload.phone:
        raise HTTPException(status_code=400, detail="Provide either lead_id or phone")

    db = get_supabase()

    matched_lead_id: str | None = None
    matched_lead_name: str | None = None

    if payload.lead_id:
        lead = db.table("leads").select("phone,name,do_not_call").eq("id", str(payload.lead_id)).eq("tenant_id", tenant_id).maybe_single().execute()
        if not lead.data:
            raise HTTPException(status_code=404, detail="Lead not found")
        if lead.data.get("do_not_call"):
            raise HTTPException(status_code=400, detail="Lead is on Do Not Call")
        lead_phone = lead.data["phone"]
        matched_lead_id = str(payload.lead_id)
        matched_lead_name = lead.data.get("name")
    else:
        lead_phone = payload.phone
        # try to find a lead by phone so live notes can be linked
        match = db.table("leads").select("id,name,do_not_call").eq("phone", lead_phone).eq("tenant_id", tenant_id).maybe_single().execute()
        if match and match.data:
            if match.data.get("do_not_call"):
                raise HTTPException(status_code=400, detail="Lead is on Do Not Call")
            matched_lead_id = match.data["id"]
            matched_lead_name = match.data.get("name")
        else:
            # auto-create a minimal lead so notes can always be saved
            try:
                new_lead = db.table("leads").insert({
                    "phone": lead_phone,
                    "source": "manual",
                    "score": 5,
                    "segment": "C",
                    "tenant_id": tenant_id,
                    "call_status": "in_progress",
                }).execute()
                if new_lead.data:
                    matched_lead_id = new_lead.data[0]["id"]
                    matched_lead_name = None
            except Exception as e:
                logger.warning(f"Auto-create lead failed for {lead_phone}: {e}")

    # Owners can call directly without a caller record; telecallers require their phone
    caller_telecmi_agent_id: str | None = None
    if role != "owner":
        caller_phone: str | None = None
        if payload.caller_id:
            caller = db.table("callers").select("phone,telecmi_agent_id").eq("id", str(payload.caller_id)).eq("tenant_id", tenant_id).maybe_single().execute()
            if caller.data:
                caller_phone = caller.data.get("phone")
                caller_telecmi_agent_id = caller.data.get("telecmi_agent_id") or None
        if not caller_phone:
            raise HTTPException(status_code=400, detail="Caller has no phone number configured")
    elif payload.caller_id:
        caller = db.table("callers").select("telecmi_agent_id").eq("id", str(payload.caller_id)).eq("tenant_id", tenant_id).maybe_single().execute()
        if caller.data:
            caller_telecmi_agent_id = caller.data.get("telecmi_agent_id") or None

    best_number = await get_best_voice_number(tenant_id)
    if not best_number:
        raise HTTPException(status_code=400, detail="No active voice numbers in pool")

    log_insert = db.table("call_logs").insert({
        "lead_id": matched_lead_id,
        "caller_id": str(payload.caller_id) if payload.caller_id else None,
        "status": "initiated",
        "tenant_id": tenant_id,
        "follow_up_job_id": str(payload.callback_job_id) if payload.callback_job_id else None,
    }).execute()
    call_log_id = log_insert.data[0]["id"]

    try:
        # TeleCMI click-to-call: rings the caller first, then bridges to the lead
        telecmi_callerid = get_setting("telecmi_callerid", tenant_id=tenant_id) or best_number["number"]
        # Caller's own agent ID takes priority; admin direct calls fall back to global setting
        # Fallback: owner's own caller record agent_id, then global setting
        effective_agent_id = caller_telecmi_agent_id
        if not effective_agent_id:
            owner_member = db.table("tenant_users").select("user_id").eq("tenant_id", tenant_id).eq("role", "owner").maybe_single().execute()
            if owner_member.data:
                owner_caller = db.table("callers").select("telecmi_agent_id").eq("user_id", owner_member.data["user_id"]).eq("tenant_id", tenant_id).maybe_single().execute()
                if owner_caller.data:
                    effective_agent_id = owner_caller.data.get("telecmi_agent_id")
        if not effective_agent_id:
            effective_agent_id = get_setting("telecmi_user_id", tenant_id=tenant_id)
        if not effective_agent_id:
            raise HTTPException(status_code=400, detail="No TeleCMI Agent ID found. Assign one from the Team page.")
        result = await initiate_click2call(
            user_id=effective_agent_id,
            secret=telecmi_secret,
            to=lead_phone,
            callerid=telecmi_callerid,
            extra_params={"call_log_id": call_log_id},
        )
        request_id = result.get("request_id", "")
    except Exception as e:
        err_msg = str(e).replace(telecmi_secret, "***") if telecmi_secret else str(e)
        logger.error(f"TeleCMI call failed: {err_msg}")
        db.table("call_logs").update({"status": "failed"}).eq("id", call_log_id).execute()
        raise HTTPException(status_code=502, detail=f"TeleCMI call failed: {err_msg}")

    db.table("call_logs").update({"call_sid": request_id}).eq("id", call_log_id).execute()
    await increment_voice_call_count(best_number["id"])
    return {
        "call_log_id": call_log_id,
        "call_sid": request_id,
        "status": "initiated",
        "lead_id": matched_lead_id,
        "lead_name": matched_lead_name,
    }


# ── TeleCMI CDR Webhook ──────────────────────────────────────────────
# TeleCMI sends JSON CDR to this endpoint after a call completes.
# Configure this URL in your TeleCMI dashboard → SETTINGS → WEBHOOKS.
# URL: https://YOUR-RENDER-URL.onrender.com/api/v1/calls/telecmi-cdr

_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


def _verify_telecmi_webhook_secret(request: Request, tenant_id: str | None = None) -> bool:
    configured_secret = get_setting("telecmi_webhook_secret", tenant_id=tenant_id)
    received_secret = request.query_params.get("webhook_secret")
    if not configured_secret or not received_secret:
        raise HTTPException(status_code=403, detail="Invalid webhook secret")
    if not hmac.compare_digest(received_secret, configured_secret):
        raise HTTPException(status_code=403, detail="Invalid webhook secret")
    return True


def _extract_call_log_id(cdr: dict) -> str | None:
    """Pull a usable call_log_id from a TeleCMI CDR `custom` field.

    TeleCMI sends the literal string `"none"` (lowercase) when no custom value
    was attached at dial time — treat that like a missing field. Also reject
    our own marker `"aira_ai_call"` and anything that isn't a UUID, to avoid
    sending invalid UUIDs to PostgREST (which returns 400 and crashes the
    handler via maybe_single).
    """
    raw = cdr.get("custom")
    if not raw or not isinstance(raw, str):
        return None
    val = raw.strip()
    if val.lower() in {"", "none", "null", "aira_ai_call"}:
        return None
    if not _UUID_RE.match(val):
        return None
    return val


@public_router.post("/telecmi-cdr")
async def telecmi_cdr(request: Request, background_tasks: BackgroundTasks):
    """Receive Call Detail Record (CDR) from TeleCMI."""
    try:
        cdr = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    tenant_id = request.query_params.get("tenant_id")
    if not tenant_id:
        call_log_id = _extract_call_log_id(cdr)
        if call_log_id:
            db = get_supabase()
            call_log = db.table("call_logs").select("tenant_id").eq("id", call_log_id).maybe_single().execute()
            if call_log and call_log.data:
                tenant_id = call_log.data.get("tenant_id")

    _verify_telecmi_webhook_secret(request, tenant_id=tenant_id)
    logger.info(f"TeleCMI CDR received: {cdr}")

    status = cdr.get("status")
    call_log_id = _extract_call_log_id(cdr)

    # TeleCMI sends separate CDRs for user_missed / user_answered (agent leg).
    # We only process outbound CDRs with a call_log_id embedded in custom.
    if status == "user_missed":
        logger.info("TeleCMI CDR: agent missed the call, updating call log")
        if call_log_id:
            db = get_supabase()
            db.table("call_logs").update({
                "status": "missed",
                "outcome": "no_answer",
            }).eq("id", call_log_id).execute()
        return {"ok": True}

    if not call_log_id:
        logger.warning(f"TeleCMI CDR missing/invalid call_log_id, ignoring: {cdr}")
        return {"ok": True}

    db = get_supabase()

    log_row = (
        db.table("call_logs")
        .select("id,caller_id,lead_id,tenant_id")
        .eq("id", call_log_id)
        .maybe_single()
        .execute()
    )
    if not log_row or not log_row.data:
        logger.warning(f"TeleCMI CDR: no call_log found for id={call_log_id}")
        return {"ok": True}

    call_log_id = log_row.data["id"]

    # If call_log has no lead linked, try to match/create one from the dialed number
    if not log_row.data.get("lead_id"):
        dialed = cdr.get("to") or cdr.get("customer_number") or cdr.get("did")
        tenant_id = log_row.data.get("tenant_id")
        if dialed and tenant_id:
            match = db.table("leads").select("id").eq("phone", dialed).eq("tenant_id", tenant_id).maybe_single().execute()
            if match and match.data:
                resolved_lead_id = match.data["id"]
            else:
                try:
                    new_lead = db.table("leads").insert({
                        "phone": dialed, "source": "manual", "score": 5,
                        "segment": "C", "tenant_id": tenant_id,
                        "call_status": "in_progress",
                    }).execute()
                    resolved_lead_id = new_lead.data[0]["id"] if new_lead.data else None
                except Exception as e:
                    logger.warning(f"CDR: auto-create lead failed for {dialed}: {e}")
                    resolved_lead_id = None
            if resolved_lead_id:
                db.table("call_logs").update({"lead_id": resolved_lead_id}).eq("id", call_log_id).execute()
                log_row.data["lead_id"] = resolved_lead_id
                logger.info(f"CDR: linked call {call_log_id} to lead {resolved_lead_id} via phone {dialed}")

    updates: dict = {}

    # TeleCMI final CDR statuses: "answered", "missed", "user_missed"
    if status == "answered":
        updates["status"] = "completed"
        answered_sec = cdr.get("answeredsec") or cdr.get("bilsec")
        if answered_sec is not None:
            try:
                updates["duration_seconds"] = int(answered_sec)
            except (ValueError, TypeError):
                pass
    elif status in ("missed", "no_answer"):
        updates["status"] = "no_answer"
        updates["outcome"] = "no_answer"
    else:
        updates["status"] = "failed"

    # Handle recording if present
    # TeleCMI recording URL: https://piopiy.telecmi.com/v1/play?appid=<appid>&token=<secret>&file=<filename>
    recording_filename = cdr.get("filename")
    if recording_filename:
        appid = cdr.get("appid")
        secret = get_setting("telecmi_secret", tenant_id=log_row.data.get("tenant_id"))
        if appid and secret:
            # This play URL embeds the TeleCMI secret token, so it must NOT be
            # persisted. Pass it only to the background task, which downloads the
            # file and re-stores it in Supabase Storage, then writes the Supabase
            # URL to recording_url. On failure recording_url stays null rather
            # than leaking the secret into the DB / frontend.
            full_url = (
                f"https://piopiy.telecmi.com/v1/play"
                f"?appid={appid}&token={secret}&file={recording_filename}"
            )
            background_tasks.add_task(_process_telecmi_recording, call_log_id, full_url)

    if updates:
        db.table("call_logs").update(updates).eq("id", call_log_id).execute()

    # Recompute caller score on terminal statuses
    if updates.get("status") in ("completed", "no_answer"):
        row = log_row.data
        score = score_from_outcome(updates.get("outcome"), updates.get("duration_seconds"))
        db.table("call_logs").update({"score": score}).eq("id", call_log_id).execute()
        if row.get("caller_id"):
            recompute_caller_score(row["caller_id"], db)
            
        # Target achievement milestone check
        if updates.get("status") == "completed" and row.get("caller_id") and row.get("tenant_id"):
            try:
                from datetime import datetime, timezone
                today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
                achieved_res = (
                    db.table("call_logs")
                    .select("id", count="exact")
                    .eq("caller_id", row["caller_id"])
                    .eq("tenant_id", row["tenant_id"])
                    .eq("status", "completed")
                    .gte("created_at", today_start)
                    .execute()
                )
                achieved = achieved_res.count or 0
                
                from app.services.assignment import get_telecalling_config
                cfg = get_telecalling_config(row["tenant_id"])
                targets = cfg.get("targets") or {}
                target = targets.get(str(row["caller_id"])) or targets.get(row["caller_id"]) or targets.get("daily_calls", 50)
                
                if achieved == target:
                    caller_res = db.table("callers").select("user_id, name").eq("id", row["caller_id"]).maybe_single().execute()
                    if caller_res.data and caller_res.data.get("user_id"):
                        from app.services.notify import notify_user
                        notify_user(
                            row["tenant_id"],
                            caller_res.data["user_id"],
                            "milestone_achieved",
                            "Milestone Achieved! 🎉",
                            f"Congratulations {caller_res.data['name']}! You have achieved your daily target of {target} calls today.",
                            db=db,
                        )
            except Exception as milestone_err:
                logger.warning(f"Failed to verify milestone target completed: {milestone_err}")

    return {"ok": True}


# ── TeleCMI Live Events Webhook ───────────────────────────────────────
# Optional: receive real-time call status events (started, answered, hangup)

@public_router.post("/telecmi-events")
async def telecmi_live_events(request: Request):
    """Receive live call events from TeleCMI (optional — for real-time UI updates)."""
    try:
        event = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    tenant_id = request.query_params.get("tenant_id")
    if not tenant_id:
        request_id = event.get("request_id")
        if request_id:
            db = get_supabase()
            call_log = db.table("call_logs").select("tenant_id").eq("call_sid", request_id).maybe_single().execute()
            if call_log and call_log.data:
                tenant_id = call_log.data.get("tenant_id")

    _verify_telecmi_webhook_secret(request, tenant_id=tenant_id)
    status = event.get("status")
    request_id = event.get("request_id")
    logger.info(f"TeleCMI event: status={status}, request_id={request_id}")
    
    if request_id:
        db = get_supabase()
        log_status = None
        if status in ("dial", "started", "initiated"):
            log_status = "initiated"
        elif status in ("answered", "in_progress"):
            log_status = "in_progress"
        elif status in ("hangup", "ended", "completed"):
            log_status = "completed"
            
        if log_status:
            db.table("call_logs").update({"status": log_status}).eq("call_sid", request_id).execute()
            
    return {"ok": True}


# ── Recording Processing ─────────────────────────────────────────────

# Max concurrent Groq (Whisper + LLM) requests — prevents rate-limit failures
# when many calls end at the same time (shift end, break, etc.)
_GROQ_SEMAPHORE = asyncio.Semaphore(5)


async def _process_telecmi_recording(call_log_id: str, recording_url: str) -> None:
    """Download TeleCMI recording and run AI summarization."""
    async with _GROQ_SEMAPHORE:
        db = get_supabase()

        for attempt in range(1, 4):
            delay = 10 * attempt
            logger.info(f"Recording download attempt {attempt}/3 for {call_log_id} — waiting {delay}s")
            await asyncio.sleep(delay)
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    resp = await client.get(recording_url)
                    if resp.status_code == 404:
                        logger.warning(f"Recording not ready yet (attempt {attempt}): {recording_url}")
                        continue
                    resp.raise_for_status()
                    audio_bytes = resp.content

                storage_path = f"{call_log_id}.mp3"
                db.storage.from_("call-recordings").upload(
                    storage_path,
                    audio_bytes,
                    {"content-type": "audio/mpeg", "upsert": "true"},
                )
                public_url = db.storage.from_("call-recordings").get_public_url(storage_path)
                db.table("call_logs").update({"recording_url": public_url}).eq("id", call_log_id).execute()
                logger.info(f"Recording saved for {call_log_id}: {public_url}")

                # Run AI summarization
                await _run_summarization(call_log_id, public_url)
                return

            except Exception as e:
                logger.error(f"Recording attempt {attempt} failed for {call_log_id}: {e}")

        logger.error(f"All recording attempts failed for {call_log_id}")


_SKIP_OUTCOMES = {"no_answer", "voicemail"}
_TRANSCRIBE_MIN_DURATION = 30
_EVAL_MIN_DURATION = 60
_EVAL_DAILY_CAP_DEFAULT = 50
_NEW_CALLER_DAYS = 14


def _should_evaluate(
    duration: int | None,
    caller_id: str | None,
    tenant_id: str | None,
    db,
) -> bool:
    """Layer 3 gate: decide whether a call gets full AI evaluation."""
    dur = duration or 0

    # New callers (< 14 days) bypass the duration gate
    is_new_caller = False
    if caller_id:
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=_NEW_CALLER_DAYS)).isoformat()
            cr = (
                db.table("callers")
                .select("id")
                .eq("id", caller_id)
                .gte("created_at", cutoff)
                .maybe_single()
                .execute()
            )
            is_new_caller = bool(cr and cr.data)
        except Exception:
            pass

    if not is_new_caller and dur < _EVAL_MIN_DURATION:
        return False

    # Per-tenant daily cap
    if tenant_id:
        try:
            from app.services.assignment import get_telecalling_config
            cfg = get_telecalling_config(tenant_id)
            cap = cfg.get("eval_daily_cap", _EVAL_DAILY_CAP_DEFAULT)

            today_start = datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            ).isoformat()
            count_res = (
                db.table("call_logs")
                .select("id", count="exact")
                .eq("tenant_id", tenant_id)
                .not_.is_("evaluation", "null")
                .gte("created_at", today_start)
                .execute()
            )
            if (count_res.count or 0) >= cap:
                logger.info(f"Eval daily cap ({cap}) reached for tenant {tenant_id}")
                return False
        except Exception as e:
            logger.warning(f"Eval cap check failed: {e}")

    return True


async def _run_summarization(call_log_id: str, recording_url: str, force: bool = False) -> None:
    try:
        db = get_supabase()

        call_row = (
            db.table("call_logs")
            .select("outcome,duration_seconds,lead_id,caller_id,tenant_id")
            .eq("id", call_log_id)
            .maybe_single()
            .execute()
        )
        call_data = (call_row.data or {})
        outcome = call_data.get("outcome")
        duration = call_data.get("duration_seconds") or 0
        tenant_id = call_data.get("tenant_id")
        caller_id = call_data.get("caller_id")
        lead_id = call_data.get("lead_id")

        # ── Layer 2: Transcription gate ──────────────────────────────────
        if not force and outcome in _SKIP_OUTCOMES:
            logger.info(f"Skipping transcription for {call_log_id}: outcome={outcome}")
            return

        if not force and duration < _TRANSCRIBE_MIN_DURATION:
            logger.info(f"Skipping transcription for {call_log_id}: duration={duration}s < {_TRANSCRIBE_MIN_DURATION}s")
            return

        transcript = await transcribe_recording(recording_url, tenant_id=tenant_id)
        if not transcript:
            return

        db.table("call_logs").update({"transcript": transcript}).eq("id", call_log_id).execute()
        logger.info(f"Transcript stored for {call_log_id} ({len(transcript)} chars)")

        # ── Layer 3: Evaluation gate ─────────────────────────────────────
        if not force and not _should_evaluate(duration, caller_id, tenant_id, db):
            logger.info(f"Skipping evaluation for {call_log_id}: gated (duration={duration}s)")
            return

        lead_name: str | None = None
        if lead_id:
            lead_row = db.table("leads").select("name").eq("id", lead_id).maybe_single().execute()
            lead_name = (lead_row.data or {}).get("name")

        kb_context = ""
        if tenant_id:
            kb_context = await get_knowledge_context(tenant_id, query=transcript[:1500])

        summary, evaluation = await analyze_call(
            transcript,
            lead_name=lead_name,
            outcome=outcome,
            kb_context=kb_context,
            tenant_id=tenant_id,
        )

        updates: dict = {}
        if summary:
            updates["ai_summary"] = summary
        if evaluation:
            updates["evaluation"] = evaluation
            logger.info(f"Call evaluation stored for {call_log_id}: score={evaluation.get('overall_score')}")

        if updates:
            db.table("call_logs").update(updates).eq("id", call_log_id).execute()

        if summary.get("next_action") and lead_id:
            note_row = {
                "lead_id": lead_id,
                "call_log_id": call_log_id,
                "content": f"AI Summary: {summary.get('next_action', '')}",
                "structured": summary,
                "is_pinned": False,
            }
            if tenant_id:
                note_row["tenant_id"] = tenant_id
            db.table("lead_notes").insert(note_row).execute()

        if caller_id and evaluation:
            recompute_caller_score(caller_id, db)

        logger.info(f"Summarization complete for {call_log_id}")
    except Exception as e:
        logger.error(f"Summarization failed for {call_log_id}: {e}")


# ── Outcome & Other Endpoints (unchanged) ────────────────────────────

@router.patch("/{call_log_id}/outcome")
async def set_outcome(call_log_id: str, payload: OutcomeUpdate, ctx: dict = Depends(get_tenant_and_role)):
    db = get_supabase()
    log = (
        db.table("call_logs")
        .select("caller_id,duration_seconds,lead_id,follow_up_job_id")
        .eq("id", call_log_id)
        .eq("tenant_id", ctx["tenant_id"])
        .maybe_single()
        .execute()
    )
    if not log.data:
        raise HTTPException(status_code=404, detail="Call log not found")

    if not payload.outcome and not payload.disposition:
        raise HTTPException(status_code=400, detail="Provide an outcome or a disposition")

    if payload.outcome not in ("converted", "callback", "not_interested", "no_answer", "do_not_call", "do_not_contact", "in_progress", None):
        raise HTTPException(status_code=400, detail="Invalid outcome value")

    # Intercept DNC outcomes to handle them as lead-level actions
    dnc_outcome = None
    if payload.outcome in ("do_not_call", "do_not_contact"):
        dnc_outcome = payload.outcome
        payload.outcome = None
        payload.disposition = "answered"

    # "in_progress" is a call_status, not a call_logs.outcome (CHECK-constrained) —
    # record it as an "answered" disposition with no business outcome.
    in_progress = payload.outcome == "in_progress"
    if in_progress:
        payload.outcome = None
        payload.disposition = "answered"

    # A disposition implies a business outcome for scoring; an explicit outcome wins.
    effective_outcome = payload.outcome or _DISPOSITION_TO_OUTCOME.get(payload.disposition or "")

    log_updates: dict = {}
    if payload.disposition is not None:
        log_updates["disposition"] = payload.disposition
    if payload.notes is not None and payload.notes.strip():
        log_updates["notes"] = payload.notes.strip()
    if payload.quality_rating is not None:
        log_updates["quality_rating"] = payload.quality_rating
    score = None
    if effective_outcome is not None:
        score = score_from_outcome(effective_outcome, log.data.get("duration_seconds"))
        log_updates["outcome"] = effective_outcome
        log_updates["score"] = score
    if log_updates:
        db.table("call_logs").update(log_updates).eq("id", call_log_id).eq("tenant_id", ctx["tenant_id"]).execute()

    new_caller_score = None
    if effective_outcome is not None and log.data.get("caller_id"):
        new_caller_score = recompute_caller_score(log.data["caller_id"], db)

    lead_id = log.data.get("lead_id")
    if lead_id and (effective_outcome is not None or dnc_outcome is not None or in_progress):
        lead = (
            db.table("leads")
            .select("segment,phone,ai_enabled,converted_at,tenant_id,assigned_to")
            .eq("id", str(lead_id))
            .maybe_single()
            .execute()
        )
        lead_data = lead.data or {}
        if lead_data:
            lead_updates: dict = {}
            event_type = "call_outcome"
            
            if dnc_outcome == "do_not_call":
                lead_updates["do_not_call"] = True
                lead_updates["call_status"] = "dnc"
            elif dnc_outcome == "do_not_contact":
                lead_updates["do_not_call"] = True
                lead_updates["opted_out"] = True
                lead_updates["call_status"] = "dnc"
            elif in_progress:
                lead_updates["call_status"] = "in_progress"
            elif effective_outcome == "converted":
                lead_updates["call_status"] = "converted"
                lead_updates["converted_at"] = datetime.now(timezone.utc).isoformat()
                event_type = "converted"
            elif effective_outcome == "callback":
                lead_updates["call_status"] = "callback"
            elif effective_outcome == "not_interested":
                lead_updates["call_status"] = "not_interested"
            elif effective_outcome == "no_answer":
                # count this lead's no-answer/missed/failed calls in call_logs
                cfg = get_telecalling_config(ctx["tenant_id"])
                max_attempts = cfg.get("max_call_attempts", 4)
                
                # Fetch all logs for this lead to count attempts
                logs_res = db.table("call_logs").select("id, status, outcome").eq("lead_id", str(lead_id)).eq("tenant_id", ctx["tenant_id"]).execute()
                logs = logs_res.data or []
                
                no_answer_count = 0
                for lg in logs:
                    if lg["id"] == call_log_id:
                        # This is the current call, count it as no_answer since effective_outcome == "no_answer"
                        no_answer_count += 1
                    elif lg.get("status") in ("no_answer", "missed", "failed") or lg.get("outcome") == "no_answer":
                        no_answer_count += 1
                
                if no_answer_count >= max_attempts:
                    lead_updates["call_status"] = "unreachable"
                else:
                    lead_updates["call_status"] = "in_progress"
            else:
                # Any other answered-with-no-business-outcome (e.g. None or anything else)
                lead_updates["call_status"] = "in_progress"

            if lead_updates:
                updated_lead = db.table("leads").update(lead_updates).eq("id", str(lead_id)).eq("tenant_id", ctx["tenant_id"]).execute()
                if updated_lead.data:
                    lead_data = updated_lead.data[0]

            record_stage_event(
                str(lead_id),
                from_segment=lead.data.get("segment"),
                to_segment=lead_data.get("segment"),
                event_type=event_type,
                metadata={
                    "outcome": dnc_outcome or ("in_progress" if in_progress else effective_outcome),
                    "disposition": payload.disposition,
                    "call_status": lead_updates.get("call_status"),
                },
                tenant_id=lead_data.get("tenant_id"),
                db=db,
            )

            outcome_reason = "in_progress" if in_progress else effective_outcome

            if dnc_outcome is not None:
                # Explicitly cancel all pending follow-up jobs
                db.table("follow_up_jobs").update({
                    "status": "canceled",
                    "skip_reason": f"dnc_{dnc_outcome}",
                }).eq("lead_id", str(lead_id)).eq("status", "pending").execute()
            else:
                sync_follow_up_jobs(
                    str(lead_id),
                    segment=lead_data.get("segment"),
                    phone=lead_data.get("phone"),
                    converted_at=lead_data.get("converted_at"),
                    ai_enabled=lead_data.get("ai_enabled", True),
                    reason=f"call_{outcome_reason}",
                    tenant_id=lead_data.get("tenant_id"),
                    db=db,
                )

            if (
                effective_outcome not in ("converted",)
                and dnc_outcome is None
                and lead_updates.get("call_status") != "unreachable"
                and not lead_data.get("assigned_to")
            ):
                from app.services.assignment import maybe_assign_lead
                maybe_assign_lead(
                    str(lead_id), ctx["tenant_id"],
                    lead_data.get("segment"), None,
                    reason=f"call_{outcome_reason}",
                )

            linked_job_id = log.data.get("follow_up_job_id")
            if effective_outcome == "callback":
                target_time = (payload.callback_time or (datetime.now(timezone.utc) + timedelta(days=1))).isoformat()
                target_job_id = linked_job_id
                if not target_job_id:
                    job = (
                        db.table("follow_up_jobs")
                        .select("id")
                        .eq("lead_id", str(lead_id))
                        .eq("status", "pending")
                        .order("scheduled_for")
                        .limit(1)
                        .execute()
                    )
                    target_job_id = job.data[0]["id"] if job.data else None
                if target_job_id:
                    db.table("follow_up_jobs").update({
                        "scheduled_for": target_time,
                    }).eq("id", target_job_id).eq("tenant_id", ctx["tenant_id"]).execute()
            elif (effective_outcome is not None or dnc_outcome is not None) and linked_job_id:
                db.table("follow_up_jobs").update({
                    "status": "sent" if dnc_outcome is None else "canceled",
                    "sent_at": datetime.now(timezone.utc).isoformat() if dnc_outcome is None else None,
                    "skip_reason": f"dnc_{dnc_outcome}" if dnc_outcome is not None else None,
                }).eq("id", linked_job_id).eq("tenant_id", ctx["tenant_id"]).execute()

    return {
        "call_log_id": call_log_id,
        "outcome": effective_outcome,
        "disposition": payload.disposition,
        "score": score,
        "caller_overall_score": new_caller_score,
    }


@router.get("/stats-today")
async def stats_today(ctx: dict = Depends(get_tenant_and_role)):
    from datetime import datetime, timezone
    db = get_supabase()
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    result = db.table("call_logs").select("id,outcome").eq("tenant_id", ctx["tenant_id"]).gte("created_at", today).execute()
    logs = result.data or []
    return {
        "calls_today": len(logs),
        "conversions_today": sum(1 for l in logs if l.get("outcome") == "converted"),
    }


@router.get("/recent-by-leads")
async def recent_by_leads(lead_ids: str = Query(..., description="Comma-separated lead UUIDs, max 50"), ctx: dict = Depends(get_tenant_and_role)):
    ids = [i.strip() for i in lead_ids.split(",") if i.strip()][:50]
    if not ids:
        return {}
    db = get_supabase()
    rows = (
        db.table("call_logs")
        .select("lead_id,created_at")
        .in_("lead_id", ids)
        .eq("tenant_id", ctx["tenant_id"])
        .order("created_at", desc=True)
        .execute()
    )
    seen: dict[str, str] = {}
    for row in rows.data or []:
        lid = row["lead_id"]
        if lid not in seen:
            seen[lid] = row["created_at"]
    return seen


@router.post("/backfill-summaries")
async def backfill_summaries(background_tasks: BackgroundTasks, limit: int = Query(10, ge=1, le=50), ctx: dict = Depends(get_tenant_and_role)):
    """Re-run summarization on call logs that have recording_url but no ai_summary."""
    db = get_supabase()
    rows = (
        db.table("call_logs")
        .select("id,recording_url")
        .eq("tenant_id", ctx["tenant_id"])
        .not_.is_("recording_url", "null")
        .is_("ai_summary", "null")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    ).data or []

    for row in rows:
        background_tasks.add_task(_run_summarization, row["id"], row["recording_url"])

    return {"queued": len(rows)}


@router.post("/{call_log_id}/generate-summary")
async def generate_summary(call_log_id: str, ctx: dict = Depends(get_tenant_and_role)):
    """On-demand AI summary (re)generation from a call's recording."""
    db = get_supabase()
    log = (
        db.table("call_logs")
        .select("recording_url")
        .eq("id", call_log_id)
        .eq("tenant_id", ctx["tenant_id"])
        .maybe_single()
        .execute()
    )
    if not log.data:
        raise HTTPException(status_code=404, detail="Call log not found")
    if not log.data.get("recording_url"):
        raise HTTPException(status_code=400, detail="No recording available for this call")

    await _run_summarization(call_log_id, log.data["recording_url"], force=True)

    result = (
        db.table("call_logs")
        .select("*")
        .eq("id", call_log_id)
        .eq("tenant_id", ctx["tenant_id"])
        .maybe_single()
        .execute()
    )
    return result.data


@router.get("/next-lead")
async def next_lead(
    caller_id: UUID | None = Query(None),
    ctx: dict = Depends(get_tenant_and_role)
):
    tenant_id = ctx["tenant_id"]
    resolved_caller_id = str(caller_id) if caller_id else ctx.get("caller_id")
    if not resolved_caller_id:
        raise HTTPException(status_code=400, detail="caller_id is required")

    db = get_supabase()

    # 1. Fetch telecalling config segments
    cfg = get_telecalling_config(tenant_id)
    if not cfg.get("enabled"):
        raise HTTPException(status_code=404, detail="Telecalling is not enabled")
    segments = cfg.get("segments", ["A"])

    # 2. Pull unassigned hot leads in telecalling_config.segments (default ['A']), not D, not converted, sorted by score desc.
    unassigned_res = (
        db.table("leads")
        .select("*")
        .eq("tenant_id", tenant_id)
        .is_("assigned_to", "null")
        .in_("segment", segments)
        .neq("segment", "D")
        .is_("converted_at", "null")
        .is_("deleted_at", "null")
        .neq("do_not_call", True)
        .neq("call_status", "converted")
        .neq("call_status", "not_interested")
        .neq("call_status", "dnc")
        .neq("call_status", "unreachable")
        .order("score", desc=True)
        .limit(5)
        .execute()
    )

    if unassigned_res.data:
        caller_name = None
        caller_res = db.table("callers").select("name").eq("id", resolved_caller_id).eq("tenant_id", tenant_id).maybe_single().execute()
        if caller_res and caller_res.data:
            caller_name = caller_res.data.get("name")

        # Atomic claim: only assign if the lead is STILL unassigned. Guards
        # against two callers pulling the same lead at the same instant — the
        # loser's update matches 0 rows, so we try the next candidate.
        for lead in unassigned_res.data:
            claim = (
                db.table("leads")
                .update({
                    "assigned_to": resolved_caller_id,
                    "assigned_at": datetime.now(timezone.utc).isoformat(),
                })
                .eq("id", lead["id"])
                .eq("tenant_id", tenant_id)
                .is_("assigned_to", "null")
                .execute()
            )
            if claim.data:
                record_assignment_event(
                    lead_id=lead["id"],
                    tenant_id=tenant_id,
                    segment=lead.get("segment"),
                    caller_id=resolved_caller_id,
                    caller_name=caller_name,
                    reason="call_next",
                    method="pull",
                    score=lead.get("score"),
                    matched_segments=segments,
                    db=db,
                )
                return {**claim.data[0], "_source": "pool"}

    # 3. Fall back to caller's own assigned leads, sorted by least-recently-called
    assigned_res = (
        db.table("leads")
        .select("*")
        .eq("tenant_id", tenant_id)
        .eq("assigned_to", resolved_caller_id)
        .neq("segment", "D")
        .is_("converted_at", "null")
        .is_("deleted_at", "null")
        .neq("do_not_call", True)
        .neq("call_status", "converted")
        .neq("call_status", "dnc")
        .neq("call_status", "unreachable")
        .execute()
    )

    leads_list = assigned_res.data or []
    if not leads_list:
        raise HTTPException(status_code=404, detail="No leads in pool or queue")

    lead_ids = [lead["id"] for lead in leads_list]
    logs_res = (
        db.table("call_logs")
        .select("lead_id, created_at")
        .eq("tenant_id", tenant_id)
        .in_("lead_id", lead_ids)
        .order("created_at", desc=True)
        .execute()
    )

    last_call_map = {}
    for log in (logs_res.data or []):
        lid = log["lead_id"]
        if lid not in last_call_map:
            last_call_map[lid] = log["created_at"]

    def sort_key(lead):
        last_call_time = last_call_map.get(lead["id"])
        if last_call_time is None:
            return (0, "")
        return (1, last_call_time)

    leads_list.sort(key=sort_key)
    return {**leads_list[0], "_source": "queue"}


@router.get("/assignment-mode")
async def get_assignment_mode(ctx: dict = Depends(get_tenant_and_role)):
    cfg = get_telecalling_config(ctx["tenant_id"])
    return {
        "mode": cfg.get("assignment_mode", "push"),
        "enabled": cfg.get("enabled", False),
    }


@router.get("/pending-wrapups")
async def get_pending_wrapups(ctx: dict = Depends(get_tenant_and_role)):
    tenant_id = ctx["tenant_id"]
    caller_id = ctx.get("caller_id")
    db = get_supabase()

    q = (
        db.table("call_logs")
        .select("*, leads(name, phone)")
        .eq("tenant_id", tenant_id)
        .eq("status", "completed")
        .is_("outcome", "null")
        .is_("disposition", "null")
    )
    if caller_id:
        q = q.eq("caller_id", caller_id)

    result = q.execute()
    return result.data or []


@router.get("/{call_log_id}")
async def get_call_log(call_log_id: UUID, ctx: dict = Depends(get_tenant_and_role)):
    db = get_supabase()
    result = (
        db.table("call_logs")
        .select("*")
        .eq("id", str(call_log_id))
        .eq("tenant_id", ctx["tenant_id"])
        .maybe_single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Call log not found")
    return result.data


@router.delete("/{call_log_id}")
async def delete_call_log(call_log_id: str, ctx: dict = Depends(get_tenant_and_role)):
    db = get_supabase()
    result = db.table("call_logs").delete().eq("id", call_log_id).eq("tenant_id", ctx["tenant_id"]).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Call log not found")
    return {"deleted": True}
