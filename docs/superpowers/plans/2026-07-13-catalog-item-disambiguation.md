# Catalog Item Disambiguation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the AI catalog feature from guessing (or over-sending) when a customer's message matches several catalog items that are variants of one thing — ask which one instead — and make `max_images_per_reply` an actually-enforced cap.

**Architecture:** Add variant-group + attribute schema and a `vector(512)` embedding column to `catalog_items`, reusing the Knowledge Base RAG stack's Jina-embeddings + pgvector + RPC pattern verbatim. A new `catalog_retrieval.py` module does retrieval (query embedding → `match_catalog_items` RPC) and a pure disambiguation gate (contention set → confident / same-group / broad-browse). `ai_reply.py`'s `_build_catalog_context` is rewired to use it, failing open to today's "list everything" behavior on any retrieval error. The send loop gets a hard `max_images_per_reply` slice, independent of the gate.

**Tech Stack:** Python 3, FastAPI, Supabase (Postgres + pgvector, already installed per migration 087), Jina `jina-embeddings-v3` via `app/services/embeddings.py` (already wired, no new provider), pytest / `unittest.TestCase` + `unittest.IsolatedAsyncioTestCase`.

## Global Constraints

- Reuse `app/services/embeddings.py` (`embed_texts`, `embed_query`, `to_pgvector`) exactly as-is — do not add a second embedding provider or change `EMBED_DIM` (512).
- Migration numbering: re-verify the actual current max with `ls backend/supabase/migrations | sort | tail -5` immediately before creating the file — this plan assumes `140_...sql` (current max at plan-writing time is `139_repair_tenant_rbac_schema_cache.sql`), but the sequence moves fast across branches; do not hardcode 140 blindly.
- Fail-open, always: any embedding/RPC/provider failure must fall back to today's "list every ready item" behavior for that turn — a provider hiccup must never block a reply. Mirror `knowledge_service.get_knowledge_context`'s documented contract (`backend/app/services/knowledge_service.py:265-266`).
- Fully backward compatible: existing `catalog_items` rows get `attributes = {}`, `variant_group_id = null`, `embedding = null` and must behave exactly as they do today (no new clarifying questions for ungrouped tenants).
- Test conventions: mirror `backend/tests/test_catalog.py` exactly — `unittest.TestCase`/`unittest.IsolatedAsyncioTestCase`, `@patch("app.<module>.<name>", ...)` targeting the module the code actually imports from, `sys.path.insert(0, str(Path(__file__).resolve().parents[1]))` at the top of new test files.
- Run backend tests with `cd backend && pytest tests/<file>.py -v` (per project `CLAUDE.md`).
- No frontend changes in this plan — the variant-group/attribute editor UI is an explicit fast-follow; the backend gate must work correctly even with zero UI support (data can be seeded directly via the API/DB).

---

### Task 1: Schema migration — variant groups, catalog item columns, retrieval RPCs

**Files:**
- Create: `backend/supabase/migrations/140_catalog_disambiguation.sql` (verify exact number per Global Constraints first)

**Interfaces:**
- Produces:
  - Table `catalog_variant_groups(id uuid pk, tenant_id uuid, name text, item_type text, created_at timestamptz)`, RLS enabled, tenant-scoped policy.
  - `catalog_items` gains `attributes jsonb not null default '{}'`, `variant_group_id uuid references catalog_variant_groups(id) on delete set null`, `embedding vector(512)`.
  - RPC `update_catalog_item_embedding(p_item_id uuid, p_tenant_id uuid, p_embedding text) returns void`.
  - RPC `match_catalog_items(query_embedding text, p_tenant_id uuid, match_count int default 5) returns table(id uuid, name text, item_type text, description text, attributes jsonb, variant_group_id uuid, similarity float)`.

- [x] **Step 1: Verify the current migration number**

Run: `ls backend/supabase/migrations | sort | tail -5`
Expected: the highest `NNN_*.sql` file. Use `NNN+1` as this migration's number (this plan assumes `140`; adjust every reference below if the real max differs).

- [x] **Step 2: Write the migration file**

Create `backend/supabase/migrations/140_catalog_disambiguation.sql`:

