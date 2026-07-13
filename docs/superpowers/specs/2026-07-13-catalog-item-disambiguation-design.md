# Catalog Item Disambiguation via Semantic Retrieval — Design

## Context

`backend/app/services/ai_reply.py` lets the AI recommend catalog items (`catalog_items` /
`catalog_media`, migration `136_catalog_items.sql`) and auto-send their photos over WhatsApp. This
was traced end-to-end and has two related gaps:

- **No disambiguation.** `_build_catalog_context()` (`ai_reply.py:747-796`) dumps every `status='ready'`
  item into the system prompt verbatim, and `_CATALOG_RECOMMEND_TOOL` (`ai_reply.py:703-724`) only
  asks the model, in prose, to "not call more than once per reply." Nothing detects that a query like
  "send me 2BHK apartment photos" or "show me chocolate cake pics" matches several catalog items that
  differ by one attribute (city, flavor, size) rather than matching one clear item. The schema has no
  place to even represent that relationship — `catalog_items` (migration 136) has only `name`,
  `item_type`, `description`, `status`.
- **No enforced cap.** The tool-call loop (`ai_reply.py:1021-1060`) processes every `tool_calls` entry
  the model returns with no count limit, and the send loop (`ai_reply.py:1176-1178`) sends every entry
  in `catalog_images_to_send`. `AI Rules -> max_images_per_reply` (`routes/catalog.py:194-233`,
  frontend `dashboard/catalog/page.tsx:456-534`) is only ever used to word the prompt
  (`ai_reply.py:794`) — it is never enforced in code. If the model emits 3 tool calls for 3 cities, all
  3 photos go out.

This is a platform-wide gap: any tenant whose catalog naturally has "the same thing, several
variants" (real estate by city, bakery by flavor/size, courses by batch, salons by service tier) can
hit it, not just real estate.

Separately, this codebase already has a mature RAG pipeline for the unrelated "Knowledge Base"
feature (`backend/app/services/knowledge_service.py`, `embeddings.py`, migration
`087_knowledge_rag.sql`): Jina `jina-embeddings-v3` embeddings truncated to 512 dims, a
`pgvector` `knowledge_chunks.embedding vector(512)` column with an HNSW cosine index, a
`match_knowledge_chunks` Postgres RPC, and a hybrid semantic+keyword retrieval mode merged via
Reciprocal Rank Fusion (`_rrf_merge`, `knowledge_service.py:239`), with an explicit fail-open
guarantee: *"Always falls back to full-text injection when the query is empty, retrieval errors, or
nothing matches — a provider hiccup must never blank the knowledge base"* (`knowledge_service.py:265-266`).
This design reuses that infrastructure rather than introducing a second embedding provider or a
parallel retrieval stack.

## Goals

- When a customer's message matches multiple catalog items that are variants of the same underlying
  thing (differing only in an attribute like city/flavor/size), the AI asks a clarifying question
  naming the real differentiating values, instead of guessing or sending every matching photo.
- When the message matches one item clearly, or a follow-up narrows a prior clarifying question, the
  AI recommends that one item as it does today.
- When a message is a broad category browse across genuinely different products (not variants of one
  thing), the AI lists the distinct options as text and asks which one — it does not send any images
  until narrowed (confirmed: this is the desired behavior, not a carousel/preview of one photo per
  group).
- `max_images_per_reply` becomes a real, code-enforced cap regardless of how many tool calls the model
  emits, closing the current unbounded-send gap.
- Fully backward compatible: tenants who never group their items keep exactly today's behavior (no
  ambiguity possible without a group to be ambiguous within).
- A provider/embedding failure degrades gracefully to today's "list everything" behavior for that
  turn — it must never block a reply.

## Non-Goals

- No changes to the Knowledge Base RAG pipeline itself — it is reused, not modified.
- No new embedding provider — reuses `app/services/embeddings.py` (Jina v3, 512-dim) as-is.
- Frontend variant-group/attribute editor UI is a fast-follow, not required for the backend gate to
  function (tenants can be onboarded onto grouping via a support-assisted data entry initially).
- No change to WhatsApp message type — clarifying questions are plain AI-generated text (per
  decision), not native interactive list/button messages.

## Schema Changes

New migration (next number after the current max in `backend/supabase/migrations/`, verified at
implementation time — do not hardcode 137 here, the sequence moves fast):

