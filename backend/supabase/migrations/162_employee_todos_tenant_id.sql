-- 162_employee_todos_tenant_id.sql
-- employee_todos was created (migration 027) without a tenant_id column,
-- but routes/todos.py filters/inserts on tenant_id everywhere -- every
-- /api/v1/todos call 500s in production ("column employee_todos.tenant_id
-- does not exist"). Add + backfill it, same pattern migration 114 used for
-- conversations.tenant_id.

alter table public.employee_todos
    add column if not exists tenant_id uuid references public.tenants(id);

update public.employee_todos et
set tenant_id = tu.tenant_id
from public.tenant_users tu
where tu.user_id = et.user_id
  and et.tenant_id is null;

create index if not exists idx_employee_todos_tenant_id on public.employee_todos(tenant_id);
