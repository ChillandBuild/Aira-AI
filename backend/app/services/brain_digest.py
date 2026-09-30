"""Aira Brain weekly digest: one dashboard notification per tenant owner with how many things
are waiting and the top questions Aira could not answer. Same shape as
call_alerts.send_morning_summaries: per-tenant, skips quiet tenants, one failure never stops
the rest. Reads stored data only (no model call, no gather()). Dashboard push only, no WhatsApp."""
import logging
from datetime import datetime, timedelta, timezone

from app.services.brain import handovers, waiting
from app.services.notify import notify_user

logger = logging.getLogger(__name__)

DIGEST_TYPE = "brain_digest"
DIGEST_TITLE = "Aira Brain weekly digest"
DIGEST_URL = "/dashboard/brain"
LOOKBACK_DAYS = 7
TOP_QUESTIONS = 3
QUESTION_PREVIEW_CHARS = 80


def owner_user_ids(db, tenant_id: str) -> list[str]:
    rows = db.table("tenant_users").select("user_id").eq("tenant_id", tenant_id).eq("role", "owner").execute()
    return [r["user_id"] for r in (rows.data or []) if r.get("user_id")]


def _preview(question: str) -> str:
    text = " ".join(question.split())
    if len(text) <= QUESTION_PREVIEW_CHARS:
        return text
    return text[:QUESTION_PREVIEW_CHARS - 3].rstrip() + "..."


def top_unanswered_questions(db, tenant_id: str, since_iso: str) -> list[str]:
    """Newest knowledge-gap handover questions since since_iso, de-duplicated, at most TOP_QUESTIONS."""
    seen: set[str] = set()
    questions: list[str] = []
    for row in handovers.recent_handovers(db, tenant_id, since_iso):
        question = row.get("likely_question")
        if row.get("kind") != handovers.KIND_KNOWLEDGE_GAP or not question:
            continue
        preview = _preview(question)
        key = preview.lower()
        if key in seen:
            continue
        seen.add(key)
        questions.append(preview)
        if len(questions) == TOP_QUESTIONS:
            break
    return questions


def build_digest_message(waiting_count: int, questions: list[str]) -> str | None:
    """None when there is nothing to say (an empty week sends nothing)."""
    if waiting_count <= 0 and not questions:
        return None
    if waiting_count > 0:
        noun = "thing needs" if waiting_count == 1 else "things need"
        lead = f"Aira Brain: {waiting_count} {noun} you."
    else:
        lead = "Aira Brain: nothing is waiting on you."
    if not questions:
        return lead
    label = "Top question" if len(questions) == 1 else "Top questions"
    quoted = "; ".join(f"'{q}'" for q in questions)
    return f"{lead} {label} Aira couldn't answer: {quoted}"


def _all_tenant_ids(db) -> list[str]:
    rows = db.table("tenants").select("id").execute().data or []
    return [r["id"] for r in rows if r.get("id")]


def send_weekly_digests(db, now: datetime | None = None) -> int:
    """Send this week's digest to the owners of every tenant that has something to say.
    Returns the number of notifications sent."""
    now = now or datetime.now(timezone.utc)
    since_iso = (now - timedelta(days=LOOKBACK_DAYS)).isoformat()
    sent = 0
    for tenant_id in _all_tenant_ids(db):
        try:
            waiting_count = waiting.waiting_summary(db, tenant_id)["count"]
            questions = top_unanswered_questions(db, tenant_id, since_iso)
            message = build_digest_message(waiting_count, questions)
            if message is None:
                continue
            for user_id in owner_user_ids(db, tenant_id):
                notify_user(tenant_id, user_id, DIGEST_TYPE, DIGEST_TITLE, message, db=db, push_url=DIGEST_URL)
                sent += 1
        except Exception as e:
            logger.error(f"Brain digest failed for tenant {tenant_id}: {e}")
    return sent
