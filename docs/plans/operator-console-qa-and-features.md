# Operator Console — QA Fixes + New Features

Execution plan for the operator console (`frontend/app/operator/(console)`, backend `backend/app/routes/operator.py`). Order: safety fixes first, then the custom toggle, then QA polish, then new features. Impersonation is last and gated behind a security review.

## Global Constraints (bind every task)

- **Stack:** Next.js 14 App Router (`frontend/`), FastAPI (`backend/app/`), Supabase (Postgres + Auth), TypeScript strict.
- **Every operator backend route** already requires `is_system_admin` via the existing dependency in `backend/app/routes/operator.py`. Any NEW operator route MUST use the same admin guard used by existing routes in that file — copy the exact dependency, never invent a looser one. Never expose operator data without it.
- **Design tokens only.** Use the existing semantic classes: `text-ink`, `text-ink-secondary`, `text-ink-muted`, `bg-primary`, `bg-primary-light`, `bg-primary-muted`, `text-primary`, `bg-surface-mid`, `bg-background`, `border-border`, `border-border-subtle`, `rounded-card`, `shadow-card`, `text-success`/`text-danger`/`text-warning`. Do NOT introduce raw Tailwind grays (`text-gray-900`, `#5b21b6` literals) in new/edited code — the scheduler page currently violates this and must be brought in line when touched.
- **No native `alert()`/`confirm()`/`prompt()`** in the operator console. Use in-app modal components (reuse `client/[id]/components/confirm-dialog.tsx` pattern or a shared confirm).
- **API access:** frontend uses `getAuthHeaders()` / `API_URL` from `@/lib/api`. Prefer the shared operator fetch helper introduced in Task 4 over per-file re-declarations once it exists.
- **Accessibility:** any interactive element must be keyboard-operable (button, or `role`+`tabIndex`+key handler) and have an accessible label.
- **Tests:** frontend has `npm run typecheck` and `npm run lint` (run from `frontend/`). Backend has `pytest` (run from `backend/`). Each task must leave typecheck + lint clean for touched frontend files, and pytest green for touched backend routes. Where a pure function is added (e.g. health scoring, debounce), add a unit test.
- Do not break existing operator functionality. Preserve all current props/behavior unless the task says to change it.

---

## Task 1: Safety — auth-check resilience + correct sign-out redirect

**Files:** `frontend/app/operator/(console)/layout.tsx`, `frontend/app/operator/(console)/components/operator-sidebar.tsx`

**Problem A — layout ejects operators on transient backend failure.** `layout.tsx` calls `/api/v1/operator/me`; today ANY failure (network error, 500, 502, timeout) falls into `catch {}` and `redirect("/dashboard")`, so a Render cold-start boots a logged-in admin out of the console. Only a genuine "not an admin" (a successful response with `is_system_admin === false`, or a 401/403) should redirect to `/dashboard`.

Requirements:
- Distinguish auth failure from infra failure. If the `me` fetch returns ok and `is_system_admin` is false → `redirect("/dashboard")` (unchanged). If it returns 401/403 → `redirect("/operator/login")`.
- If the fetch throws (network/abort) or returns a 5xx/timeout, do NOT redirect. Render a lightweight "Can't reach the server — retry" fallback UI (server component may render a small client retry component, or render children with a non-blocking banner is NOT acceptable because that would leak the console to a possibly-unauthorized user — so render a dedicated "backend unreachable" screen with a Retry button that reloads). The key invariant: an authenticated user is never silently dropped to `/dashboard` because of a 5xx/network blip, and an UNVERIFIED user is never shown console contents.
- Add a short timeout (e.g. 8s) to the `me` fetch so a hanging backend shows the retry screen rather than hanging the route.

**Problem B — sign-out sends operators to the wrong login.** `operator-sidebar.tsx` `handleSignOut` does `router.push("/login")`. Operators log in at `/operator/login`. Change the post-sign-out redirect to `/operator/login`.

Verify: `npm run typecheck` and `npm run lint` clean.

---

## Task 2: Safety — destructive-action guardrails + secure temp-password handling

