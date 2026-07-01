-- Migration 125: contact/business metadata on tenants
alter table tenants add column if not exists business_type text;
alter table tenants add column if not exists contact_name text;
alter table tenants add column if not exists contact_phone text;
alter table tenants add column if not exists billing_region text;
