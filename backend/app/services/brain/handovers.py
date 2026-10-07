"""Why customers reached a human: chat_handovers rows classified by reason, each with the
customer's likely message.

The likely message is the latest inbound message for the lead at or before opened_at.
chat_handovers stores no message, and a burst of messages can make the match inexact, so
callers label it "likely message"."""
from app.services import ai_reply, deal_turn

KIND_ASKED_FOR_HUMAN = "asked_for_human"
KIND_KNOWLEDGE_GAP = "knowledge_gap"
KIND_PAYMENT = "payment"
KIND_OTHER = "other"

# Highest first: a chat with several handovers counts once, under its most telling reason.
KIND_PRIORITY = (KIND_ASKED_FOR_HUMAN, KIND_KNOWLEDGE_GAP, KIND_PAYMENT, KIND_OTHER)

_TRIGGERS = ai_reply._TRIGGER_REASONS
_ASKED_FOR_HUMAN = {_TRIGGERS["C"]}
# Anril told the customer it was checking with the team, or its answer failed or fell back.
# Handovers opened before the rename were saved with the old wording; they still count.
_LEGACY_TEAM_CLAIM_REASON = "Aira told the customer it is checking with the team"
_KNOWLEDGE_GAP = {deal_turn.TEAM_CLAIM_REASON, _LEGACY_TEAM_CLAIM_REASON, _TRIGGERS["B"], _TRIGGERS["A"], _TRIGGERS["F"]}
_PAYMENT_PREFIX = "payment link could not be created"

HANDOVER_LIMIT = 20
QUESTION_MAX_CHARS = 300


def classify_reason(reason: str | None) -> str:
    text = (reason or "").strip()
    if text in _ASKED_FOR_HUMAN:
        return KIND_ASKED_FOR_HUMAN
    if text in _KNOWLEDGE_GAP:
        return KIND_KNOWLEDGE_GAP
    if text.lower().startswith(_PAYMENT_PREFIX):
        return KIND_PAYMENT
    return KIND_OTHER


def likely_question(db, tenant_id: str, lead_id: str, opened_at: str) -> str | None:
    rows = (
        db.table("messages")
        .select("content")
        .eq("tenant_id", tenant_id)
        .eq("lead_id", lead_id)
        .eq("direction", "inbound")
        .lte("created_at", opened_at)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    ).data or []
    content = (rows[0].get("content") or "").strip() if rows else ""
    return content[:QUESTION_MAX_CHARS] or None


def recent_handovers(db, tenant_id: str, since_iso: str, *, include_conversation: bool = True) -> list[dict]:
    """The newest handovers opened since since_iso, at most HANDOVER_LIMIT.

    lead_id and likely_question are conversation data: with include_conversation False
    (the caller lacks conversations.view) both come back null and no message is read."""
    rows = (
        db.table("chat_handovers")
        .select("id,lead_id,reason,opened_at")
        .eq("tenant_id", tenant_id)
        .gte("opened_at", since_iso)
        .order("opened_at", desc=True)
        .limit(HANDOVER_LIMIT)
        .execute()
    ).data or []
    return [
        {
            "handover_id": r["id"],
            "lead_id": r["lead_id"] if include_conversation else None,
            "reason": r.get("reason"),
            "kind": classify_reason(r.get("reason")),
            "likely_question": (
                likely_question(db, tenant_id, r["lead_id"], r["opened_at"]) if include_conversation else None
            ),
            "opened_at": r["opened_at"],
        }
        for r in rows
    ]
