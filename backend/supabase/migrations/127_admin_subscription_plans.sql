-- Migration 127: Admin-customizable subscription plans (single plan per tenant)
--
-- Replaces the 6 hardcoded messaging/telecalling/ai_tier plans with a single
-- admin-authored `plans` table (name, price, feature checklist, quotas).
-- Verified against live data before writing this: `tenant_subscriptions` has
-- zero rows, so no tenant currently references any plan -- safe to drop the
-- seed rows and old columns without a data backfill.

-- tenant_subscriptions: single plan_id replaces the three old plan/tier fields
alter table tenant_subscriptions add column if not exists plan_id uuid references plans(id) on delete set null;
alter table tenant_subscriptions drop column if exists messaging_plan_id;
alter table tenant_subscriptions drop column if exists telecalling_plan_id;
alter table tenant_subscriptions drop column if exists ai_tier;
alter table tenant_subscriptions drop column if exists custom_overrides;

-- plans: delete the 6 seed rows (confirmed nothing in tenant_subscriptions
-- references them) so the table starts genuinely empty for the admin.
delete from plans;

-- plans: new shape -- a flat feature checklist + canonical usage-metric quotas
alter table plans drop column if exists pillar;
alter table plans drop column if exists tier;
alter table plans drop column if exists ai_tier;
alter table plans drop column if exists included;
alter table plans add column if not exists feature_keys jsonb not null default '[]';
alter table plans add column if not exists quotas jsonb not null default '{}';
