-- Migration 136: Catalog items + media for AI-recommendable products/services/properties/courses
create table if not exists catalog_items (
    id uuid primary key default gen_random_uuid(),
    tenant_id uuid references tenants(id) on delete cascade not null,
    name text not null,
    item_type text not null default 'product',
    description text,
    status text not null default 'draft' check (status in ('draft', 'ready')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
alter table catalog_items enable row level security;
create policy "Tenant members can manage their catalog items" on catalog_items
    for all using (tenant_id = (select tenant_id from tenant_users where user_id = auth.uid() limit 1));
create index if not exists idx_catalog_items_tenant on catalog_items(tenant_id);

create table if not exists catalog_media (
    id uuid primary key default gen_random_uuid(),
    tenant_id uuid references tenants(id) on delete cascade not null,
    catalog_item_id uuid references catalog_items(id) on delete cascade not null,
    storage_path text not null,
    label text,
    created_at timestamptz not null default now()
);
alter table catalog_media enable row level security;
create policy "Tenant members can manage their catalog media" on catalog_media
    for all using (tenant_id = (select tenant_id from tenant_users where user_id = auth.uid() limit 1));
create index if not exists idx_catalog_media_item on catalog_media(catalog_item_id);

insert into storage.buckets (id, name, public)
values ('catalog-media', 'catalog-media', true)
on conflict (id) do nothing;

create policy "Allow authenticated users to upload catalog media"
on storage.objects for insert
with check (bucket_id = 'catalog-media' and auth.role() = 'authenticated');

create policy "Allow public read access to catalog media"
on storage.objects for select
using (bucket_id = 'catalog-media');

create policy "Allow authenticated users to delete catalog media"
on storage.objects for delete
using (bucket_id = 'catalog-media' and auth.role() = 'authenticated');