```sql
-- 140_catalog_disambiguation.sql
-- Adds variant grouping + semantic retrieval to catalog_items so the AI can disambiguate
-- between variants of the same item (e.g. same apartment type across cities, same cake
-- across flavors/sizes) instead of guessing or recommending every match. Reuses the same
-- pgvector setup and Jina embeddings (512-dim) already wired for Knowledge Base RAG
-- (087_knowledge_rag.sql) -- no new embedding provider.

create table if not exists catalog_variant_groups (
    id          uuid primary key default gen_random_uuid(),
    tenant_id   uuid references tenants(id) on delete cascade not null,
    name        text not null,
    item_type   text not null default 'product',
    created_at  timestamptz not null default now()
);
alter table catalog_variant_groups enable row level security;
create policy "Tenant members can manage their catalog variant groups" on catalog_variant_groups
    for all using (tenant_id = (select tenant_id from tenant_users where user_id = auth.uid() limit 1));

alter table catalog_items
    add column if not exists attributes jsonb not null default '{}',
    add column if not exists variant_group_id uuid references catalog_variant_groups(id) on delete set null,
    add column if not exists embedding vector(512);

create index if not exists idx_catalog_items_variant_group on catalog_items(variant_group_id);
create index if not exists catalog_items_embedding_idx
    on catalog_items using hnsw (embedding vector_cosine_ops);

-- Stores an item's embedding. Embedding arrives as a vector-literal string (e.g. '[0.1,0.2,...]')
-- and is cast inside, sidestepping PostgREST/supabase-py vector serialization (same pattern as
-- insert_knowledge_chunk in 087_knowledge_rag.sql).
create or replace function update_catalog_item_embedding(
    p_item_id   uuid,
    p_tenant_id uuid,
    p_embedding text
) returns void
language plpgsql
as $$
begin
    update catalog_items
    set embedding = p_embedding::vector(512)
    where id = p_item_id and tenant_id = p_tenant_id;
end;
$$;

-- Top-k cosine match over ready items, tenant-scoped. query_embedding is a vector-literal string.
create or replace function match_catalog_items(
    query_embedding text,
    p_tenant_id     uuid,
    match_count     int default 5
) returns table (
    id               uuid,
    name             text,
    item_type        text,
    description      text,
    attributes       jsonb,
    variant_group_id uuid,
    similarity       float
)
language sql
stable
as $$
    select
        ci.id, ci.name, ci.item_type, ci.description, ci.attributes, ci.variant_group_id,
        1 - (ci.embedding <=> query_embedding::vector(512)) as similarity
    from catalog_items ci
    where ci.tenant_id = p_tenant_id
      and ci.status = 'ready'
      and ci.embedding is not null
    order by ci.embedding <=> query_embedding::vector(512)
    limit match_count;
$$;
```

- [x] **Step 3: Apply the migration**

Apply via the project's Supabase MCP tool (`mcp__claude_ai_Supabase__apply_migration`) or `supabase db push` per this project's existing migration workflow — do not hand-run it against production without going through the same path prior migrations used.

- [x] **Step 4: Verify the schema landed**

Run this query (via the Supabase MCP `execute_sql` tool or `mcp__claude_ai_Supabase__list_tables`):

```sql
select column_name from information_schema.columns
where table_name = 'catalog_items' and column_name in ('attributes', 'variant_group_id', 'embedding');

select proname from pg_proc where proname in ('match_catalog_items', 'update_catalog_item_embedding');
```

Expected: 3 rows from the first query, 2 rows from the second.

- [x] **Step 5: Commit**

```bash
git add backend/supabase/migrations/140_catalog_disambiguation.sql
git commit -m "feat: add variant grouping + embedding columns for catalog disambiguation"
```

---

### Task 2: Disambiguation gate — pure logic

**Files:**
- Create: `backend/app/services/catalog_retrieval.py`
- Test: `backend/tests/test_catalog_retrieval.py`

**Interfaces:**
- Produces:
  - `contention_set(candidates: list[dict]) -> list[dict]` — `candidates` are best-first dicts with a `similarity` float key.
  - `classify_gate(contention: list[dict]) -> str` — returns `"confident"`, `"same_group"`, or `"broad_browse"`. Assumes non-empty input.
  - `differing_attribute_directive(contention: list[dict]) -> str`
  - `broad_browse_directive(contention: list[dict]) -> str`

- [x] **Step 1: Write the failing tests**

Create `backend/tests/test_catalog_retrieval.py`:

