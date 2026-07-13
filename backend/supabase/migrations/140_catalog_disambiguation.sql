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
