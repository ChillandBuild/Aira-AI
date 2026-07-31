# Client-Controlled Analytics Ranges Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an Analytics client choose any reporting period and, only when desired, independently choose a comparison period; render the redesigned Overview from one coherent selected-period dataset.

**Architecture:** Keep the legacy `/analytics/overview` response unchanged for Dashboard home and operator-console callers. Extend the comparison service into an explicit-period analytics payload: it always returns the requested reporting period and returns a second period only when `comparison=previous` or `comparison=custom`. The Dashboard Analytics Overview consumes that payload, while a compact attention queue continues to use its explicitly labelled rolling-24-hour endpoint.

**Tech Stack:** FastAPI, Supabase RPC-backed period aggregates, Next.js 14 App Router, React 18, TypeScript, Vitest, Recharts.

## Global Constraints

- Preserve IST calendar-date period semantics and the existing PostgreSQL RPC signatures.
- Do not alter the legacy `/api/v1/analytics/overview` contract.
- Reporting range and comparison range are client choices; comparison defaults to `off` and no endpoint silently substitutes a previous period.
- Do not create migrations or change database schema.
- Preserve unrelated untracked files already present in the worktree.
- Use the current checkout as directed by the existing analytics follow-up plan; do not create a worktree.

---

### Task 1: Make the analytics comparison API client-controlled

**Files:**
- Modify: `backend/app/routes/analytics.py:1279-1375`
- Modify: `backend/tests/test_analytics_compare_routes.py`
- Modify: `backend/tests/test_analytics_custom_range.py`

**Interfaces:**
- Consumes: existing `resolve_period`, `previous_period`, and `_period_payload` helpers.
- Produces: `GET /api/v1/analytics/compare?preset=<preset>&start=<date>&end=<date>&comparison=off|previous|custom&comparison_start=<date>&comparison_end=<date>`.
- Response contract: `current` is always present; `previous`, delta maps, and aligned series are `null`/empty when `comparison=off`; custom comparison uses only its explicit dates.

- [ ] **Step 1: Write failing API tests**

Add cases that request a custom reporting period with `comparison=off`, `comparison=previous`, and `comparison=custom`. Assert that off calls only the current-period RPCs, previous uses the derived predecessor, custom uses exactly the supplied comparison dates, and incomplete/reversed custom comparison dates return HTTP 400.

```python
res = self.client.get(
    "/api/v1/analytics/compare?preset=custom&start=2026-07-10&end=2026-07-12&comparison=off"
)
self.assertEqual(res.status_code, 200)
self.assertIsNone(res.json()["previous"])
self.assertEqual(res.json()["metrics"], {})
```

- [ ] **Step 2: Run the focused backend tests and confirm RED**

Run: `cd backend && pytest tests/test_analytics_compare_routes.py tests/test_analytics_custom_range.py -q`

Expected: the new tests fail because the endpoint still derives a previous period automatically and does not accept comparison controls.

- [ ] **Step 3: Implement explicit comparison resolution**

Add `comparison: Literal["off", "previous", "custom"] = Query("off")`, `comparison_start`, and `comparison_end` to `compare_analytics`. Resolve the reporting period exactly as today. Resolve the second period only for `previous` or validated `custom`; invoke `_period_payload` once for off and concurrently twice otherwise. Return `previous: None`, `{}` delta maps, and empty series for off. Keep the existing current/previous response shape for enabled comparisons.

```python
if comparison == "off":
    current = await _period_payload(db, tenant_id, cur_start, cur_end)
    previous = None
elif comparison == "custom":
    prev_start, prev_end = resolve_period("custom", comparison_start, comparison_end, today_ist)
    current, previous = await asyncio.gather(...)
else:
    prev_start, prev_end = previous_period(cur_start, cur_end, preset)
    current, previous = await asyncio.gather(...)
```

- [ ] **Step 4: Make comparison export explicit**

Require `comparison=previous|custom` for `/compare/export`, forwarding the same range parameters to `compare_analytics`. Return a clear HTTP 400 when a client asks to export a comparison while comparison is off. Update its tests accordingly.