**Files:** `frontend/app/operator/(console)/page.tsx`, `frontend/app/operator/(console)/scheduler/page.tsx`. You may add a small shared confirm modal under `frontend/app/operator/(console)/components/` if the existing `confirm-dialog.tsx` (which forces a typed match) is too heavy; a simpler yes/cancel `ActionConfirm` is acceptable for non-typed confirmations.

**Problem A — reset-password uses native `confirm()` and leaks the temp password.** In `page.tsx`, `handleResetPassword` uses `confirm(...)`, and the resulting temp password is shown in a plaintext banner ([lines ~291-299]) with no copy button and no masking.
Requirements:
- Replace the native `confirm()` with an in-app confirmation modal ("Reset password for {name}?", Cancel / Reset).
- Show the returned temp password **masked by default** (dots) with a reveal (eye) toggle and a **Copy** button (reuse the copy-with-checkmark pattern already in `page.tsx`). Keep the manual Dismiss.

**Problem B — pausing a platform-critical scheduler job has no guard.** In `scheduler/page.tsx`, `toggleJob` flips a job with a single click. Pausing jobs like `scheduled-broadcasts`, `broadcast-retries`, `reengagement-rules`, `assignment-sweep`, `callback-reassignment` silently halts platform-wide behavior for every tenant.
Requirements:
- Define a set of critical job ids (the five above). When the user attempts to **pause** (not resume) a critical job, show a confirmation modal naming the job and the platform-wide consequence before calling the toggle endpoint. Resuming needs no confirmation. Non-critical jobs pause without confirmation.
- Keep the existing optimistic-update + rollback-on-error behavior.
- While here, replace this file's raw `text-gray-*` / `#5b21b6` literals with design tokens per Global Constraints.

Verify: `npm run typecheck` + `npm run lint` clean.

---

## Task 3: Custom `OperatorToggle` component + adopt everywhere

**Goal:** a single distinctive, polished toggle used across the operator console — NOT a plain rounded pill switch. Invoke the frontend-design skill for the visual design. It should feel deliberately custom (e.g. a track with an icon that morphs/slides, a check/lock glyph on the knob, a subtle glow when on, spring easing), consistent with the existing `EntitlementToggle` visual language (gradient `from-primary to-violet-500`, spring `cubic-bezier(.34,1.56,.64,1)` knob, check glyph). Must respect `prefers-reduced-motion`.

**New file:** `frontend/app/operator/(console)/components/operator-toggle.tsx` exporting `OperatorToggle`.
Props: `{ checked: boolean; onChange: (next: boolean) => void; disabled?: boolean; loading?: boolean; size?: "sm" | "md"; "aria-label": string }`.
Requirements:
- Rendered as a real `<button role="switch" aria-checked={checked}>`, keyboard-operable (Enter/Space), focus-visible ring, disabled + loading states (loading shows a spinner/pulse and blocks clicks).
- Distinct from a stock switch — document the design choice in a top-of-file comment.

**Adopt it in:**
- `client/[id]/sidebar.tsx` — replace the inline `FeatureToggle` button markup with `OperatorToggle` (keep the same feature-toggle behavior, `featureUpdating` → `loading`/`disabled`, `stopPropagation` on the row click).
- `scheduler/page.tsx` — replace the inline pause/resume toggle with `OperatorToggle` (`loading={toggling === j.id}`, aria-label = pause/resume job name). Keep Task 2's critical-pause confirmation in front of the state change.
- Leave `EntitlementToggle` (feature-store) as-is unless trivial — it has metered/locked/usage-ring semantics `OperatorToggle` does not cover. Note this in the report.

Verify: `npm run typecheck` + `npm run lint` clean. Confirm toggles still function (feature enable/disable, job pause/resume).

---

## Task 4: QA polish — debounce, refresh, shared fetch/time utils, a11y

**Files:** `frontend/app/operator/(console)/audit-log/page.tsx`, `frontend/app/operator/(console)/page.tsx`, `frontend/app/operator/(console)/fleet/page.tsx`, plus a new `frontend/app/operator/(console)/lib/` (or `frontend/lib/operator.ts`) for shared helpers.

