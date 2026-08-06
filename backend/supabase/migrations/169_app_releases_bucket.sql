-- Migration 169: Public storage bucket for distributing the Aira Sync Android APK
-- (sideload-only, not on Play Store — see decisions/log.md 2026-07-02)
insert into storage.buckets (id, name, public)
values ('app-releases', 'app-releases', true)
on conflict (id) do nothing;

create policy "Allow public read access to app releases"
on storage.objects for select
using (bucket_id = 'app-releases');
