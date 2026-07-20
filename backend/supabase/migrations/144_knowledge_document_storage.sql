-- Knowledge document viewing: keep the original uploaded file so clients can download it,
-- and expose the extracted text they can already read.
--
-- Before this, upload_document read the file into memory, extracted full_text, and let the
-- bytes go -- the original was never persisted. Documents uploaded BEFORE this migration
-- have storage_path = NULL and can only ever show extracted text; only re-uploading gives
-- them a downloadable original.

alter table knowledge_documents
  add column if not exists storage_path text;

-- Private bucket, same shape as broadcast-csvs: no policies are created, so anon and
-- authenticated clients are denied. The backend reaches it with the service role (which
-- bypasses RLS) and hands out short-lived signed URLs.
insert into storage.buckets (id, name, public)
values ('knowledge-documents', 'knowledge-documents', false)
on conflict (id) do nothing;