Requirements:
- **Shared operator fetch + relTime.** Create one shared `operatorFetch<T>(path, init?)` helper and one `relTime(iso)` used by the operator pages, removing the per-file re-declarations in `page.tsx`, `fleet/page.tsx`, `scheduler/page.tsx`, `audit-log/page.tsx`, `client/[id]/page.tsx`, `client/[id]/views/health.tsx`. The two divergent `relTime` implementations (scheduler vs audit-log) must converge to one. Add a unit test for `relTime` covering seconds/minutes/hours/days and future ("in Xs") values.
- **Audit-log search debounce.** Debounce the `search` input (~300ms) so typing does not fire a request per keystroke. Page still resets to 1 on a new search.
- **Clients list refresh.** Add a manual Refresh button (spinner while loading) to `page.tsx` (Clients) and to `fleet/page.tsx`. Clients list may also poll on the same 60s cadence as the health card — reuse one interval if practical.
- **Keyboard a11y for clickable rows/cards.** The client grid cards and table rows in `page.tsx`, and fleet rows, use `<div onClick>` / `<tr onClick>` for navigation. Make them keyboard-operable (wrap nav in an `<a>`/`<button>` or add `role="button" tabIndex={0}` + Enter/Space handler + `aria-label`), preserving the `stopPropagation` on nested action buttons.

Verify: `npm run typecheck` + `npm run lint` clean; new `relTime` test passes.

---

## Task 5: Feature — Fleet attention queue (at-risk surfacing, sort/filter, export)

The Fleet page subtitle promises an "attention queue" it never renders, and backend `health` is a trivial `active ? healthy : warning`.

**Backend** (`backend/app/routes/operator.py`, `/fleet`): enrich each fleet row with the signals needed to compute real attention. Reuse data the file already gathers where possible. Add per-client booleans/counts: `near_cap` (ai_usage ≥ 80), `token_expired` (Meta token expired/not-set where messaging enabled), `channel_unhealthy` (any configured channel unhealthy), `no_activity_14d` (last_activity older than 14d or null while active). Compute `health` from these signals (critical if token_expired or channel_unhealthy or ai_usage ≥ 100; warning if near_cap or no_activity_14d; else healthy) instead of the status-only rule. Keep the response shape backward-compatible (only add fields). Add/adjust a pytest for the scoring helper (extract it as a pure function).

**Frontend** (`fleet/page.tsx`): 
- Add an **Attention Queue** section above the table listing only clients with `health !== "healthy"`, each with a chip explaining WHY (Near cap / Token expired / Channel down / Idle 14d). Empty state: "All clients healthy."
- Make the full table **sortable** (MRR, AI usage, messages, last activity) and **filterable** by status and health.
- Add **Export CSV** of the current (filtered) fleet view using the existing blob-download pattern from `@/lib/api` (see `leads.exportLeads`).

Verify: pytest green for the scoring function; `npm run typecheck` + `npm run lint` clean.

---

## Task 6: Feature — Operator alert center (bell)

A single place surfacing platform problems, in the operator header.

**Backend** (`operator.py`): add `GET /api/v1/operator/alerts` (admin-guarded) returning an aggregated, deduped list of active platform issues drawn from existing signals: failing/paused scheduler jobs (from the scheduler-health logic already in this file), clients with expired Meta tokens, clients at/over AI cap, open incidents, unhealthy channels. Each alert: `{ id, severity: "critical"|"warning"|"info", title, detail, tenant_id?, tenant_name?, source, created_at, href? }`. Extract shared logic from the existing scheduler-health / fleet endpoints rather than duplicating queries. Add a pytest.

**Frontend:** add a bell to `operator-sidebar.tsx` header showing an unread/critical count badge, opening a dropdown panel grouped by severity; clicking an alert with `href`/`tenant_id` navigates (e.g. to the client or scheduler page). Poll every 60s. Use design tokens; keyboard-accessible (button + focus-visible, Esc closes).

Verify: pytest green; `npm run typecheck` + `npm run lint` clean.

---

## Task 7: Feature — ⌘K command palette

Global quick-nav for operators.

