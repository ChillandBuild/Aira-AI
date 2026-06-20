# Spec: Feature Flags Operator Console

> 19 nodes · cohesion 0.16

## Key Concepts

- **RLS Storage Audit Hardening Plan** (13 connections) — `docs/superpowers/plans/2026-05-31-rls-storage-audit-hardening.md`
- **Production SaaS Hardening Plan (2026-05-30)** (7 connections) — `docs/superpowers/plans/2026-05-30-production-saas-hardening.md`
- **Operator Console (System Admin Client Provisioning UI)** (5 connections) — `docs/superpowers/plans/2026-05-19-feature-flags-operator-console.md`
- **Feature Flags + Operator Console Plan (2026-05-19)** (4 connections) — `docs/superpowers/plans/2026-05-19-feature-flags-operator-console.md`
- **X-Hub-Signature-256 Webhook Verification** (4 connections) — `CLAUDE.md`
- **Application Audit Log (app_audit_logs — Immutable Events)** (3 connections) — `docs/superpowers/plans/2026-05-31-rls-storage-audit-hardening.md`
- **enabled_features (Tenant Feature Flags Array)** (3 connections) — `docs/superpowers/plans/2026-05-19-feature-flags-operator-console.md`
- **system_admins Table (Super-Admin Gate)** (3 connections) — `docs/superpowers/plans/2026-05-19-feature-flags-operator-console.md`
- **Service Tier (whatsapp_only / telecalling_only / combined)** (3 connections) — `docs/superpowers/plans/2026-05-19-feature-flags-operator-console.md`
- **RLS as Defense in Depth (Not Live Toggle)** (2 connections) — `docs/superpowers/plans/2026-05-30-production-saas-hardening.md`
- **Migration 072 (Security Hardening — audit logs, RLS, storage)** (2 connections) — `docs/superpowers/plans/2026-05-30-production-saas-hardening.md`
- **Supabase Schema Reconciliation Audit** (2 connections) — `docs/superpowers/audits/2026-06-06-supabase-schema-reconciliation.md`
- **Local vs Live Migration Drift** (2 connections) — `docs/superpowers/audits/2026-06-06-supabase-schema-reconciliation.md`
- **Supabase Project ayftynkgmfkaqmmnlmoc** (2 connections) — `docs/superpowers/audits/2026-06-06-supabase-schema-reconciliation.md`
- **broadcast-csvs Bucket Made Private (No Public URL)** (1 connections) — `docs/superpowers/plans/2026-05-31-rls-storage-audit-hardening.md`
- **Razorpay Idempotency Key (booking:{id}:payment_link)** (1 connections) — `docs/superpowers/plans/2026-05-30-production-saas-hardening.md`
- **TeleCMI Webhook Shared-Secret Guard (x-aira-webhook-secret)** (1 connections) — `docs/superpowers/plans/2026-05-30-production-saas-hardening.md`
- **Public→Signed URL CSV Migration** (1 connections) — `docs/superpowers/plans/2026-05-31-rls-storage-audit-hardening.md`
- **app_audit_logs (non-blocking)** (1 connections) — `docs/superpowers/plans/2026-05-31-rls-storage-audit-hardening.md`

## Relationships

- [[Spec: Bot Flow Builder Phase2]] (1 shared connections)

## Source Files

- `CLAUDE.md`
- `docs/superpowers/audits/2026-06-06-supabase-schema-reconciliation.md`
- `docs/superpowers/plans/2026-05-19-feature-flags-operator-console.md`
- `docs/superpowers/plans/2026-05-30-production-saas-hardening.md`
- `docs/superpowers/plans/2026-05-31-rls-storage-audit-hardening.md`

## Audit Trail

- EXTRACTED: 56 (93%)
- INFERRED: 4 (7%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*