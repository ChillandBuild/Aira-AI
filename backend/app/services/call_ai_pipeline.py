"""Recording -> transcript -> summary + evaluation -> score, surviving restarts.

Each recorded call carries its own progress in call_logs.ai_status
(pending -> transcribing -> scoring -> done | failed). The webhook starts the work
straight away as a background task; a scheduler sweep picks up anything a restart
or deploy interrupted, and retries failures up to MAX_ATTEMPTS before showing
"failed" with a manual retry. A conditional update on ai_attempts claims each run,
so the webhook task and the sweep can't both process the same call.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

import httpx

from app.config_dynamic import get_setting
from app.db.supabase import get_supabase
from app.services.audio_format import detect_audio_format, detect_gemini_audio_mime
from app.services.call_scorer import SCORE_MIN_SECONDS, finalize_call_score
from app.services.call_summarizer import DEFAULT_CRITERIA, analyze_call, normalize_criteria, transcribe_call

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
RETRY_AFTER = timedelta(minutes=2)
STUCK_AFTER = timedelta(minutes=15)
SWEEP_BATCH = 20
ACTIVE_STATUSES = ("pending", "transcribing", "scoring")

# Max concurrent call-AI runs, so a whole shift hanging up together doesn't trip the
# provider's rate limit. Extra calls wait their turn.
_CALL_AI_SEMAPHORE = asyncio.Semaphore(5)

_MIN_AUDIO_BYTES = 1024
_DOWNLOAD_DELAYS = (10, 20, 30)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_audio_payload(resp: httpx.Response, body: bytes) -> bool:
    """True when a /v2/play response body is plausibly an audio file.

    TeleCMI returns HTTP 200 with a JSON error body on auth/lookup failure, so the
    response has to be inspected rather than trusted.
    """
    content_type = (resp.headers.get("content-type") or "").lower()
    if "json" in content_type or "html" in content_type or "text/" in content_type:
        return False
    if body.lstrip()[:1] in (b"{", b"["):
        return False
    return len(body) >= _MIN_AUDIO_BYTES


def queue_call_ai(db, call_log_id: str, recording_filename: str) -> None:
    db.table("call_logs").update({
        "recording_filename": recording_filename,
        "ai_status": "pending",
        "ai_attempts": 0,
        "ai_error": None,
        "ai_updated_at": _now(),
    }).eq("id", call_log_id).execute()


def retry_call_ai(db, call_log_id: str, tenant_id: str) -> bool:
    res = (
        db.table("call_logs")
        .update({"ai_status": "pending", "ai_attempts": 0, "ai_error": None, "ai_updated_at": _now()})
        .eq("id", call_log_id)
        .eq("tenant_id", tenant_id)
        .eq("ai_status", "failed")
        .execute()
    )
    return bool(res.data)


def _set_stage(db, call_log_id: str, stage: str) -> None:
    db.table("call_logs").update({"ai_status": stage, "ai_updated_at": _now()}).eq("id", call_log_id).execute()


async def _download_from_telecmi(row: dict, appid_override: str | None) -> bytes:
    from app.services.telecmi_client import build_recording_url

    tenant_id = row.get("tenant_id")
    appid = appid_override or get_setting("telecmi_app_id", tenant_id=tenant_id)
    secret = get_setting("telecmi_secret", tenant_id=tenant_id)
    if not appid or not secret:
        raise RuntimeError("TeleCMI app id/secret not configured, cannot download the recording")
    url = build_recording_url(
        appid=str(appid),
        secret=secret,
        filename=row["recording_filename"],
        base_url=get_setting("telecmi_recording_base_url", tenant_id=tenant_id),
    )
    for attempt, delay in enumerate(_DOWNLOAD_DELAYS, start=1):
        await asyncio.sleep(delay)
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.get(url)
            if resp.status_code == 404:
                logger.info(f"Recording not ready yet (attempt {attempt}) for call {row['id']}")
                continue
            resp.raise_for_status()
            if not is_audio_payload(resp, resp.content):
                logger.warning(
                    f"Recording download returned non-audio (attempt {attempt}) for call {row['id']}: "
                    f"content_type={resp.headers.get('content-type')!r} body={resp.content[:200]!r}"
                )
                continue
            return resp.content
        except httpx.HTTPError as e:
            logger.warning(f"Recording download attempt {attempt} failed for call {row['id']}: {type(e).__name__}")
    raise RuntimeError("recording could not be downloaded from TeleCMI")


async def _load_audio(db, row: dict, appid_override: str | None) -> tuple[bytes, str]:
    """The call's audio and its Gemini mime type; downloads + stores it on first run."""
    if row.get("recording_url"):
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.get(row["recording_url"])
            resp.raise_for_status()
        audio = resp.content
        return audio, detect_gemini_audio_mime(audio, row["recording_url"])

    if not row.get("recording_filename"):
        raise RuntimeError("no recording is attached to this call")
    audio = await _download_from_telecmi(row, appid_override)
    extension, content_type = detect_audio_format(audio, row["recording_filename"])
    storage_path = f"{row['id']}.{extension}"
    db.storage.from_("call-recordings").upload(storage_path, audio, {"content-type": content_type, "upsert": "true"})
    public_url = db.storage.from_("call-recordings").get_public_url(storage_path)
    db.table("call_logs").update({"recording_url": public_url}).eq("id", row["id"]).execute()
    logger.info(f"Recording saved for {row['id']}")
    return audio, detect_gemini_audio_mime(audio, row["recording_filename"])


def _selected_criteria(tenant_id: str | None, db) -> list[str]:
    from app.services.assignment import get_telecalling_config

    if not tenant_id:
        return list(DEFAULT_CRITERIA)
    cfg = get_telecalling_config(tenant_id, db=db)
    return normalize_criteria(cfg.get("score_criteria")) or list(DEFAULT_CRITERIA)