**Frontend only:** add a command palette (new component under `components/`) mounted from the operator `layout` (client island) opening on ⌘K / Ctrl+K. It lists: all clients (fetched once, fuzzy-searchable by name/ID → navigate to `/operator/client/{id}`), and static nav/actions (Clients, Fleet, Schedulers, Audit Log, New Client). Arrow-key navigation, Enter to select, Esc to close, focus trap, restores focus on close. Design-token styled, `prefers-reduced-motion` respected. Reuse `operatorFetch` for the client list.

Verify: `npm run typecheck` + `npm run lint` clean.

---

## Task 8: Feature — Scheduler "Run now" + per-job history

**Backend** (`operator.py`): add `POST /api/v1/operator/scheduler/{job_id}/run` (admin-guarded) that triggers the named job immediately via the existing scheduler mechanism used by the toggle endpoint; validate `job_id` against the known set; return the run result/queued status. Add a pytest. If the scheduler architecture cannot safely trigger an ad-hoc run, report BLOCKED with the specific reason instead of forcing it.

**Frontend** (`scheduler/page.tsx`): add a "Run now" action per job card (disabled while a run is in flight; shows result via the existing error/last-run surface). Keep Task 2/3 pause behavior intact.

Verify: pytest green; `npm run typecheck` + `npm run lint` clean.

---

## Task 9: Feature — Bulk client actions

**Frontend** (`page.tsx`, Clients): add multi-select (checkbox per card/row + select-all in table view) and a bulk action bar: Suspend, Activate (reuse existing per-client `PATCH /status`), executed sequentially with a progress/result summary and one confirmation modal. No new backend route required (loop existing endpoints); if a bulk endpoint is clearly warranted for atomicity, note it in the report but do not build it without one.

Verify: `npm run typecheck` + `npm run lint` clean.

---

## Task 10: Feature — Operator dark mode (scoped CSS-variable refactor)

APPROACH DECIDED BY THE USER — do NOT deviate: migrate the design tokens to channel-triplet CSS variables so a `.dark` class recolors all token-based classes at once, gate `.dark` to the operator console root ONLY, and keep light values byte-for-byte identical (zero visual change anywhere in light mode, dashboard included).

**Current state:** `frontend/tailwind.config.ts` defines colors as hardcoded HEX (`ink: "#1c1917"`, `background: "#faf8f5"`, `primary: "#5b21b6"`, etc.). `frontend/app/globals.css` has a parallel `:root` set of `--token: #hex` vars that the Tailwind classes do NOT consume. The codebase uses opacity modifiers (`bg-success/10`, `bg-danger/10`) that must keep working.

**Step 1 — token → channel-triplet variables (light values identical):**
- In `globals.css` `:root`, redefine each color token as a SPACE-SEPARATED RGB TRIPLET of its CURRENT hex (e.g. `#1c1917` → `--ink: 28 25 23;`, `#faf8f5` → `--bg: 250 248 245;`). Convert EVERY color token used by tailwind.config (background, surface*, primary*, ink*, border*, success/warning/danger, secondary*, on-surface*, segment-* — the full set).
- In `tailwind.config.ts`, change each of those color entries to `"rgb(var(--<token>) / <alpha-value>)"` so `bg-primary` → `rgb(var(--primary)/1)` and `bg-primary/10` → `rgb(var(--primary)/0.1)`. This preserves opacity-modifier support. VERIFY the triplet for each token equals the exact prior hex — any drift is a light-mode visual regression across the whole app. Keep radii/shadows/fonts unchanged.
- Do NOT change `darkMode` to break anything; set `darkMode: "class"` (or `["selector", ".dark"]`) so `.dark` scoping works. This is inert everywhere there is no `.dark` ancestor, so the dashboard is unaffected.

**Step 2 — dark override set, scoped to operator:**
- Add a `.dark { --bg: ...; --surface: ...; --ink: ...; --border: ...; ... }` block (in `globals.css`) with dark-appropriate triplets for the structural tokens (dark bg, light ink, adjusted surfaces/borders, and primary/success/warning/danger tuned for dark). Because Tailwind classes now resolve to `rgb(var(--token))`, every descendant of `.dark` recolors automatically — no per-element `dark:` variants needed for token-based classes.
- Apply the `.dark` class to the OPERATOR CONSOLE ROOT only (the wrapping div in `frontend/app/operator/(console)/layout.tsx`), driven by a client theme state — NOT to `<html>`/`<body>` (that would darken the whole app). Since the layout is a server component, introduce a small `"use client"` theme wrapper/provider that owns the class + a `ThemeContext`, or apply the class via a client component that wraps `{children}` + sidebar. Keep the existing auth-gating untouched.