```sql
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

-- Mirrors match_knowledge_chunks (087_knowledge_rag.sql) exactly, scoped to ready items.
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

`attributes` is an open `jsonb` bag (`{"location": "Coimbatore"}`, `{"flavor": "dark chocolate",
"size": "1kg"}`) rather than fixed columns, because catalog verticals are tenant-defined (real
estate, bakery, courses, salons, ...) and a rigid schema would force a migration per vertical.

## Retrieval and Disambiguation Flow

Replace `_build_catalog_context()`'s "load every ready item into the prompt" with a per-turn
retrieval + gate step, invoked from `generate_reply()` where `_build_catalog_context` is currently
called (`ai_reply.py:948-952`):

1. **Embed the query.** `embed_query(message)` (`embeddings.py:65-68`, reused as-is).
2. **Retrieve candidates.** Call `match_catalog_items` RPC (top-K, default 5). If a tenant-level
   `catalog_retrieval_mode` setting is `hybrid` (mirroring `kb_retrieval_mode`,
   `knowledge_service.py:260-263,276-278`), also run a cheap `ILIKE` keyword prefilter over
   `catalog_items.name` and merge both lists with `_rrf_merge`-equivalent logic. Default mode is
   `semantic`.
3. **Compute the contention set.** Let `top = candidates[0].similarity`. The contention set is every
   candidate whose similarity is within `CONFIDENT_MARGIN` (default `0.08`, tunable constant) of
   `top` — i.e. `candidates[i].similarity >= top - CONFIDENT_MARGIN`. If fewer than 2 candidates
   exist, or the contention set has size 1, that single item is trivially unambiguous.
4. **Gate decision**, based on the contention set:
   - **Confident single match** (contention set size 1) → only `candidates[0]` is passed into the
     catalog prompt block and the `recommend_catalog_item` tool's implicit item set — the model has
     nothing else to recommend.
   - **Ambiguous within one group** (contention set size >= 2, and every member shares the same
     non-null `variant_group_id`) → the `recommend_catalog_item` tool is **not** offered this turn.
     Instead, inject a directive built from real data: the distinct values of the attribute key that
     differs across the contention set's `attributes` (e.g. `location:
     Coimbatore/Chennai/Salem`), instructing the model to ask which one before anything is
     recommended.
   - **Broad browse across groups** (contention set size >= 2, spanning 2+ distinct
     `variant_group_id`s, or a mix of grouped/ungrouped items) → tool also withheld; directive lists
     the distinct item/group names from the contention set as plain options and asks which the
     customer wants — zero images sent this turn (confirmed behavior, no per-group photo preview).
5. **Next turn.** A follow-up message ("Chennai please") re-runs the same retrieval; the added
   specificity should produce a confident single match, falling into the first branch.

## Enforced Image Cap (independent of the gate)

Regardless of gate outcome, `ai_reply.py:1176-1178`'s send loop is changed from sending all of
`catalog_images_to_send` to slicing it: `catalog_images_to_send[:rules.get("max_images_per_reply",
3)]`. This is defense-in-depth — the gate should make multi-recommend rare, but the cap must hold
even if gate logic has a bug or the model ignores its instructions, exactly the failure mode that
prompted this design.

## Failure Handling

Mirrors `get_knowledge_context`'s fail-open contract (`knowledge_service.py:254-309`) exactly:

- Embedding call fails, RPC errors, or nothing matches → log a warning (existing style,
  `ai_reply.py:768` pattern) and fall back to today's behavior: dump all ready items into the prompt,
  offer the tool for all of them, no gate. A provider hiccup must never block a reply.
- The hard image cap still applies even on the fallback path.

## Rollout

- Fully additive migration — existing `catalog_items` rows get `attributes = {}`,
  `variant_group_id = null`, `embedding = null`. With no group and no embedding, they fall through to
  the fail-open "no embedding" path (equivalent to today's full-dump behavior) until backfilled.
- **Backfill:** new `reindex_catalog_items(tenant_id)` in a catalog-equivalent of
  `knowledge_service.reindex_tenant()` (`knowledge_service.py:312`) — embeds `name + item_type +
  description + attributes` for every `status='ready'` item lacking an embedding.
- **New/updated items:** `routes/catalog.py::create_item` / `update_item` synchronously call
  `embed_texts([...], input_type="document")` and store the result via `to_pgvector()`, mirroring
  `_index_chunks` (`knowledge_service.py:51-67`).
- **Frontend:** Items tab (`dashboard/catalog/page.tsx`) fast-follow adds an optional "Variant group"
  picker and a key/value "Attributes" editor on `AddItemModal` / item rows. Not required to ship the
  backend gate — a tenant with zero groups simply never hits the ambiguous branches.

## Testing

- **Unit** (pure functions, no DB): margin computation, group-membership classification, cap
  slicing — feed fixture similarity-score lists covering all three gate branches plus the "fewer
  than 2 candidates" trivial case.
- **Integration:** seed 3 items under one `variant_group_id` with distinct `attributes.location`;
  mock the Jina embedding response; assert an ambiguous query withholds the tool and the injected
  directive lists all 3 locations; assert a follow-up with a location mention resolves to exactly one
  tool call and one sent image.
- **Regression:** a tenant with only ungrouped legacy items must produce byte-identical behavior to
  today (single best match offered, or full-dump on embedding failure) — no new clarifying questions
  should appear for tenants who were never grouped.
- **Cap enforcement:** construct a case where the model (mocked) returns 3 `recommend_catalog_item`
  tool calls in one response; assert only `max_images_per_reply` images are actually sent.
