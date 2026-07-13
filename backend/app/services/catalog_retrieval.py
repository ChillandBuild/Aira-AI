"""Semantic disambiguation gate for AI catalog recommendations.

When a customer's message matches several catalog items that are variants of one
underlying thing (same apartment type across cities, same cake across flavors/sizes),
the AI should ask which one instead of guessing or recommending every match. This module
turns a ranked list of retrieval candidates into that decision.
"""
import logging

from app.db.supabase import get_supabase

logger = logging.getLogger(__name__)

_CONFIDENT_MARGIN = 0.08
_MATCH_COUNT = 5


def contention_set(candidates: list[dict]) -> list[dict]:
    """Return the prefix of `candidates` (best-first, each with a 'similarity' float)
    whose similarity is within _CONFIDENT_MARGIN of the top score. Empty input returns
    empty output; a single candidate is trivially its own one-item contention set."""
    if not candidates:
        return []
    top = candidates[0]["similarity"]
    return [c for c in candidates if c["similarity"] >= top - _CONFIDENT_MARGIN]


def classify_gate(contention: list[dict]) -> str:
    """Classify a non-empty contention set as "confident" (one item, safe to recommend
    directly), "same_group" (multiple variants of one item -- ask which one), or
    "broad_browse" (multiple distinct items/groups -- list options, send no photos)."""
    if len(contention) == 1:
        return "confident"
    group_ids = {c.get("variant_group_id") for c in contention}
    if len(group_ids) == 1 and None not in group_ids:
        return "same_group"
    return "broad_browse"


def differing_attribute_directive(contention: list[dict]) -> str:
    """Build a system-prompt directive asking the customer to pick between variants of
    one item, naming the actual attribute values that differ (e.g. 'location: Coimbatore,
    Chennai, Salem') rather than letting the model invent the question."""
    all_keys: set[str] = set()
    for c in contention:
        all_keys.update((c.get("attributes") or {}).keys())

    differing_lines = []
    for key in sorted(all_keys):
        values = [
            str((c.get("attributes") or {}).get(key))
            for c in contention
            if (c.get("attributes") or {}).get(key)
        ]
        distinct = sorted(set(values))
        if len(distinct) > 1:
            differing_lines.append(f"{key}: {', '.join(distinct)}")

    names = ", ".join(c["name"] for c in contention)
    detail = f" that differ by {'; '.join(differing_lines)}" if differing_lines else ""
    return (
        f"\n\nDISAMBIGUATION NEEDED: The customer's message matches multiple variants of the same "
        f"item ({names}){detail}. Ask the customer which one they mean before recommending or "
        f"sending any photo. Do NOT call recommend_catalog_item yet."
    )


def broad_browse_directive(contention: list[dict]) -> str:
    """Build a system-prompt directive for a message matching several distinct
    items/product families (not variants of one thing) -- list the options as text,
    send zero images until the customer narrows it down."""
    names = ", ".join(sorted({c["name"] for c in contention}))
    return (
        f"\n\nDISAMBIGUATION NEEDED: The customer's message could refer to several different "
        f"items: {names}. List these options in your reply and ask which one they want. Do NOT "
        f"call recommend_catalog_item and do NOT send any photos yet."
    )