```python
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.catalog_retrieval import (
    contention_set,
    classify_gate,
    differing_attribute_directive,
    broad_browse_directive,
)


class ContentionSetTests(unittest.TestCase):
    def test_empty_candidates_returns_empty(self):
        self.assertEqual(contention_set([]), [])

    def test_single_candidate_is_its_own_contention_set(self):
        candidates = [{"id": "a", "similarity": 0.9}]
        self.assertEqual(contention_set(candidates), candidates)

    def test_confident_top_match_excludes_far_second(self):
        candidates = [
            {"id": "a", "similarity": 0.91},
            {"id": "b", "similarity": 0.60},
        ]
        self.assertEqual(contention_set(candidates), [candidates[0]])

    def test_close_scores_are_all_in_contention(self):
        candidates = [
            {"id": "a", "similarity": 0.83},
            {"id": "b", "similarity": 0.82},
            {"id": "c", "similarity": 0.81},
            {"id": "d", "similarity": 0.55},
        ]
        self.assertEqual(contention_set(candidates), candidates[:3])


class ClassifyGateTests(unittest.TestCase):
    def test_single_item_is_confident(self):
        self.assertEqual(classify_gate([{"id": "a", "variant_group_id": None}]), "confident")

    def test_shared_variant_group_is_same_group(self):
        contention = [
            {"id": "a", "variant_group_id": "vg-1"},
            {"id": "b", "variant_group_id": "vg-1"},
        ]
        self.assertEqual(classify_gate(contention), "same_group")

    def test_ungrouped_items_are_broad_browse(self):
        contention = [
            {"id": "a", "variant_group_id": None},
            {"id": "b", "variant_group_id": None},
        ]
        self.assertEqual(classify_gate(contention), "broad_browse")

    def test_different_variant_groups_are_broad_browse(self):
        contention = [
            {"id": "a", "variant_group_id": "vg-1"},
            {"id": "b", "variant_group_id": "vg-2"},
        ]
        self.assertEqual(classify_gate(contention), "broad_browse")


class DifferingAttributeDirectiveTests(unittest.TestCase):
    def test_names_differing_locations(self):
        contention = [
            {"id": "a", "name": "2BHK Apartment", "attributes": {"location": "Coimbatore"}},
            {"id": "b", "name": "2BHK Apartment", "attributes": {"location": "Chennai"}},
            {"id": "c", "name": "2BHK Apartment", "attributes": {"location": "Salem"}},
        ]
        directive = differing_attribute_directive(contention)
        self.assertIn("location: Chennai, Coimbatore, Salem", directive)
        self.assertIn("Do NOT call recommend_catalog_item", directive)

    def test_no_shared_attribute_key_still_produces_a_directive(self):
        contention = [
            {"id": "a", "name": "Chocolate Cake", "attributes": {}},
            {"id": "b", "name": "Chocolate Cake", "attributes": {}},
        ]
        directive = differing_attribute_directive(contention)
        self.assertIn("Chocolate Cake", directive)
        self.assertIn("Do NOT call recommend_catalog_item", directive)


class BroadBrowseDirectiveTests(unittest.TestCase):
    def test_lists_distinct_item_names(self):
        contention = [
            {"id": "a", "name": "Chocolate Cake"},
            {"id": "b", "name": "Red Velvet Cake"},
        ]
        directive = broad_browse_directive(contention)
        self.assertIn("Chocolate Cake", directive)
        self.assertIn("Red Velvet Cake", directive)
        self.assertIn("do NOT send any photos", directive)


if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `cd backend && pytest tests/test_catalog_retrieval.py -v`
Expected: `ModuleNotFoundError: No module named 'app.services.catalog_retrieval'` (or import error) — the module doesn't exist yet.

- [x] **Step 3: Write the implementation**

Create `backend/app/services/catalog_retrieval.py`:

```python
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
```

- [x] **Step 4: Run the tests to verify they pass**

Run: `cd backend && pytest tests/test_catalog_retrieval.py -v`
Expected: all `ContentionSetTests`, `ClassifyGateTests`, `DifferingAttributeDirectiveTests`, `BroadBrowseDirectiveTests` PASS.

- [x] **Step 5: Commit**

```bash
git add backend/app/services/catalog_retrieval.py backend/tests/test_catalog_retrieval.py
git commit -m "feat: add pure disambiguation gate logic for catalog retrieval"
```

---

### Task 3: Retrieval + embedding + reindex functions

**Files:**
- Modify: `backend/app/services/catalog_retrieval.py` (append to the file from Task 2)
- Test: `backend/tests/test_catalog_retrieval.py` (append to the file from Task 2)

**Interfaces:**
- Consumes: Task 1's RPCs (`update_catalog_item_embedding`, `match_catalog_items`); `app/services/embeddings.py`'s `embed_texts`, `embed_query`, `to_pgvector` (existing, unchanged).
- Produces:
  - `build_catalog_item_embedding_text(name: str, item_type: str, description: str | None, attributes: dict | None) -> str`
  - `async def embed_and_store_catalog_item(db, tenant_id: str, item_id: str, name: str, item_type: str, description: str | None, attributes: dict | None) -> None`
  - `async def match_catalog_items(db, tenant_id: str, query: str, match_count: int = 5) -> list[dict]`
  - `async def reindex_catalog_items(tenant_id: str) -> dict` — returns `{"items_embedded": int, "items_total": int}`

- [x] **Step 1: Write the failing tests**

Append to `backend/tests/test_catalog_retrieval.py` (add this import near the top alongside the existing ones: `from unittest.mock import MagicMock, patch`):

```python
class BuildEmbeddingTextTests(unittest.TestCase):
    def test_combines_name_type_description_and_attributes(self):
        from app.services.catalog_retrieval import build_catalog_item_embedding_text

        text = build_catalog_item_embedding_text(
            "2BHK Apartment", "property", "Spacious flat", {"location": "Coimbatore"}
        )
        self.assertIn("2BHK Apartment", text)
        self.assertIn("property", text)
        self.assertIn("Spacious flat", text)
        self.assertIn("location: Coimbatore", text)

    def test_skips_missing_description(self):
        from app.services.catalog_retrieval import build_catalog_item_embedding_text

        text = build_catalog_item_embedding_text("Item", "product", None, {})
        self.assertEqual(text, "Item | product")


class EmbedAndStoreCatalogItemTests(unittest.IsolatedAsyncioTestCase):
    @patch("app.services.embeddings.embed_texts")
    async def test_stores_embedding_via_rpc(self, mock_embed_texts):
        from app.services.catalog_retrieval import embed_and_store_catalog_item

        mock_embed_texts.return_value = [[0.1, 0.2, 0.3]]
        db = MagicMock()

        await embed_and_store_catalog_item(
            db, "tenant-1", "item-1", "Chocolate Cake", "product", "Rich cake", {}
        )

        db.rpc.assert_called_once()
        rpc_name, rpc_args = db.rpc.call_args[0]
        self.assertEqual(rpc_name, "update_catalog_item_embedding")
        self.assertEqual(rpc_args["p_item_id"], "item-1")
        self.assertEqual(rpc_args["p_tenant_id"], "tenant-1")
        self.assertIn("0.1", rpc_args["p_embedding"])

    @patch("app.services.embeddings.embed_texts", return_value=[])
    async def test_no_vectors_returned_is_a_noop(self, mock_embed_texts):
        from app.services.catalog_retrieval import embed_and_store_catalog_item

        db = MagicMock()
        await embed_and_store_catalog_item(db, "tenant-1", "item-1", "Item", "product", None, {})
        db.rpc.assert_not_called()


