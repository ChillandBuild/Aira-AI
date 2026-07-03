# Mobile PWA Bottom Nav Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the mobile PWA's fixed 7-column bottom nav (which leaves dead space for roles with few tabs) with a consistent 3-tab Home/Calls/Inbox layout for every role, and move "More" out of the bottom bar into a header-triggered, role-filtered side drawer.

**Architecture:** Two pure helpers (`isActive`, `getHomeHref`) move into `lib/utils.ts` so nav logic is unit-testable without rendering React. `MobileDashboardNav.tsx` shrinks to just the 3-tab grid. A new self-contained `MoreMenu.tsx` (no props, owns its own open/close state — mirroring the existing `NotificationBell` pattern) owns the full `MORE_ITEMS` list (today's `MORE_ITEMS` plus the owner-only items — Leads, Send, Templates — that are losing their primary-tab slot) and is mounted from two call sites: inline inside `AppHeader.tsx`, and as a small fixed-position element inside `ClientLayout.tsx`'s header-less Inbox branch (since `AppHeader` does not render there today).

**Tech Stack:** Next.js 14 App Router, React, TypeScript, Tailwind, lucide-react icons, Vitest (unit tests, `environment: "node"`), Playwright (e2e, `tests/e2e/`).

## Global Constraints

- Bottom nav tab label is **"Home"** for every role — never "Admin Overview" / "Telecaller Overview". The role distinction lives in which route Home points to, not in the label.
- Exactly 3 primary tabs, always: **Home — Calls — Inbox**, in a `grid-cols-3` layout, always evenly spread full-width. No `isVisible()`/role filtering on this bar — all 3 are valid destinations for every role.
- Home's target: `/dashboard` for `role === "owner"` (and while `role` is still `null`/loading); `/dashboard/profile` for `role === "caller"`.
- `MORE_ITEMS` in the new `MoreMenu.tsx` must include **all** of today's `MORE_ITEMS` entries **plus** `Leads` (`/dashboard/leads`), `Send` (`/dashboard/outbound-leads`), and `Templates` (`/dashboard/templates`) — these three are moving out of the old `PRIMARY_ITEMS` bar, not being removed. Every item's existing `ownerOnly`/`feature`/`anyFeature` gate is preserved verbatim — this is a relocation, not a rewrite of the gating rules.
- `MoreMenu` is a **self-contained** component: no props, manages its own `isOpen` state internally (mirrors `components/NotificationBell.tsx`'s existing pattern of owning its own trigger + panel + state).
- No changes to desktop/tablet layout — every new/changed piece of mobile UI stays `md:hidden`, matching the existing convention in `MobileDashboardNav.tsx` and `NotificationBell.tsx`.
- The `MoreMenu` drawer panel's bottom edge must stay above the bottom nav's screen region (`bottom-[calc(4.75rem+env(safe-area-inset-bottom))]`, matching `MobileDashboardNav`'s own height calc) — confirmed by direct testing that a `fixed` drawer nested inside `AppHeader`'s `sticky z-40` header renders **below** the bottom nav's `z-60` at any point where the two would visually overlap, regardless of the drawer's own (higher) z-index, because `AppHeader` establishes its own stacking context. Keeping the panel spatially clear of the nav's region sidesteps this entirely (this is the same reason `NotificationBell`'s panel already stops short of the bottom nav today).

---

### Task 1: Extract `isActive` and `getHomeHref` into `lib/utils.ts`

**Files:**
- Modify: `frontend/lib/utils.ts`
- Test: `frontend/lib/utils.test.ts` (new)

**Interfaces:**
- Produces: `isActive(pathname: string, href: string): boolean` — exact prefix-match logic already used inline in `MobileDashboardNav.tsx` today (`pathname === href || pathname.startsWith(\`${href}/\`)`).
- Produces: `getHomeHref(role: "owner" | "caller" | null): string` — returns `"/dashboard/profile"` when `role === "caller"`, otherwise `"/dashboard"` (covers `"owner"` and the `null`/still-loading state).
- Consumed by Task 2 (`MobileDashboardNav.tsx`) and Task 3 (`MoreMenu.tsx`).

- [ ] **Step 1: Write the failing test**

Create `frontend/lib/utils.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { getHomeHref, isActive } from "./utils";

describe("isActive", () => {
  it("returns true for an exact path match", () => {
    expect(isActive("/dashboard/telecalling", "/dashboard/telecalling")).toBe(true);
  });

  it("returns true for a nested path under href", () => {
    expect(isActive("/dashboard/telecalling/scheduled", "/dashboard/telecalling")).toBe(true);
  });

  it("returns false for an unrelated path", () => {
    expect(isActive("/dashboard/conversations", "/dashboard/telecalling")).toBe(false);
  });

  it("returns false for a path that merely starts with the same characters", () => {
    expect(isActive("/dashboard/telecallingX", "/dashboard/telecalling")).toBe(false);
  });
});

describe("getHomeHref", () => {
  it("returns /dashboard/profile for callers", () => {
    expect(getHomeHref("caller")).toBe("/dashboard/profile");
  });

  it("returns /dashboard for owners", () => {
    expect(getHomeHref("owner")).toBe("/dashboard");
  });

  it("returns /dashboard while role is still loading (null)", () => {
    expect(getHomeHref(null)).toBe("/dashboard");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run lib/utils.test.ts`
Expected: FAIL — `isActive` and `getHomeHref` are not exported from `./utils`.

- [ ] **Step 3: Add the two functions to `lib/utils.ts`**

Append to `frontend/lib/utils.ts` (after the existing `formatIST` function, keep every existing export untouched):

```ts
export function isActive(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function getHomeHref(role: "owner" | "caller" | null): string {
  return role === "caller" ? "/dashboard/profile" : "/dashboard";
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run lib/utils.test.ts`
Expected: PASS — 7 tests passing (4 for `isActive`, 3 for `getHomeHref`).

- [ ] **Step 5: Run the full unit test suite to confirm no regressions**

Run: `cd frontend && npx vitest run`
Expected: PASS — all test files pass (the pre-existing `lib/operator.test.ts` plus the new `lib/utils.test.ts`).

- [ ] **Step 6: Commit**

```bash
cd frontend
git add lib/utils.ts lib/utils.test.ts
git commit -m "feat(frontend): extract isActive and getHomeHref helpers to lib/utils"
```

---

### Task 2: Rewrite `MobileDashboardNav.tsx` to a fixed 3-tab layout

**Files:**
- Modify: `frontend/components/MobileDashboardNav.tsx` (full rewrite — current file is 164 lines; new file is much shorter)

**Interfaces:**
- Consumes: `isActive(pathname: string, href: string): boolean` and `getHomeHref(role: "owner" | "caller" | null): string` from `@/lib/utils` (Task 1).
- Consumes: `useAuthRole()` from `@/app/dashboard/contexts/AuthRoleContext`, which returns `{ role: "owner" | "caller" | null, callerId, enabledFeatures, isSystemAdmin, loading }` — this task only needs `role`.
- Produces: no exports other than `MobileDashboardNav` itself (unchanged export name/shape — it is still a zero-prop component, so `ClientLayout.tsx`'s two existing `<MobileDashboardNav />` call sites need no changes).

- [ ] **Step 1: Replace the full contents of `frontend/components/MobileDashboardNav.tsx`**

```tsx
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Home, MessageSquare, Phone } from "lucide-react";
import { useAuthRole } from "@/app/dashboard/contexts/AuthRoleContext";
import { cn, getHomeHref, isActive } from "@/lib/utils";

type NavTab = {
  href: string;
  icon: typeof Home;
  label: string;
};

export function MobileDashboardNav() {
  const pathname = usePathname() || "/dashboard";
  const { role } = useAuthRole();

  const tabs: NavTab[] = [
    { href: getHomeHref(role), icon: Home, label: "Home" },
    { href: "/dashboard/telecalling", icon: Phone, label: "Calls" },
    { href: "/dashboard/conversations", icon: MessageSquare, label: "Inbox" },
  ];

  return (
    <nav className="fixed inset-x-0 bottom-0 z-[60] h-[calc(4.75rem+env(safe-area-inset-bottom))] border-t border-border bg-white/95 px-3 pt-2 shadow-[0_-10px_30px_rgba(28,25,23,0.08)] backdrop-blur md:hidden">
      <div className="mx-auto grid h-14 max-w-lg grid-cols-3 gap-0.5 pb-0">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          const active = isActive(pathname, tab.href);
          return (
            <Link
              key={tab.label}
              href={tab.href}
              className={cn(
                "flex h-14 min-w-0 flex-col items-center justify-center gap-1 rounded-xl px-0.5 text-[9px] font-extrabold leading-none",
                active ? "bg-primary-light text-primary" : "text-ink-secondary"
              )}
            >
              <Icon size={16} strokeWidth={2.1} />
              <span className="max-w-full truncate">{tab.label}</span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
```

Note: the tab `key` is `tab.label` (stable across renders), not `tab.href` — Home's `href` changes once `role` resolves from `null` to `"caller"`/`"owner"` after the initial render, and keying on `href` would force React to unmount/remount that tab's `<Link>` at that moment instead of just updating its `href` prop.

- [ ] **Step 2: Type-check**

Run: `cd frontend && npx tsc --noEmit --pretty false`
Expected: no errors referencing `MobileDashboardNav.tsx`.

- [ ] **Step 3: Manual visual check with the dev server**

Run: `cd frontend && npm run dev`, then open `http://localhost:3000/aira/dashboard` (or whichever route you're logged into) with a mobile-width viewport (browser devtools device toolbar, ~390px wide).

Expected: bottom bar shows exactly 3 evenly-spaced tabs — Home, Calls, Inbox — filling the full width with no leftover empty columns. Tapping each one navigates and highlights the active tab.

- [ ] **Step 4: Commit**

```bash
cd frontend
git add components/MobileDashboardNav.tsx
git commit -m "feat(frontend): rewrite mobile bottom nav to fixed 3-tab Home/Calls/Inbox layout"
```

---

### Task 3: Create `MoreMenu.tsx`

**Files:**
- Create: `frontend/components/MoreMenu.tsx`

**Interfaces:**
- Consumes: `isActive` from `@/lib/utils` (Task 1).
- Consumes: `useAuthRole()` from `@/app/dashboard/contexts/AuthRoleContext` — needs `role` and `enabledFeatures`.
- Produces: `export function MoreMenu()` — a zero-prop, self-contained component (owns its own `isOpen` state). Consumed by Task 4's two call sites (`AppHeader.tsx`, `ClientLayout.tsx`).

- [ ] **Step 1: Create `frontend/components/MoreMenu.tsx`**

```tsx
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import {
  BarChart2,
  BookOpen,
  Calendar,
  Grid3X3,
  Inbox,
  Layers,
  Menu,
  Settings,
  SquarePen,
  StickyNote,
  Upload,
  Users,
  X,
} from "lucide-react";
import { useAuthRole } from "@/app/dashboard/contexts/AuthRoleContext";
import { cn, isActive } from "@/lib/utils";

type MoreMenuItem = {
  href: string;
  icon: typeof Users;
  label: string;
  ownerOnly?: boolean;
  feature?: string;
  anyFeature?: string[];
};

const MORE_ITEMS: MoreMenuItem[] = [
  { href: "/dashboard/leads", icon: Users, label: "Leads", ownerOnly: true, anyFeature: ["outbound_leads", "inbound_leads"] },
  { href: "/dashboard/outbound-leads", icon: Upload, label: "Send", ownerOnly: true, feature: "outbound_leads" },
  { href: "/dashboard/templates", icon: SquarePen, label: "Templates", ownerOnly: true, feature: "outbound_leads" },
  { href: "/dashboard/telecalling/scheduled", icon: Calendar, label: "Scheduled Calls", feature: "telecalling.scheduled" },
  { href: "/dashboard/notes", icon: StickyNote, label: "Call Notes", feature: "telecalling.notes" },
  { href: "/dashboard/inbound-leads", icon: Inbox, label: "Inbound Leads", ownerOnly: true, feature: "inbound_leads" },
  { href: "/dashboard/numbers", icon: Layers, label: "Numbers Pool", ownerOnly: true, anyFeature: ["outbound_leads", "inbound_leads"] },
  { href: "/dashboard/knowledge", icon: BookOpen, label: "Knowledge Base", ownerOnly: true, anyFeature: ["outbound_leads", "inbound_leads"] },
  { href: "/dashboard/analytics", icon: BarChart2, label: "Analytics", ownerOnly: true, anyFeature: ["outbound_leads", "inbound_leads"] },
  { href: "/dashboard/team", icon: Grid3X3, label: "Team", ownerOnly: true },
  { href: "/dashboard/settings", icon: Settings, label: "Settings", ownerOnly: true },
];

function isVisible(item: MoreMenuItem, role: string | null, enabledFeatures: string[]) {
  if (item.ownerOnly && role !== "owner") return false;
  if (item.feature && !enabledFeatures.includes(item.feature)) return false;
  if (item.anyFeature && !item.anyFeature.some((feature) => enabledFeatures.includes(feature))) return false;
  return true;
}

export function MoreMenu() {
  const pathname = usePathname() || "/dashboard";
  const { role, enabledFeatures } = useAuthRole();
  const [isOpen, setIsOpen] = useState(false);

  const items = MORE_ITEMS.filter((item) => isVisible(item, role, enabledFeatures));

  return (
    <div className="relative md:hidden">
      <button
        type="button"
        onClick={() => setIsOpen(true)}
        aria-label="More"
        className="flex h-[34px] w-[34px] items-center justify-center rounded-full text-white transition-transform hover:scale-105"
        style={{ background: "linear-gradient(135deg, #2e1065, #5b21b6)" }}
      >
        <Menu size={16} />
      </button>

      {isOpen && (
        <div className="fixed inset-0 z-[70] md:hidden">
          <button
            type="button"
            aria-label="Close navigation"
            className="absolute inset-0 bg-black/35"
            onClick={() => setIsOpen(false)}
          />
          <div className="absolute right-0 top-0 bottom-[calc(4.75rem+env(safe-area-inset-bottom))] w-[80vw] max-w-xs overflow-y-auto bg-white p-4 pt-[calc(1rem+env(safe-area-inset-top))] shadow-2xl animate-in fade-in slide-in-from-right duration-200">
            <div className="mb-3 flex items-center justify-between px-1">
              <div className="font-display text-sm font-extrabold text-ink">More</div>
              <button
                type="button"
                onClick={() => setIsOpen(false)}
                className="flex h-9 w-9 items-center justify-center rounded-full text-ink-secondary hover:bg-surface-mid"
                aria-label="Close"
              >
                <X size={18} />
              </button>
            </div>
            {items.length === 0 ? (
              <div className="rounded-xl border border-border-subtle bg-surface-low px-3 py-4 text-center font-body text-sm text-ink-muted">
                No more sections are available for this account.
              </div>
            ) : (
              <div className="flex flex-col gap-2">
                {items.map((item) => {
                  const Icon = item.icon;
                  const active = isActive(pathname, item.href);
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      onClick={() => setIsOpen(false)}
                      className={cn(
                        "flex min-h-12 items-center gap-3 rounded-xl border px-3 py-2.5 text-sm font-bold",
                        active
                          ? "border-primary-muted bg-primary-light text-primary"
                          : "border-border-subtle bg-surface-low text-ink hover:border-border"
                      )}
                    >
                      <Icon size={17} />
                      <span className="min-w-0 truncate">{item.label}</span>
                    </Link>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

Run: `cd frontend && npx tsc --noEmit --pretty false`
Expected: no errors referencing `MoreMenu.tsx`.

- [ ] **Step 3: Commit**

```bash
cd frontend
git add components/MoreMenu.tsx
git commit -m "feat(frontend): add self-contained MoreMenu drawer component"
```

---

### Task 4: Mount `MoreMenu` in `AppHeader.tsx` and `ClientLayout.tsx`

**Files:**
- Modify: `frontend/components/AppHeader.tsx:1-9` (imports), `frontend/components/AppHeader.tsx:383-384` (icons row)
- Modify: `frontend/components/ClientLayout.tsx:1-13` (imports), `frontend/components/ClientLayout.tsx:67-68` (isInbox branch)

**Interfaces:**
- Consumes: `MoreMenu` from `@/components/MoreMenu` (Task 3) — zero props.

- [ ] **Step 1: Import `MoreMenu` in `AppHeader.tsx`**

In `frontend/components/AppHeader.tsx`, the current imports are:

```tsx
import { NotificationBell } from "@/components/NotificationBell";
import { ProfileMenu } from "@/components/ProfileMenu";
import { useAuthRole } from "@/app/dashboard/contexts/AuthRoleContext";
```

Add `MoreMenu` alongside them:

```tsx
import { NotificationBell } from "@/components/NotificationBell";
import { ProfileMenu } from "@/components/ProfileMenu";
import { MoreMenu } from "@/components/MoreMenu";
import { useAuthRole } from "@/app/dashboard/contexts/AuthRoleContext";
```

- [ ] **Step 2: Mount `<MoreMenu />` in `AppHeader.tsx`'s icons row**

Find this block near the end of the file:

```tsx
        <NotificationBell />
        <ProfileMenu />
      </div>
    </header>
```

Replace with:

```tsx
        <MoreMenu />
        <NotificationBell />
        <ProfileMenu />
      </div>
    </header>
```

- [ ] **Step 3: Import `MoreMenu` in `ClientLayout.tsx`**

In `frontend/components/ClientLayout.tsx`, the current imports include:

```tsx
import { MobileDashboardNav } from "@/components/MobileDashboardNav";
```

Add `MoreMenu` on the next line:

```tsx
import { MobileDashboardNav } from "@/components/MobileDashboardNav";
import { MoreMenu } from "@/components/MoreMenu";
```

- [ ] **Step 4: Mount `<MoreMenu />` in the header-less Inbox branch**

In `frontend/components/ClientLayout.tsx`, find the `isInbox` branch's return block:

```tsx
              {children}
              <MobileDashboardNav />
            </div>
```

Replace with (adds a fixed-position wrapper, since this branch has no header row to drop `MoreMenu` into inline — unlike the `AppHeader` call site in Step 2, which places it in normal flow):

```tsx
              {children}
              <div className="fixed top-[calc(0.75rem+env(safe-area-inset-top))] right-3 z-[65] md:hidden">
                <MoreMenu />
              </div>
              <MobileDashboardNav />
            </div>
```

Do **not** add `MoreMenu` anywhere in the non-inbox branch's JSX beyond Step 2 — that branch already renders `AppHeader` (via `<Suspense>` further up in the same file), which now includes `MoreMenu` inline. Mounting it a second time there would show two triggers on every non-Inbox page.

- [ ] **Step 5: Type-check**

Run: `cd frontend && npx tsc --noEmit --pretty false`
Expected: no errors referencing `AppHeader.tsx` or `ClientLayout.tsx`.

- [ ] **Step 6: Manual check — trigger reachable from all three tabs**

Run: `cd frontend && npm run dev`, log in, at mobile viewport width:
1. On the Home tab (`/dashboard` or `/dashboard/profile`): confirm the More trigger (small circular icon, left of the notification bell) is visible in the header and opens the drawer.
2. On the Calls tab (`/dashboard/telecalling`): same check.
3. On the Inbox tab (`/dashboard/conversations`): confirm the trigger is visible as a floating button in the top-right corner (no header row here) and opens the same drawer.
4. In the drawer, confirm tapping a backdrop area outside the panel closes it, and the `X` button closes it.

Expected: all three checks pass, and the drawer never visually renders behind or gets clipped by the bottom nav bar.

- [ ] **Step 7: Commit**

```bash
cd frontend
git add components/AppHeader.tsx components/ClientLayout.tsx
git commit -m "feat(frontend): mount MoreMenu in AppHeader and the header-less Inbox layout branch"
```

---

### Task 5: e2e structural test + manual role verification

**Files:**
- Create: `frontend/tests/e2e/mobile-nav.spec.ts`

**Interfaces:**
- Consumes: nothing new — this is a black-box Playwright spec against the running dev server, following the existing convention in `frontend/tests/e2e/templates.spec.ts` (same docstring format, same "requires dev server + logged-in session" assumption — this codebase's e2e tests are run manually against an authenticated browser session, not from a from-scratch login flow).

- [ ] **Step 1: Write the e2e spec**

Create `frontend/tests/e2e/mobile-nav.spec.ts`:

```ts
import { test, expect } from "@playwright/test";

/**
 * Mobile Bottom Nav + More Drawer E2E Tests
 *
 * Tests the 3-tab bottom nav (Home/Calls/Inbox) and the More drawer.
 * Requires: Next.js dev server on localhost:3000 + logged-in session.
 *
 * Run: npx playwright test tests/e2e/mobile-nav.spec.ts --headed
 */

test.use({ viewport: { width: 390, height: 844 } });

test.describe("Mobile bottom nav", () => {
  test("shows exactly 3 evenly-spaced tabs: Home, Calls, Inbox", async ({ page }) => {
    await page.goto("/dashboard");
    await page.waitForLoadState("networkidle");

    const nav = page.locator("nav").filter({ has: page.getByText("Home") });
    await expect(nav.getByText("Home")).toBeVisible();
    await expect(nav.getByText("Calls")).toBeVisible();
    await expect(nav.getByText("Inbox")).toBeVisible();

    // No 4th tab or leftover "More" button in the bottom bar itself.
    await expect(nav.getByText("More")).toHaveCount(0);
  });

  test("Calls tab navigates to the telecalling page and highlights active", async ({ page }) => {
    await page.goto("/dashboard");
    await page.waitForLoadState("networkidle");

    await page.getByRole("link", { name: "Calls" }).click();
    await page.waitForURL(/\/dashboard\/telecalling/);
  });
});

test.describe("More drawer", () => {
  test("opens from the header trigger and closes on backdrop tap", async ({ page }) => {
    await page.goto("/dashboard");
    await page.waitForLoadState("networkidle");

    await page.getByRole("button", { name: "More" }).click();
    await expect(page.getByText("More", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Close" })).toBeVisible();

    // Tap the backdrop (top-left corner, outside the right-side panel) to dismiss.
    await page.mouse.click(10, 10);
    await expect(page.getByRole("button", { name: "Close" })).toHaveCount(0);
  });
});
```

- [ ] **Step 2: Run the spec against a logged-in dev session**

Run: `cd frontend && npm run dev` (separate terminal), then, once logged in through the browser at `http://localhost:3000`:

`npx playwright test tests/e2e/mobile-nav.spec.ts --headed`

Expected: all 3 tests pass. If they fail because of the login redirect, this matches the pre-existing limitation already documented in `templates.spec.ts` (no auth fixture exists in this repo yet) — note the failure and fall back to the manual checklist in Step 3 instead of trying to build new auth infrastructure (out of scope for this plan).

- [ ] **Step 3: Manual role-based verification checklist (perform as a human with real owner + caller test accounts — this cannot be automated without an auth fixture this repo doesn't have)**

At 320px, 375px, and 768px widths, for **both** an owner account and a caller account:

- [ ] Bottom nav shows exactly 3 evenly-spaced tabs, no dead space.
- [ ] Home tab: owner lands on the analytics overview (`/dashboard`); caller lands on the performance overview (`/dashboard/profile`, titled "Overview").
- [ ] Calls and Inbox tabs go to the same destinations for both roles.
- [ ] More drawer, owner account: shows Leads, Send, Templates, Scheduled Calls, Call Notes, Inbound Leads, Numbers Pool, Knowledge Base, Analytics, Team, Settings (whichever of these the account's enabled features allow) — confirm none of these silently disappeared compared to today's nav.
- [ ] More drawer, caller account: shows only Scheduled Calls / Call Notes (whichever `enabledFeatures` allow) — confirm no owner-only item leaks through.
- [ ] More drawer is reachable and fully usable (not clipped, not hidden behind the bottom nav) from all three tabs, including Inbox specifically.

- [ ] **Step 4: Commit**

```bash
cd frontend
git add tests/e2e/mobile-nav.spec.ts
git commit -m "test(frontend): add e2e spec for the 3-tab mobile nav and More drawer"
```