def _claim(db, call_log_id: str) -> dict | None:
    res = (
        db.table("call_logs")
        .select("id,tenant_id,caller_id,lead_id,duration_seconds,recording_url,recording_filename,ai_status,ai_attempts")
        .eq("id", call_log_id)
        .maybe_single()
        .execute()
    )
    row = res.data if res else None
    if not row or row.get("ai_status") not in ACTIVE_STATUSES:
        return None
    attempts = row.get("ai_attempts") or 0
    if attempts >= MAX_ATTEMPTS:
        return None
    claimed = (
        db.table("call_logs")
        .update({"ai_status": "transcribing", "ai_attempts": attempts + 1, "ai_updated_at": _now()})
        .eq("id", call_log_id)
        .eq("ai_attempts", attempts)
        .in_("ai_status", list(ACTIVE_STATUSES))
        .execute()
    )
    if not claimed.data:
        return None
    row["ai_attempts"] = attempts + 1
    return row


async def _process(db, row: dict, appid_override: str | None) -> None:
    from app.services.knowledge_service import get_knowledge_context

    call_log_id = row["id"]
    tenant_id = row.get("tenant_id")
    audio, mime_type = await _load_audio(db, row, appid_override)

    transcript, chunks = await transcribe_call(audio, mime_type, tenant_id=tenant_id)
    if not transcript.strip():
        raise RuntimeError("the transcript came back empty")
    db.table("call_logs").update({"transcript": transcript}).eq("id", call_log_id).execute()
    logger.info(f"Transcript stored for {call_log_id} ({len(transcript)} chars)")

    if (row.get("duration_seconds") or 0) < SCORE_MIN_SECONDS:
        db.table("call_logs").update({"ai_status": "done", "ai_error": None, "ai_updated_at": _now()}).eq("id", call_log_id).execute()
        return

    _set_stage(db, call_log_id, "scoring")
    lead_name = None
    if row.get("lead_id"):
        lead = db.table("leads").select("name").eq("id", row["lead_id"]).maybe_single().execute()
        lead_name = ((lead.data if lead else None) or {}).get("name")
    kb_context = await get_knowledge_context(tenant_id, query=transcript[:1500]) if tenant_id else ""

    summary, evaluation = await analyze_call(
        transcript,
        _selected_criteria(tenant_id, db),
        lead_name=lead_name,
        kb_context=kb_context,
        tenant_id=tenant_id,
        chunks=chunks,
    )
    db.table("call_logs").update({
        "ai_summary": summary,
        "evaluation": evaluation,
        "ai_status": "done",
        "ai_error": None,
        "ai_updated_at": _now(),
    }).eq("id", call_log_id).execute()
    logger.info(f"Call {call_log_id} evaluated: AI average {evaluation.get('ai_average')}")

    if summary.get("next_action") and row.get("lead_id"):
        note_row = {
            "lead_id": row["lead_id"],
            "call_log_id": call_log_id,
            "content": f"AI Summary: {summary['next_action']}",
            "structured": summary,
            "is_pinned": False,
        }
        if tenant_id:
            note_row["tenant_id"] = tenant_id
        db.table("lead_notes").insert(note_row).execute()


async def run_call_ai(call_log_id: str, appid_override: str | None = None) -> None:
    async with _CALL_AI_SEMAPHORE:
        db = get_supabase()
        row = _claim(db, call_log_id)
        if not row:
            return
        try:
            await _process(db, row, appid_override)
        except Exception as e:
            error = f"{type(e).__name__}: {e}"[:500]
            final = row["ai_attempts"] >= MAX_ATTEMPTS
            logger.error(f"Call AI attempt {row['ai_attempts']}/{MAX_ATTEMPTS} failed for {call_log_id}: {error}")
            db.table("call_logs").update({
                "ai_status": "failed" if final else "pending",
                "ai_error": error,
                "ai_updated_at": _now(),
            }).eq("id", call_log_id).execute()
        try:
            finalize_call_score(db, call_log_id)
        except Exception as e:
            logger.error(f"Scoring failed for call {call_log_id}: {e}")


async def sweep_call_ai() -> int:
    """Resume calls a restart interrupted and retry earlier failures. Returns how many ran."""
    db = get_supabase()
    now = datetime.now(timezone.utc)
    due_pending = (
        db.table("call_logs")
        .select("id,ai_attempts")
        .eq("ai_status", "pending")
        .lt("ai_updated_at", (now - RETRY_AFTER).isoformat())
        .order("ai_updated_at")
        .limit(SWEEP_BATCH)
        .execute()
    ).data or []
    stuck = (
        db.table("call_logs")
        .select("id,ai_attempts")
        .in_("ai_status", ["transcribing", "scoring"])
        .lt("ai_updated_at", (now - STUCK_AFTER).isoformat())
        .order("ai_updated_at")
        .limit(SWEEP_BATCH)
        .execute()
    ).data or []

    runnable = []
    for row in due_pending + stuck:
        if (row.get("ai_attempts") or 0) >= MAX_ATTEMPTS:
            db.table("call_logs").update({
                "ai_status": "failed",
                "ai_error": "stopped after the maximum number of attempts",
                "ai_updated_at": _now(),
            }).eq("id", row["id"]).execute()
            finalize_call_score(db, row["id"])
        else:
            runnable.append(row["id"])
    if runnable:
        logger.info(f"Call AI sweep: resuming {len(runnable)} call(s)")
        await asyncio.gather(*(run_call_ai(cid) for cid in runnable))
    return len(runnable)