class MatchCatalogItemsTests(unittest.IsolatedAsyncioTestCase):
    @patch("app.services.embeddings.embed_query")
    async def test_returns_rpc_rows(self, mock_embed_query):
        from app.services.catalog_retrieval import match_catalog_items

        mock_embed_query.return_value = [0.1, 0.2]
        db = MagicMock()
        db.rpc.return_value.execute.return_value.data = [
            {"id": "item-1", "name": "2BHK Coimbatore", "similarity": 0.83}
        ]

        rows = await match_catalog_items(db, "tenant-1", "2bhk apartment photos")

        self.assertEqual(rows[0]["id"], "item-1")
        rpc_name, rpc_args = db.rpc.call_args[0]
        self.assertEqual(rpc_name, "match_catalog_items")
        self.assertEqual(rpc_args["p_tenant_id"], "tenant-1")

    @patch("app.services.embeddings.embed_query")
    async def test_no_rows_returns_empty_list(self, mock_embed_query):
        from app.services.catalog_retrieval import match_catalog_items

        mock_embed_query.return_value = [0.1, 0.2]
        db = MagicMock()
        db.rpc.return_value.execute.return_value.data = None

        rows = await match_catalog_items(db, "tenant-1", "anything")
        self.assertEqual(rows, [])


class ReindexCatalogItemsTests(unittest.IsolatedAsyncioTestCase):
    @patch("app.services.catalog_retrieval.embed_and_store_catalog_item")
    @patch("app.services.catalog_retrieval.get_supabase")
    async def test_embeds_every_ready_item_without_one(self, mock_get_db, mock_embed_and_store):
        from app.services.catalog_retrieval import reindex_catalog_items

        db = MagicMock()
        db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
            {"id": "item-1", "name": "A", "item_type": "product", "description": None, "attributes": {}},
            {"id": "item-2", "name": "B", "item_type": "product", "description": None, "attributes": {}},
        ]
        mock_get_db.return_value = db
        mock_embed_and_store.return_value = None

        result = await reindex_catalog_items("tenant-1")

        self.assertEqual(result, {"items_embedded": 2, "items_total": 2})
        self.assertEqual(mock_embed_and_store.call_count, 2)

    @patch("app.services.catalog_retrieval.embed_and_store_catalog_item")
    @patch("app.services.catalog_retrieval.get_supabase")
    async def test_one_item_failing_does_not_stop_the_rest(self, mock_get_db, mock_embed_and_store):
        from app.services.catalog_retrieval import reindex_catalog_items

        db = MagicMock()
        db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
            {"id": "item-1", "name": "A", "item_type": "product", "description": None, "attributes": {}},
            {"id": "item-2", "name": "B", "item_type": "product", "description": None, "attributes": {}},
        ]
        mock_get_db.return_value = db
        mock_embed_and_store.side_effect = [Exception("boom"), None]

        result = await reindex_catalog_items("tenant-1")

        self.assertEqual(result, {"items_embedded": 1, "items_total": 2})
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `cd backend && pytest tests/test_catalog_retrieval.py -v`
Expected: the new test classes FAIL with `ImportError`/`AttributeError` (`build_catalog_item_embedding_text`, `embed_and_store_catalog_item`, `match_catalog_items`, `reindex_catalog_items` don't exist yet). The Task 2 test classes still PASS.

- [x] **Step 3: Append the implementation**

Append to `backend/app/services/catalog_retrieval.py`:

```python
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
```

- [x] **Step 4: Run the tests to verify they pass**

Run: `cd backend && pytest tests/test_catalog_retrieval.py -v`
Expected: every test in the file PASSES (Task 2's classes plus the new ones from Step 1).

- [x] **Step 5: Commit**

```bash
git add backend/app/services/catalog_retrieval.py backend/tests/test_catalog_retrieval.py
git commit -m "feat: add embedding storage, retrieval, and reindex to catalog_retrieval"
```

---

### Task 4: Wire the gate into `ai_reply.py` and enforce the image cap

**Files:**
- Modify: `backend/app/services/ai_reply.py:9` (imports), `:747-796` (`_build_catalog_context`), `:946-991` (caller in `generate_reply`), `:1176-1178` (send loop)
- Modify: `backend/tests/test_catalog.py` (update `CatalogAiReplyIntegrationTests` for the new async 4-tuple signature; add cap-enforcement and gate-behavior tests)

**Interfaces:**
- Consumes: Task 2/3's `contention_set`, `classify_gate`, `differing_attribute_directive`, `broad_browse_directive`, `match_catalog_items` from `app.services.catalog_retrieval`.
- Produces: `_build_catalog_context(db, tenant_id: str, message: str) -> tuple[str, list[dict], dict[str, dict], int]` — now **async**, returns `(catalog_text_block, tool_definitions, items_by_id, max_images_per_reply)`.

- [x] **Step 1: Write the failing tests**

In `backend/tests/test_catalog.py`, replace the entire `CatalogAiReplyIntegrationTests` class (it currently spans lines 196-273) with:

```python
class CatalogAiReplyIntegrationTests(unittest.IsolatedAsyncioTestCase):
    """Tests for _build_catalog_context and _load_catalog_ai_rules in ai_reply.py."""

    async def test_build_catalog_context_returns_empty_when_can_recommend_is_false(self):
        from app.services.ai_reply import _build_catalog_context
        db = MagicMock()
        db.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
            {"value": json.dumps({"can_recommend": False})}
        ]

        text, tools, items_by_id, max_images = await _build_catalog_context(db, "tenant-1", "hello")
        self.assertEqual(text, "")
        self.assertEqual(tools, [])
        self.assertEqual(items_by_id, {})
        self.assertEqual(max_images, 0)

    @patch("app.services.ai_reply.match_catalog_items")
    async def test_confident_single_match_offers_the_tool_for_that_item_only(self, mock_match):
        from app.services.ai_reply import _build_catalog_context
        db = MagicMock()
        db.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
        mock_match.return_value = [
            {"id": "item-1", "name": "Chocolate Cake", "item_type": "product", "description": "Rich cake",
             "attributes": {}, "variant_group_id": None, "similarity": 0.91},
            {"id": "item-2", "name": "Vanilla Cake", "item_type": "product", "description": "Light cake",
             "attributes": {}, "variant_group_id": None, "similarity": 0.55},
        ]

        text, tools, items_by_id, max_images = await _build_catalog_context(db, "tenant-1", "chocolate cake photos")

        self.assertIn("Chocolate Cake", text)
        self.assertNotIn("Vanilla Cake", text)
        self.assertEqual(list(items_by_id.keys()), ["item-1"])
        self.assertEqual(len(tools), 1)
        self.assertEqual(max_images, 3)

    @patch("app.services.ai_reply.match_catalog_items")
    async def test_ambiguous_same_group_withholds_tool_and_asks_which_one(self, mock_match):
        from app.services.ai_reply import _build_catalog_context
        db = MagicMock()
        db.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
        mock_match.return_value = [
            {"id": "a", "name": "2BHK Apartment", "item_type": "property", "description": None,
             "attributes": {"location": "Coimbatore"}, "variant_group_id": "vg-1", "similarity": 0.83},
            {"id": "b", "name": "2BHK Apartment", "item_type": "property", "description": None,
             "attributes": {"location": "Chennai"}, "variant_group_id": "vg-1", "similarity": 0.82},
            {"id": "c", "name": "2BHK Apartment", "item_type": "property", "description": None,
             "attributes": {"location": "Salem"}, "variant_group_id": "vg-1", "similarity": 0.81},
        ]

        text, tools, items_by_id, max_images = await _build_catalog_context(db, "tenant-1", "2bhk apartment photos")

        self.assertIn("DISAMBIGUATION NEEDED", text)
        self.assertIn("location: Chennai, Coimbatore, Salem", text)
        self.assertEqual(tools, [])
        self.assertEqual(items_by_id, {})

    @patch("app.services.ai_reply.match_catalog_items")
    async def test_broad_browse_lists_distinct_items_and_withholds_tool(self, mock_match):
        from app.services.ai_reply import _build_catalog_context
        db = MagicMock()
        db.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
        mock_match.return_value = [
            {"id": "a", "name": "Chocolate Cake", "item_type": "product", "description": None,
             "attributes": {}, "variant_group_id": None, "similarity": 0.80},
            {"id": "b", "name": "Red Velvet Cake", "item_type": "product", "description": None,
             "attributes": {}, "variant_group_id": None, "similarity": 0.79},
        ]

        text, tools, items_by_id, max_images = await _build_catalog_context(db, "tenant-1", "show me your cakes")

        self.assertIn("Chocolate Cake", text)
        self.assertIn("Red Velvet Cake", text)
        self.assertIn("do NOT send any photos", text)
        self.assertEqual(tools, [])

    @patch("app.services.ai_reply.match_catalog_items", side_effect=Exception("provider down"))
    async def test_retrieval_failure_falls_back_to_full_catalog_list(self, mock_match):
        from app.services.ai_reply import _build_catalog_context
        db = MagicMock()

        def table(name):
            tbl = MagicMock()
            if name == "app_settings":
                tbl.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
            elif name == "catalog_items":
                tbl.select.return_value.eq.return_value.eq.return_value.order.return_value.execute.return_value.data = [
                    {"id": "item-1", "name": "Chocolate Cake", "item_type": "product", "description": "Rich cake"}
                ]
            return tbl

        db.table.side_effect = table

        text, tools, items_by_id, max_images = await _build_catalog_context(db, "tenant-1", "cake photos")

        self.assertIn("Chocolate Cake", text)
        self.assertEqual(len(tools), 1)
        self.assertEqual(items_by_id["item-1"]["name"], "Chocolate Cake")

    async def test_load_catalog_ai_rules_merges_with_defaults(self):
        from app.services.ai_reply import _load_catalog_ai_rules
        db = MagicMock()
        db.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
            {"value": json.dumps({"can_recommend": False})}
        ]

        rules = _load_catalog_ai_rules(db, "tenant-1")
        self.assertFalse(rules["can_recommend"])
        self.assertTrue(rules["can_send_images"])  # from defaults
        self.assertEqual(rules["max_images_per_reply"], 3)  # from defaults

    def test_generate_reply_static_import_scopes(self):
        import inspect
        from app.services import ai_reply

        source = inspect.getsource(ai_reply.generate_reply)
        assert "_build_catalog_context" in source
        assert "sarvam_chat_completion_with_tools" in source
        assert "catalog_images_to_send" in source
        assert "catalog_max_images" in source


class CatalogImageCapEnforcementTests(unittest.TestCase):
    def test_send_loop_slices_to_max_images_per_reply(self):
        """Static check: the WhatsApp catalog-image send loop must slice
        catalog_images_to_send by catalog_max_images, not iterate it unbounded --
        this is the hard cap that must hold even if the model over-recommends."""
        import inspect
        from app.services import ai_reply

        source = inspect.getsource(ai_reply.generate_reply)
        assert "catalog_images_to_send[:catalog_max_images]" in source


if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `cd backend && pytest tests/test_catalog.py -v`
Expected: `CatalogAiReplyIntegrationTests` and `CatalogImageCapEnforcementTests` FAIL — `_build_catalog_context` isn't async yet, doesn't accept `message`, doesn't return a 4-tuple, and `app.services.ai_reply.match_catalog_items` doesn't exist. The other classes in the file (`CatalogItemsTests`, `CatalogMediaTests`, `CatalogAiRulesTests`) still PASS untouched.

- [x] **Step 3: Add the import**

In `backend/app/services/ai_reply.py`, after line 9 (`from app.services.knowledge_service import get_knowledge_context`), add:

```python
from app.services.catalog_retrieval import (
    contention_set,
    classify_gate,
    differing_attribute_directive,
    broad_browse_directive,
    match_catalog_items,
)
```

- [x] **Step 4: Rewrite `_build_catalog_context`**

Replace `backend/app/services/ai_reply.py:747-796` (the current `_build_catalog_context` function) with:

```python
async def _build_catalog_context(db, tenant_id: str, message: str) -> tuple[str, list[dict], dict[str, dict], int]:
    """Fetch relevant catalog items for this message and build the prompt context + tool
    definitions, gating disambiguation when multiple variants of one item are in contention.

    Returns (catalog_text_block, tool_definitions, items_by_id, max_images_per_reply).
    catalog_text_block is empty when no items exist or can_recommend is disabled. On any
    retrieval failure (or when nothing matches), falls back to listing every ready item --
    today's original behavior -- so a provider hiccup never blocks a reply.
    """
    rules = _load_catalog_ai_rules(db, tenant_id)
    if not rules.get("can_recommend"):
        return "", [], {}, 0

    candidates: list[dict] = []
    try:
        candidates = await match_catalog_items(db, tenant_id, message)
    except Exception as e:
        logger.warning(f"Catalog retrieval failed for tenant {tenant_id}, falling back to full catalog: {e}")

    directive = ""
    if candidates:
        contention = contention_set(candidates)
        gate = classify_gate(contention)
        if gate == "confident":
            items = [contention[0]]
        elif gate == "same_group":
            items = []
            directive = differing_attribute_directive(contention)
        else:
            items = []
            directive = broad_browse_directive(contention)
    else:
        try:
            res = (
                db.table("catalog_items")
                .select("id,name,item_type,description")
                .eq("tenant_id", tenant_id)
                .eq("status", "ready")
                .order("name")
                .execute()
            )
            items = res.data or []
        except Exception as e:
            logger.warning(f"Failed to load catalog items for tenant {tenant_id}: {e}")
            return "", [], {}, 0

    if not items and not directive:
        return "", [], {}, 0

    items_by_id = {row["id"]: row for row in items}
    item_lines: list[str] = []
    for row in items:
        line = f"  • {row['name']} ({row['item_type']}) [id: {row['id']}]"
        if row.get("description"):
            line += f" — {row['description']}"
        item_lines.append(line)

    text_block = ""
    if item_lines:
        text_block = (
            "\n\nCATALOG:\nWhen the customer asks about what's available or shows interest in a type of "
            "product/service, use your catalog below. Mention items by name — and when you do, call the "
            "recommend_catalog_item tool with the item's [id] so the customer receives its photo automatically.\n"
            + "\n".join(item_lines)
        )
    text_block += directive

    max_images = rules.get("max_images_per_reply", 3)
    tools: list[dict] = []
    if rules.get("can_send_images", True) and items:
        tools = [dict(_CATALOG_RECOMMEND_TOOL)]
        text_block += f"\n\nYou may recommend up to {max_images} item(s) with photos per reply."

    return text_block, tools, items_by_id, max_images
```

- [x] **Step 5: Update the caller in `generate_reply`**

In `backend/app/services/ai_reply.py`, replace the block at (originally) `:946-952`:

```python
    catalog_tools: list[dict] = []
    catalog_items_by_id: dict[str, dict] = {}
    try:
        catalog_context, catalog_tools, catalog_items_by_id = _build_catalog_context(db, tenant_id)
    except Exception:
        catalog_context = ""
        logger.warning(f"Catalog context build failed for tenant {tenant_id}")
```

with:

```python
    catalog_tools: list[dict] = []
    catalog_items_by_id: dict[str, dict] = {}
    catalog_max_images = 0
    try:
        catalog_context, catalog_tools, catalog_items_by_id, catalog_max_images = await _build_catalog_context(
            db, tenant_id, message
        )
    except Exception:
        catalog_context = ""
        logger.warning(f"Catalog context build failed for tenant {tenant_id}")
```

- [x] **Step 6: Enforce the hard cap at the send site**

In `backend/app/services/ai_reply.py`, replace (originally at `:1176-1178`):

```python
        if _wa_phone and sid and catalog_images_to_send:
            from app.services.meta_cloud import upload_media_to_meta, send_media_message
            for img_filename, img_bytes in catalog_images_to_send:
```

with:

```python
        if _wa_phone and sid and catalog_images_to_send:
            from app.services.meta_cloud import upload_media_to_meta, send_media_message
            for img_filename, img_bytes in catalog_images_to_send[:catalog_max_images]:
```

- [x] **Step 7: Run the tests to verify they pass**

Run: `cd backend && pytest tests/test_catalog.py -v`
Expected: every test in the file PASSES, including all of `CatalogAiReplyIntegrationTests` and `CatalogImageCapEnforcementTests`.

- [x] **Step 8: Run the full backend suite for regressions**

Run: `cd backend && pytest -v`
Expected: no new failures anywhere else in the suite (in particular `test_ai_reply_lang_detection.py`, `test_ai_reply_llm_wiring.py`, `test_ai_reply_quota_enforcement.py` must still pass unchanged).

- [x] **Step 9: Commit**

```bash
git add backend/app/services/ai_reply.py backend/tests/test_catalog.py
git commit -m "feat: gate AI catalog recommendations through semantic disambiguation, enforce image cap"
```

**Fix round 1 (post-review):** `classify_gate` was found to incorrectly gate legacy/ungrouped tenants (all `variant_group_id: None`) into `"broad_browse"`, contradicting the backward-compatibility constraint. Fixed: all-`None` group_ids now classify as `"confident"` (recommend top match, no clarifying question); `broad_browse`/`same_group` only trigger once real grouping data exists among the contention set. Separately, `max_images_per_reply` (read from an unvalidated settings payload, used as a slice bound) is now coerced: `max_images = max(0, int(rules.get("max_images_per_reply", 3)))` wrapped in `try/except (TypeError, ValueError)` falling back to `3`. Both fixes were approved by the human owner after being surfaced as plan-mandated findings, and both are re-reviewed and confirmed correct with non-vacuous regression tests.

---

### Task 5: Accept attributes/variant grouping on write, embed on create/update, add reindex route

**Files:**
- Modify: `backend/app/routes/catalog.py:31-72` (`create_item`, `update_item`), append a new `POST /reindex` route
- Modify: `backend/tests/test_catalog.py` (add tests for the new fields and the reindex route)

**Interfaces:**
- Consumes: Task 3's `embed_and_store_catalog_item`, `reindex_catalog_items` from `app.services.catalog_retrieval`.
- Produces: `POST /api/v1/catalog/reindex` → `{"success": true, "items_embedded": int, "items_total": int}`.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_catalog.py`, inside `CatalogItemsTests` (after `test_create_item_defaults_to_draft_status`):

```python
    @patch("app.routes.catalog.embed_and_store_catalog_item")
    @patch("app.routes.catalog.get_supabase")
    def test_create_item_accepts_attributes_and_variant_group_and_embeds(self, mock_get_db, mock_embed):
        db = MagicMock()
        db.table.return_value.insert.return_value.execute.return_value.data = [
            {"id": "item-1", "name": "2BHK Apartment", "item_type": "property", "status": "draft",
             "attributes": {"location": "Coimbatore"}, "variant_group_id": "vg-1"}
        ]
        mock_get_db.return_value = db
        mock_embed.return_value = None

        res = self.client.post(
            "/api/v1/catalog/items",
            json={
                "name": "2BHK Apartment", "item_type": "property",
                "attributes": {"location": "Coimbatore"}, "variant_group_id": "vg-1",
            },
        )

        self.assertEqual(res.status_code, 200)
        insert_call = db.table.return_value.insert.call_args[0][0]
        self.assertEqual(insert_call["attributes"], {"location": "Coimbatore"})
        self.assertEqual(insert_call["variant_group_id"], "vg-1")
        mock_embed.assert_called_once()

    @patch("app.routes.catalog.embed_and_store_catalog_item")
    @patch("app.routes.catalog.get_supabase")
    def test_create_item_embedding_failure_does_not_fail_the_request(self, mock_get_db, mock_embed):
        db = MagicMock()
        db.table.return_value.insert.return_value.execute.return_value.data = [
            {"id": "item-1", "name": "New Item", "item_type": "product", "status": "draft"}
        ]
        mock_get_db.return_value = db
        mock_embed.side_effect = Exception("jina down")

        res = self.client.post("/api/v1/catalog/items", json={"name": "New Item", "item_type": "product"})
        self.assertEqual(res.status_code, 200)
```

Add a new test class at the end of the file, before `if __name__ == "__main__":`:

```python
class CatalogReindexTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}
        app.dependency_overrides[get_tenant_id] = lambda: "tenant-1"
        app.dependency_overrides[get_tenant_and_role] = lambda: {"tenant_id": "tenant-1", "role": "owner"}

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("app.routes.catalog.reindex_catalog_items")
    def test_reindex_returns_counts(self, mock_reindex):
        async def fake_reindex(tenant_id):
            return {"items_embedded": 2, "items_total": 3}

        mock_reindex.side_effect = fake_reindex

        res = self.client.post("/api/v1/catalog/reindex")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"success": True, "items_embedded": 2, "items_total": 3})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && pytest tests/test_catalog.py -v`
Expected: the new tests FAIL — `app.routes.catalog.embed_and_store_catalog_item`/`reindex_catalog_items` don't exist as importable names in that module yet, `attributes`/`variant_group_id` aren't accepted, and `/reindex` 404s.

- [ ] **Step 3: Update `create_item` and `update_item`**

In `backend/app/routes/catalog.py`, add this import near the top (after the existing imports, before `logger = logging.getLogger(__name__)`):

```python
from app.services.catalog_retrieval import embed_and_store_catalog_item, reindex_catalog_items
```

Replace the `create_item` function (originally `:31-47`):

```python
@router.post("/items")
async def create_item(
    payload: dict,
    tenant_id: str = Depends(get_tenant_id),
    _ctx: dict = Depends(require_catalog_manage),
):
    db = get_supabase()
    res = db.table("catalog_items").insert({
        "tenant_id": tenant_id,
        "name": payload.get("name"),
        "item_type": payload.get("item_type") or "product",
        "description": payload.get("description"),
        "status": "draft",
        "attributes": payload.get("attributes") or {},
        "variant_group_id": payload.get("variant_group_id"),
    }).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="Failed to create catalog item")
    item = res.data[0]
    try:
        await embed_and_store_catalog_item(
            db, tenant_id, item["id"], item["name"], item["item_type"],
            item.get("description"), item.get("attributes") or {},
        )
    except Exception as e:
        logger.warning(f"Failed to embed catalog item {item['id']}: {e}")
    return item
```

Replace the `update_item` function (originally `:50-72`):

```python
@router.patch("/items/{item_id}")
async def update_item(
    item_id: UUID,
    payload: dict,
    tenant_id: str = Depends(get_tenant_id),
    _ctx: dict = Depends(require_catalog_manage),
):
    db = get_supabase()
    updates = {
        k: v for k, v in payload.items()
        if k in {"name", "item_type", "description", "status", "attributes", "variant_group_id"}
    }
    if "status" in updates and updates["status"] not in _VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of {_VALID_STATUSES}")
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()

    res = (
        db.table("catalog_items")
        .update(updates)
        .eq("id", str(item_id))
        .eq("tenant_id", tenant_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Catalog item not found")
    item = res.data[0]
    if {"name", "item_type", "description", "attributes"} & updates.keys():
        try:
            await embed_and_store_catalog_item(
                db, tenant_id, item["id"], item["name"], item["item_type"],
                item.get("description"), item.get("attributes") or {},
            )
        except Exception as e:
            logger.warning(f"Failed to re-embed catalog item {item['id']}: {e}")
    return item
```

- [ ] **Step 4: Add the reindex route**

At the end of `backend/app/routes/catalog.py`, after the `update_ai_rules` function, add:

```python
@router.post("/reindex")
async def reindex_catalog(
    tenant_id: str = Depends(get_tenant_id),
    _ctx: dict = Depends(require_catalog_manage),
):
    """Backfill embeddings for existing catalog items (run once after grouping variants)."""
    result = await reindex_catalog_items(tenant_id)
    return {"success": True, **result}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd backend && pytest tests/test_catalog.py -v`
Expected: every test in the file PASSES.

- [ ] **Step 6: Run the full backend suite for regressions**

Run: `cd backend && pytest -v`
Expected: no new failures.

- [ ] **Step 7: Commit**

```bash
git add backend/app/routes/catalog.py backend/tests/test_catalog.py
git commit -m "feat: accept catalog attributes/variant grouping, embed on write, add reindex endpoint"
```

---

## Post-Plan Follow-Ups (not in scope here)

- Frontend: add a "Variant group" picker and key/value "Attributes" editor to `dashboard/catalog/page.tsx`'s `AddItemModal`/item rows, plus a "Reindex catalog" button calling `POST /api/v1/catalog/reindex` (mirrors the Knowledge Base's existing reindex button pattern, if one exists in `dashboard/.../knowledge`).
- Consider surfacing `catalog_retrieval_mode` (semantic/keyword/hybrid) as a per-tenant setting mirroring `kb_retrieval_mode`, if a tenant's catalog text turns out to need exact-token matching alongside semantic — not needed for the initial rollout.
