# Unified Meta Business Onboarding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect WhatsApp, Messenger, Instagram and optional read-only ads analytics through one Meta signup popup.

**Architecture:** A unified start endpoint exchanges the one-time Meta code and stores it with WhatsApp signup metadata server-side. It returns safe Page/ad-account options. A completion endpoint re-discovers and validates the chosen assets, saves all credentials and subscriptions, then clears the temporary session. The dashboard launches one new Meta configuration ID and uses the existing asset-choice dialog without catalog selection.

**Tech Stack:** Next.js/TypeScript, FastAPI/Pydantic, Supabase app settings/RPC, Meta Graph API.

## Global Constraints

- Configuration ID: `2026693308738446`.
- Use only `ads_read`; do not introduce Meta ad creation or catalog integration.
- Meta tokens stay server-side.
- Preserve legacy manual and separate embedded-signup endpoints.

---

### Task 1: Backend unified signup contract

**Files:**
- Modify: `backend/app/routes/app_settings.py`
- Modify: `backend/tests/test_facebook_embedded_signup.py`

**Interfaces:**
- Consumes: Meta OAuth `code`, `waba_id`, `phone_number_id`, optional `business_id` and `is_coexistence`.
- Produces: `POST /settings/meta/unified-signup/start` returning `session_id`, safe `pages`, and safe `ad_accounts`; `POST /settings/meta/unified-signup/complete` persists selected assets.

- [ ] **Step 1: Write failing tests** for the unified start response and completion side effects.
- [ ] **Step 2: Run tests** and confirm they fail because the unified API does not exist.
- [ ] **Step 3: Implement minimal staging and completion handlers**, sharing existing Meta Graph helpers and preserving access tokens only in app settings.
- [ ] **Step 4: Run targeted backend tests** and confirm they pass.

### Task 2: Atomic Meta asset ownership

**Files:**
- Modify: `backend/supabase/migrations/162_meta_asset_claims.sql`
- Modify: `backend/app/routes/app_settings.py`
- Test: `backend/tests/test_facebook_embedded_signup.py`

**Interfaces:**
- Consumes: selected Page, linked Instagram account, WhatsApp business account/phone number, and optional ad account.
- Produces: one atomic `claim_meta_assets` call before credentials are persisted.

- [ ] **Step 1: Write a failing test** that expects WhatsApp assets in the ownership claim.
- [ ] **Step 2: Run it** and confirm the expected missing-claim failure.
- [ ] **Step 3: Expand the migration validation and unified claim construction** for WhatsApp assets.
- [ ] **Step 4: Run targeted backend tests** and confirm they pass.

### Task 3: One dashboard connection journey

**Files:**
- Modify: `frontend/app/dashboard/settings/ConnectChannelsPanel.tsx`

**Interfaces:**
- Consumes: one Meta popup result plus `WA_EMBEDDED_SIGNUP` finish event.
- Produces: one connection action using configuration `2026693308738446`, then a Page/optional-ad choice dialog.

- [ ] **Step 1: Add a focused failing UI contract where practical; otherwise use typecheck as the browser-integration guard.**
- [ ] **Step 2: Replace the two popup launch paths with one unified launch path.**
- [ ] **Step 3: Remove catalog selection/copy and label ads as analytics only.**
- [ ] **Step 4: Run lint and typecheck.**

### Task 4: Verify and hand off

**Files:**
- Modify: relevant tests and docs only if verification identifies a defect.

- [ ] **Step 1: Run the focused backend Meta tests.**
- [ ] **Step 2: Run frontend lint, typecheck, and production build.**
- [ ] **Step 3: Review the diff for token leaks and regressions.**
- [ ] **Step 4: Provide the exact owner-account manual test checklist.**
