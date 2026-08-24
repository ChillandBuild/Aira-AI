"""Client-authored WhatsApp button messages ("quick reply blocks").

A tenant saves a named message with up to 3 reply buttons plus a `use_when` line;
the AI selects one via a tool call, the same mechanism the product catalog uses.
Every decision is a pure function here so it can be tested without a DB or an LLM
-- ai_reply.py holds only the wiring.
"""
import logging

from app.services.meta_cloud import BUTTON_COUNT_MAX

logger = logging.getLogger(__name__)

# The block list rides in every reply's prompt for that tenant, roughly 25 tokens
# each. Ten is negligible; fifty would not be. Raising this without adding
# embedding-based shortlisting first is a mistake.
MAX_BLOCKS_PER_TENANT = 10
BODY_TEXT_MAX = 1024

QUICK_REPLY_TOOL_NAME = "send_quick_reply_block"


def load_active_blocks(db, tenant_id: str) -> list[dict]:
    """Active blocks for a tenant. Returns [] on any error -- a retrieval hiccup
    must degrade to an ordinary text reply, never break the conversation."""
    try:
        result = (
            db.table("quick_reply_blocks")
            .select("*")
            .eq("tenant_id", tenant_id)
            .eq("is_active", True)
            .order("created_at")
            .limit(MAX_BLOCKS_PER_TENANT)
            .execute()
        )
        return result.data or []
    except Exception:
        logger.warning("Quick reply block load failed for tenant %s", tenant_id)
        return []


def build_quick_reply_tool(blocks: list[dict]) -> list[dict]:
    """The tool definition offered to the model, or [] when there is nothing to offer."""
    if not blocks:
        return []
    lines = "\n".join(f"  - {b['name']}: {b['use_when']}" for b in blocks)
    return [{
        "type": "function",
        "function": {
            "name": QUICK_REPLY_TOOL_NAME,
            "description": (
                "Send a saved button message when the lead's question matches one of "
                "these. Call this INSTEAD of writing your own reply -- the saved message "
                "is sent exactly as written. Do NOT call more than once per reply. "
                "Available blocks:\n" + lines
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "block_name": {
                        "type": "string",
                        "enum": [b["name"] for b in blocks],
                        "description": "The exact name of the block to send",
                    }
                },
                "required": ["block_name"],
            },
        },
    }]


def resolve_block(blocks: list[dict], name: str | None) -> dict | None:
    """Find a block by name. Returns None for a hallucinated or empty name so the
    caller falls through to an ordinary reply rather than sending an arbitrary block."""
    if not name:
        return None
    cleaned = name.strip().lower()
    for b in blocks:
        if (b.get("name") or "").strip().lower() == cleaned:
            return b
    return None


def to_send_buttons(block: dict) -> list[dict]:
    """Block buttons in the shape send_interactive_buttons expects.

    No truncation: send_interactive_buttons raises on an over-long title, and the
    API rejects one at write time, so anything stored here already fits.
    """
    return [
        {"id": b["id"], "title": b["label"]}
        for b in (block.get("buttons") or [])[:BUTTON_COUNT_MAX]
    ]


def format_block_log(block: dict) -> str:
    """What gets written to messages.content -- the body plus the offered labels, so
    the thread the AI reads back and the operator inbox both show what the lead saw."""
    labels = " ".join(f"[{b['label']}]" for b in (block.get("buttons") or []))
    body = block.get("body_text") or ""
    return f"{body}\n\n{labels}" if labels else body


def last_outbound_was_block(blocks: list[dict], recent_thread: list[dict]) -> bool:
    """True when the most recent OUTBOUND message was one of these blocks.

    recent_thread is newest-first, as generate_reply fetches it. Only the newest
    outbound row is considered: a lead who did not tap should not be handed the
    identical buttons again, but one older block send should not mute the feature.
    Inbound rows are skipped so a lead quoting the body text back cannot suppress it.
    """
    bodies = [(b.get("body_text") or "").strip() for b in blocks]
    bodies = [b for b in bodies if b]
    if not bodies:
        return False
    for row in recent_thread:
        if row.get("direction") != "outbound":
            continue
        content = (row.get("content") or "").strip()
        return any(content.startswith(body) for body in bodies)
    return False


def should_offer_quick_replies(
    channel: str, intake_active: bool, blocks: list[dict], recent_thread: list[dict]
) -> bool:
    """Whether to hand the model the quick-reply tool this turn.

    intake_active drops it for the same reason the catalog tool is dropped: a prompt
    instruction has no effect on a live tool definition the model can still call, so
    the tool itself has to go. Non-WhatsApp channels have no button format at all.
    """
    if channel != "whatsapp":
        return False
    if intake_active:
        return False
    if not blocks:
        return False
    return not last_outbound_was_block(blocks, recent_thread)
