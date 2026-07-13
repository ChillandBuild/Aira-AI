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
    "broad_browse" (multiple distinct items/groups -- list options, send no photos).

    A contention set where every candidate is ungrouped (variant_group_id is None for
    all of them) is treated as "confident" on the top-ranked candidate -- items with no
    variant-group data can't be "variants of one thing" or "distinct product families"
    by definition, and legacy/ungrouped tenants must keep today's behavior (recommend
    the best match, no clarifying question) rather than being newly gated.
    """
    if len(contention) == 1:
        return "confident"
    group_ids = {c.get("variant_group_id") for c in contention}
    if group_ids == {None}:
        return "confident"
    if len(group_ids) == 1:
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


def build_catalog_item_embedding_text(
    name: str, item_type: str, description: str | None, attributes: dict | None
) -> str:
    """Combine an item's fields into the text that gets embedded, so retrieval can match
    on location/flavor/size etc, not just name and description."""
    parts = [name, item_type]
    if description:
        parts.append(description)
    for key, value in (attributes or {}).items():
        parts.append(f"{key}: {value}")
    return " | ".join(parts)


async def embed_and_store_catalog_item(
    db, tenant_id: str, item_id: str, name: str, item_type: str,
    description: str | None, attributes: dict | None,
) -> None:
    """Embed one catalog item's text and store it via the update_catalog_item_embedding RPC.
    Raises on embedding/RPC failure -- callers must catch and treat as non-fatal (embedding
    is a retrieval nicety, never a requirement for saving a catalog item)."""
    from app.services.embeddings import embed_texts, to_pgvector

    text = build_catalog_item_embedding_text(name, item_type, description, attributes)
    vectors = await embed_texts([text], input_type="document")
    if not vectors:
        return
    db.rpc(
        "update_catalog_item_embedding",
        {"p_item_id": item_id, "p_tenant_id": tenant_id, "p_embedding": to_pgvector(vectors[0])},
    ).execute()


async def match_catalog_items(db, tenant_id: str, query: str, match_count: int = _MATCH_COUNT) -> list[dict]:
    """Vector similarity search over ready catalog items via Jina embeddings + the
    match_catalog_items RPC. Returns rows shaped {id, name, item_type, description,
    attributes, variant_group_id, similarity}, best-first. Raises on provider/RPC failure --
    callers must catch and fail open to listing every ready item."""
    from app.services.embeddings import embed_query, to_pgvector

    q_emb = await embed_query(query)
    res = db.rpc(
        "match_catalog_items",
        {"query_embedding": to_pgvector(q_emb), "p_tenant_id": tenant_id, "match_count": match_count},
    ).execute()
    return res.data or []


async def reindex_catalog_items(tenant_id: str) -> dict:
    """Backfill embeddings for every ready catalog item that doesn't have one yet."""
    db = get_supabase()
    res = (
        db.table("catalog_items")
        .select("id,name,item_type,description,attributes")
        .eq("tenant_id", tenant_id)
        .eq("status", "ready")
        .execute()
    )
    items = res.data or []
    embedded = 0
    for item in items:
        try:
            await embed_and_store_catalog_item(
                db, tenant_id, item["id"], item["name"], item["item_type"],
                item.get("description"), item.get("attributes") or {},
            )
            embedded += 1
        except Exception as e:
            logger.error(f"Catalog reindex failed for item {item['id']}: {e}")
    return {"items_embedded": embedded, "items_total": len(items)}
