-- Migration 126: close schema drift — callers.status used by code but never migrated
alter table callers add column if not exists status text default 'active';
