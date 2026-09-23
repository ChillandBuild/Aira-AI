-- AUDIT-2026-09.md finding C7 (Critical): catalog-media storage policies.
--
-- Migration 136 created two write policies on storage.objects that only checked
-- auth.role() = 'authenticated', with no check that the object's path -- which the
-- backend always writes as {tenant_id}/{item_id}/{uuid}_{filename} (routes/catalog.py) --
-- belonged to a tenant the caller is actually a member of. Any logged-in user of ANY
-- tenant could upload to or delete any OTHER tenant's catalog photos directly through
-- the Supabase Storage API (the FastAPI backend was never in the loop; it uses the
-- service-role client, which bypasses RLS regardless of this policy).
--
-- Public SELECT is intentional and UNCHANGED here: catalog photos are sent to leads
-- over WhatsApp via a public URL (get_public_url in routes/catalog.py), so Meta's
-- servers must be able to fetch them with no auth. Only INSERT/DELETE are scoped.
--
-- (storage.foldername(name))[1] is the first path segment -- the tenant_id the
-- backend always writes first. The regex check comes before the uuid cast so a
-- malformed/legacy path can never raise a cast error inside the policy; it just
-- fails the check like any other mismatch.

drop policy if exists "Allow authenticated users to upload catalog media" on storage.objects;
drop policy if exists "Allow authenticated users to delete catalog media" on storage.objects;

create policy "Tenant members can upload their own catalog media" on storage.objects
  for insert to authenticated
  with check (
    bucket_id = 'catalog-media'
    and (storage.foldername(name))[1] ~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
    and public.is_tenant_member((storage.foldername(name))[1]::uuid)
  );

create policy "Tenant members can delete their own catalog media" on storage.objects
  for delete to authenticated
  using (
    bucket_id = 'catalog-media'
    and (storage.foldername(name))[1] ~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
    and public.is_tenant_member((storage.foldername(name))[1]::uuid)
  );
