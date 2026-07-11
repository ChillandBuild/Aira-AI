create table if not exists public.tenant_roles (
    id uuid primary key default gen_random_uuid(),
    tenant_id uuid not null references public.tenants(id) on delete cascade,
    name text not null,
    slug text null,
    description text null,
    permissions text[] not null default '{}',
    is_system_template boolean not null default false,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (tenant_id, name),
    unique (tenant_id, slug)
);

alter table public.tenant_users add column if not exists role_id uuid references public.tenant_roles(id) on delete set null;
alter table public.tenant_users add column if not exists full_name text;
alter table public.tenant_users add column if not exists force_password_reset boolean not null default false;
alter table public.tenant_users add column if not exists temporary_password_issued_at timestamptz;

create index if not exists tenant_roles_tenant_id_idx on public.tenant_roles(tenant_id);
create index if not exists tenant_users_role_id_idx on public.tenant_users(role_id);

grant usage on schema public to authenticated, service_role;
grant select, insert, update, delete on public.tenant_roles to authenticated, service_role;
grant select, insert, update, delete on public.tenant_users to authenticated, service_role;

insert into public.tenant_roles (tenant_id, name, slug, description, permissions, is_system_template)
select
    t.id,
    'Telecaller',
    'telecaller',
    null,
    array['dashboard.view', 'conversations.view', 'telecalling.dialer', 'telecalling.scheduled', 'telecalling.notes'],
    true
from public.tenants t
where not exists (
    select 1 from public.tenant_roles r where r.tenant_id = t.id and r.slug = 'telecaller'
);

update public.tenant_users tu
set role_id = tr.id
from public.tenant_roles tr
where tu.tenant_id = tr.tenant_id
  and tr.slug = 'telecaller'
  and tu.role = 'caller'
  and tu.role_id is null;

alter table if exists public.tenant_roles enable row level security;

drop policy if exists tenant_roles_member_select on public.tenant_roles;
create policy tenant_roles_member_select
on public.tenant_roles for select
to authenticated
using (public.is_tenant_member(tenant_id));

drop policy if exists tenant_roles_owner_write on public.tenant_roles;
create policy tenant_roles_owner_write
on public.tenant_roles for all
to authenticated
using (public.is_tenant_owner(tenant_id))
with check (public.is_tenant_owner(tenant_id));

notify pgrst, 'reload schema';
