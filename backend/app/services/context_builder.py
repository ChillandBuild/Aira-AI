import logging
from app.db.supabase import get_supabase

logger = logging.getLogger(__name__)


def _safe_data(response) -> list | dict:
    """Safely extract .data from a Supabase response that may be None."""
    if response is None:
        return []
    return (response.data or []) if hasattr(response, "data") else []


def _format_messages(messages: list[dict]) -> str:
    """Format messages for LLM context."""
    lines = []
    for msg in reversed(messages):
        direction = "Bot" if msg.get("direction") == "outbound" else "User"
        content = (msg.get("content") or "").strip()[:200]
        if content and not content.startswith("[Template"):
            lines.append(f"{direction}: {content}")
    return "\n".join(lines) if lines else "No messages available."


def build_scorer_context(
    lead_id: str,
    db=None,
    force_full_context: bool = False
) -> str:
    """
    Build context block for the lead scorer.
    
    Args:
        lead_id: Lead UUID
        db: Supabase client (optional)
        force_full_context: If True, fetch maximum context for D-segment safety net
    
    Returns:
        Formatted context string for the scorer prompt
    """
    db = db or get_supabase()
    
    try:
        # Fetch conversation state
        state_row = (
            db.table("lead_conversation_state")
            .select("conversation_summary, message_count, state, draft_data")
            .eq("lead_id", lead_id)
            .maybe_single()
            .execute()
        )
        state_data = _safe_data(state_row) or {}
        summary = state_data.get("conversation_summary")
        msg_count = state_data.get("message_count", 0)
        flow_state = state_data.get("state", "idle")
        
        if force_full_context:
            # D-segment safety net: fetch maximum context
            if summary:
                # Post-compaction: summary + last 10 messages
                messages = (
                    db.table("messages")
                    .select("direction, content, created_at")
                    .eq("lead_id", lead_id)
                    .order("created_at", desc=True)
                    .limit(10)
                    .execute()
                )
                context_block = (
                    f"CONVERSATION SUMMARY:\n{summary}\n\n"
                    f"RECENT MESSAGES (full context for re-evaluation):\n{_format_messages(_safe_data(messages))}\n\n"
                    f"CURRENT FLOW STATE: {flow_state}"
                )
            else:
                # Pre-compaction: ALL prior messages
                messages = (
                    db.table("messages")
                    .select("direction, content, created_at")
                    .eq("lead_id", lead_id)
                    .order("created_at", desc=True)
                    .execute()
                )
                context_block = (
                    f"FULL CONVERSATION HISTORY:\n{_format_messages(_safe_data(messages))}\n\n"
                    f"CURRENT FLOW STATE: {flow_state}"
                )
        else:
            # Normal scoring path
            if summary:
                # Post-compaction: summary + last 5 messages
                messages = (
                    db.table("messages")
                    .select("direction, content, created_at")
                    .eq("lead_id", lead_id)
                    .order("created_at", desc=True)
                    .limit(5)
                    .execute()
                )
                context_block = (
                    f"CONVERSATION SUMMARY:\n{summary}\n\n"
                    f"RECENT MESSAGES:\n{_format_messages(_safe_data(messages))}\n\n"
                    f"CURRENT FLOW STATE: {flow_state}"
                )
            else:
                # Pre-compaction: last 10 messages
                messages = (
                    db.table("messages")
                    .select("direction, content, created_at")
                    .eq("lead_id", lead_id)
                    .order("created_at", desc=True)
                    .limit(10)
                    .execute()
                )
                context_block = (
                    f"RECENT CONVERSATION:\n{_format_messages(_safe_data(messages))}\n\n"
                    f"CURRENT FLOW STATE: {flow_state}"
                )
        
        return context_block
        
    except Exception as e:
        logger.error(f"Failed to build scorer context for lead {lead_id}: {e}")
        return "No prior conversation context available."