- [ ] **Step 5: Run the focused backend tests and confirm GREEN**

Run: `cd backend && pytest tests/test_analytics_compare_routes.py tests/test_analytics_custom_range.py -q`

Expected: PASS.

### Task 2: Create testable client-side range state and API types

**Files:**
- Create: `frontend/components/analytics/periodSelection.ts`
- Create: `frontend/components/analytics/periodSelection.test.ts`
- Modify: `frontend/components/analytics/RangePicker.tsx`
- Modify: `frontend/lib/api.ts:598-622,1501-1567`

**Interfaces:**
- Produces `ComparisonSelection = { mode: "off" | "previous" | "custom"; start: string; end: string }` and `isCompleteSelection` helpers.
- `RangePicker` accepts `idPrefix` so reporting and comparison custom-date inputs never duplicate DOM IDs.
- `api.analytics.compare` and `exportCompareCsv` accept `comparison`, `comparison_start`, and `comparison_end`; `ComparePayload.previous` becomes nullable and comparison-only metric maps remain empty when off.

- [ ] **Step 1: Write failing pure-state tests**

```ts
import { describe, expect, it } from "vitest";
import { canLoadComparison } from "./periodSelection";

it("loads a report without comparison when its reporting range is complete", () => {
  expect(canLoadComparison({ preset: "custom", start: "2026-07-01", end: "2026-07-07" }, { mode: "off", start: "", end: "" })).toBe(true);
});

it("waits for both comparison dates in custom mode", () => {
  expect(canLoadComparison({ preset: "last_7d", start: "", end: "" }, { mode: "custom", start: "2026-06-01", end: "" })).toBe(false);
});
```

- [ ] **Step 2: Run the focused frontend test and confirm RED**

Run: `cd frontend && npm test -- components/analytics/periodSelection.test.ts`

Expected: FAIL because `periodSelection.ts` does not exist.

- [ ] **Step 3: Implement selection helpers, typed API query building, and unique IDs**

Implement only deterministic selection validation in `periodSelection.ts`. Update `RangePicker` to use `idPrefix` in its `label htmlFor` and input `id` values. Update `ComparePayload` so UI code cannot read a previous period without checking that comparison is enabled.

- [ ] **Step 4: Run the focused frontend test and typecheck**

Run: `cd frontend && npm test -- components/analytics/periodSelection.test.ts && npm run typecheck`

Expected: PASS.

### Task 3: Build an explicit comparison control and adapt the Compare tab

**Files:**
- Create: `frontend/components/analytics/ComparisonPicker.tsx`
- Modify: `frontend/app/dashboard/analytics/CompareTab.tsx`
- Modify: `frontend/app/dashboard/analytics/CompareTab.test.tsx`

**Interfaces:**
- `ComparisonPicker` consumes `ComparisonSelection`, renders Off / Previous period / Custom, and renders a uniquely-prefixed `RangePicker` only for Custom.
- `CompareTab` fetches only after the reporting selection and, if relevant, comparison selection are complete; it renders no deltas, prior-series legend, or CSV action when comparison is off.

- [ ] **Step 1: Write failing component-level tests**

Test the exported rendering helpers (not browser-only DOM internals): `comparisonLabel({ mode: "off" })` returns `"No comparison"`; custom mode with both dates returns the exact label; `ComparisonHeader` has no “vs” text when `previous` is null.

- [ ] **Step 2: Run the focused frontend test and confirm RED**

Run: `cd frontend && npm test -- app/dashboard/analytics/CompareTab.test.tsx`

Expected: FAIL because the helpers/control do not exist and `ComparePayload.previous` is assumed to exist.

- [ ] **Step 3: Implement the control and null-safe comparison rendering**

Keep the current reporting-period picker. Add the explicit comparison picker beneath it. Pass API query parameters only when a comparison mode is enabled. Disable CSV export in off mode and replace the old automatic-comparison summary with a current-period title. Guard every previous/delta/chart rendering branch with `data.previous !== null`.