**Step 3 — hardcoded-hex cleanup (so dark mode is COMPLETE, not half-applied):**
- Grep the operator console files for hardcoded hex and arbitrary-value classes that BYPASS the token system and will stay light in dark mode: `bg-[#...]`, `text-[#...]`, `border-[#...]`, and literal hex (e.g. `#5b21b6`, `#faf8f5`, `#f5f3ff`, `#e8e3db`, `#1c1917`, `#f0ece4` appear in `client/[id]/sidebar.tsx`, `client/[id]/page.tsx`, and possibly others). Convert these to the equivalent token classes (`bg-primary-light`, `bg-background`, `border-border`, `text-primary`, `bg-surface-mid`, etc.) so they respond to `.dark`.
- For small semantic status chips using raw Tailwind palette tints (`bg-green-50`, `bg-red-50`, `emerald-*`, `amber-*`, `rose-*`) in scheduler/health/fleet/audit-log: add `dark:` variants ONLY where they'd be illegible on a dark surface (e.g. `dark:bg-emerald-500/15 dark:text-emerald-300`). Legible light-tint chips may remain; use judgment for a polished result. List any you intentionally leave in the report.

**Step 4 — theme toggle:** add a toggle in `operator-sidebar.tsx` header (sun/moon lucide icon, a `<button>` with aria-label). Persist choice to `localStorage`; on first load with no stored choice, respect `prefers-color-scheme`. Toggling adds/removes `.dark` on the operator root and updates stored preference. Avoid a light/dark flash on first paint if practical (acceptable to apply the class in a `useEffect`; a brief flash is a known non-blocker, note it if present).

Ensure ALL operator surfaces are legible in dark: clients grid/table + bulk bar, fleet + attention queue, scheduler cards + run-now, audit-log table, client detail sidebar + views, the OperatorToggle, command palette, alert center, all modals (ActionConfirm/confirm-dialog/sign-out).

**Verify:** `npm run typecheck` + `npm run lint` clean; AND `npm run build` succeeds (proves the tailwind color-config change compiles). In the report, confirm explicitly that every migrated token's triplet equals its prior hex (list a few conversions as evidence) so light mode is provably unchanged. Commit as soon as verification passes. This is a large diff — if some non-structural surfaces remain imperfect in dark, report DONE_WITH_CONCERNS listing exactly what remains rather than silently shipping half-done.

---

## Task 11: Feature — Tenant impersonation ("view as", read-only) — SECURITY-GATED

Highest-value support feature but adds a login-as surface. Treat security as the acceptance bar.

**Design + security first:** before implementing, the implementer must state the chosen mechanism and its safeguards in the report, and the task review MUST include a security pass (invoke security-review). Required safeguards: only `is_system_admin` may start impersonation; every impersonated action/request is attributed to the operator in the audit log (`operator.impersonation_started` / `_ended` + the acting admin id on any writes); impersonation is time-boxed and clearly indicated with a persistent banner; scope is READ-ONLY for v1 (no writes as the tenant) unless explicitly expanded; no privilege escalation (cannot impersonate into another operator/admin). 

**Backend:** add the minimal admin-guarded endpoint(s) to mint a scoped, short-lived read-only impersonation context for a given tenant, and audit-log start/stop. Do NOT reuse or expose the tenant owner's real credentials/session. Add pytests for: non-admin rejected, audit rows written, read-only enforcement.

**Frontend:** a "View as tenant" action on the client detail page that enters an impersonation session showing a persistent "Viewing as {tenant} — Exit" banner; Exit restores the operator session.

If a safe read-only mechanism cannot be built within the existing auth model without broader changes, report BLOCKED with the specific blocker and a recommended design, rather than shipping an unsafe impersonation.

Verify: pytest green (including the security tests); `npm run typecheck` + `npm run lint` clean; security-review pass in the task review.