- [ ] **Step 4: Run the focused frontend tests and typecheck**

Run: `cd frontend && npm test -- app/dashboard/analytics/CompareTab.test.tsx components/analytics/periodSelection.test.ts && npm run typecheck`

Expected: PASS.

### Task 4: Replace the Overview’s mixed-scope grid with the decision-first design

**Files:**
- Modify: `frontend/app/dashboard/analytics/page.tsx`
- Create: `frontend/app/dashboard/analytics/overviewPresentation.ts`
- Create: `frontend/app/dashboard/analytics/overviewPresentation.test.ts`

**Interfaces:**
- `overviewPresentation.ts` accepts the current period payload plus optional comparison payload and returns display-ready performance values, an optional delta, and scope labels.
- `OverviewTab` consumes the explicit comparison API and the stale-hot-leads endpoint separately.

- [ ] **Step 1: Write failing presentation tests**

```ts
it("does not emit a delta when the client selected no comparison", () => {
  expect(buildPerformanceCard({ current: 294, previous: null })).toMatchObject({ delta: null, scope: "Selected period" });
});

it("labels a rolling queue independently from the reporting period", () => {
  expect(attentionScopeLabel()).toBe("Last 24 hours");
});
```

- [ ] **Step 2: Run the focused frontend test and confirm RED**

Run: `cd frontend && npm test -- app/dashboard/analytics/overviewPresentation.test.ts`

Expected: FAIL because the presentation module does not exist.

- [ ] **Step 3: Implement the decision-first Overview**

Replace the eight mixed-scope cards with: (1) an explicitly labelled attention block that links to the reply/stale-hot-lead queue; (2) selected-period performance cards for new leads, qualified rate, conversions, cost per lead, and median reply time; (3) one selected-period pipeline funnel; and (4) one lead trend chart. Put `RangePicker` and `ComparisonPicker` above this content. Remove the duplicate segment-distribution card from Overview; preserve deeper analysis in the other tabs. Show a visible non-blocking error when stale-hot-lead data cannot load.

- [ ] **Step 4: Thread the reporting range through dependent tabs**

Change Channels and Inbound calls to send either their selected preset or custom start/end values. Hide the page-level reporting-range controls on Templates unless and until that endpoint supports ranges; do not display a control that has no effect.

- [ ] **Step 5: Run focused tests, typecheck, and lint**

Run: `cd frontend && npm test -- app/dashboard/analytics/overviewPresentation.test.ts app/dashboard/analytics/CompareTab.test.tsx components/analytics/periodSelection.test.ts && npm run typecheck && npm run lint`

Expected: PASS.

### Task 5: Verify user-visible behaviour and regression coverage

**Files:**
- Modify: `frontend/tests/e2e/dashboard-redesign.spec.ts`
- Modify: `backend/tests/test_analytics_compare_routes.py` only if an uncovered API edge is found during verification.

**Interfaces:**
- Verifies the deployed page offers Custom reporting range, Off-by-default comparison, custom comparison, and clear period labels without modifying source contracts outside this feature.

- [ ] **Step 1: Add an E2E assertion for client-controlled controls**

Assert that Analytics exposes a custom reporting range, comparison starts off, enabling Custom exposes a second date pair, and the selected labels are visible. Use existing authenticated dashboard test setup rather than adding a new login bypass.

- [ ] **Step 2: Run the E2E test and confirm it initially fails**

Run: `cd frontend && npx playwright test tests/e2e/dashboard-redesign.spec.ts`

Expected: FAIL before the controls and labels exist.

- [ ] **Step 3: Run complete feature verification**

Run:

```bash
cd backend && pytest tests/test_analytics_compare_routes.py tests/test_analytics_custom_range.py -q
cd frontend && npm test && npm run typecheck && npm run lint
cd frontend && npx playwright test tests/e2e/dashboard-redesign.spec.ts
```

Expected: all commands pass. Review `git -c core.fsmonitor=false status --short` and confirm it contains only intentional feature files plus the pre-existing untracked files.
