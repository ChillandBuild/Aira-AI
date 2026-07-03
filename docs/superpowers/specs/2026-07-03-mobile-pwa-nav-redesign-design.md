# Mobile PWA Bottom Nav Redesign

## Motivation

The installed PWA's mobile bottom nav (`components/MobileDashboardNav.tsx`) is a fixed `grid-cols-7` layout sized for the owner role's maximum tab count (up to 6 primary items + More). Roles with fewer visible tabs — most visibly the telecaller/caller role, which currently only sees Inbox + Calls + More — get those items packed into the first N of 7 columns, leaving dead space on the right instead of spreading evenly across the bar.

Separately, callers have no "Home" tab at all today: `Home` is `ownerOnly: true` in `PRIMARY_ITEMS`, and callers who land on `/dashboard` get redirected to `/dashboard/profile` (`DashboardClient.tsx`). That page already renders a caller-specific performance overview (AI Coaching digest, performance score, calls today, conversion rate — `ProfileClient.tsx`), and `AppHeader.tsx` already special-cases its title to "Overview" for non-owners (lines 172–175) — the precedent exists in code, it's just never been exposed as a primary nav destination.

## Goals

- Replace the fixed 7-column bottom nav with a consistent, evenly-spaced **3-tab** layout for all roles: **Home — Calls — Inbox**.
- Give callers a real Home tab, pointing at the existing `/dashboard/profile` overview screen (no new screen to build).
- Move "More" out of the bottom bar into the header, opening a right-side collapsible drawer instead of the current bottom-sheet grid.
- Keep the existing role/feature gating logic (`isVisible()`, `MORE_ITEMS`) unchanged — only the trigger location and visual presentation of "More" changes.

## Non-goals

- No redesign of the content of any individual page (Overview/profile, Calls/telecalling, Inbox/conversations) — this spec covers nav shell only.
- No changes to desktop/tablet layout (`md:hidden` scoping stays as-is; this only affects the mobile bottom nav and its header counterpart).
- No change to owner-only vs role-based visibility rules for items inside the More drawer — reuses `isVisible(item, role, enabledFeatures)` as-is.

## Design

### 1. Bottom nav — 3 fixed tabs

`MobileDashboardNav.tsx` is rewritten from a dynamic, role-filtered `PRIMARY_ITEMS` list rendered in a 7-column grid, to a fixed 3-item `grid-cols-3` layout:

| Tab | Icon | Owner target | Caller target |
|---|---|---|---|
| Home | `Home` | `/dashboard` | `/dashboard/profile` |
| Calls | `Phone` | `/dashboard/telecalling` | `/dashboard/telecalling` |
| Inbox | `MessageSquare` | `/dashboard/conversations` | `/dashboard/conversations` |

The tab label stays **"Home"** for both roles (not "Admin Overview" / "Telecaller Overview") — short, consistent, native-feeling alongside Calls/Inbox. The role distinction (which page Home actually opens) lives in routing code, not the visible label.

Active-state highlighting (`isActive()`) is unchanged — still prefix-matches `pathname` against the tab's `href`.

Since all three tabs are relevant to both roles, no `isVisible()` filtering is needed for this bar — it eliminates the empty-column bug entirely by construction (always exactly 3 items, always full width).

### 2. More — header trigger + right-side drawer

- **Correction found during planning:** `AppHeader.tsx` is not actually rendered on every route. `ClientLayout.tsx` special-cases `/dashboard/conversations` (the Inbox tab) into a header-less branch that renders only `{children}` + `MobileDashboardNav` — no `AppHeader`, no `NotificationBell`, no `ProfileMenu`. Putting the More trigger only inside `AppHeader` would make it unreachable from the Inbox tab, one of the three primary tabs this redesign relies on. Fixed by making the trigger+drawer a single self-contained component (`MoreMenu.tsx`, no props, manages its own open state — mirroring how `NotificationBell` is already self-contained) mounted from **two** call sites: inline in `AppHeader`'s icon row for every route that renders it, and as a small fixed-position element in `ClientLayout`'s header-less Inbox branch. This matches the codebase's existing pattern of `ClientLayout` rendering small shared elements (`MobileDashboardNav`, `CalendarPanel`) once per branch.
- `MoreMenu.tsx` renders a small circular trigger button (matching the 34×34 gradient-circle style of `NotificationBell`'s bell button) that opens a right-side slide-in panel (backdrop-tap to dismiss), listing today's `MORE_ITEMS`, filtered through the existing `isVisible()` role/feature gate — same visibility rules as today, just a different container and trigger location instead of the current centered bottom-sheet grid.
- The bottom nav's `isMoreOpen` state, backdrop, and grid-sheet markup are removed from `MobileDashboardNav.tsx` and move into `MoreMenu.tsx`.

### 3. Small cleanup: profile/Overview naming

`AppHeader.tsx` already renders the title "Overview" for `/dashboard/profile` when `role !== "owner"` — this stays as-is. No route rename is in scope (`/dashboard/profile` keeps its path since it's linked from `ProfileMenu` for owners too); this spec only confirms the existing title override is correct and is the thing Home now points to for callers.

## Files touched

- `components/MobileDashboardNav.tsx` — rewritten down to just the 3-tab grid (Home/Calls/Inbox) with role-aware Home target. `MORE_ITEMS`, `isVisible()`, and the bottom-sheet/backdrop markup are removed from this file entirely (they move to `MoreMenu.tsx`, below).
- `components/MoreMenu.tsx` (new) — self-contained: owns `MORE_ITEMS`, `isVisible()`, its own open/close state, the trigger button, and the right-side drawer. No props, no external state.
- `lib/utils.ts` — add the small `isActive(pathname, href)` prefix-match helper here (currently duplicated inline in the nav file), so both `MobileDashboardNav` and `MoreMenu` import the same one-line utility instead of redefining it.
- `components/AppHeader.tsx` — mount `<MoreMenu />` inline in the right-side icons row, next to `NotificationBell`/`ProfileMenu`.
- `components/ClientLayout.tsx` — mount `<MoreMenu />` in the header-less Inbox branch too (fixed top-right position, safe-area aware), so More is reachable from all three tabs regardless of which branch renders.

## Testing

- Unit test for `isActive()` (pure function, Vitest, mirrors the existing `lib/operator.test.ts` convention).
- Playwright e2e spec (`tests/e2e/mobile-nav.spec.ts`, mobile viewport) verifying: 3 evenly-spaced tabs render, More trigger opens the drawer with role-filtered items, drawer closes on backdrop tap — following the existing `tests/e2e/templates.spec.ts` convention (requires a running dev server + logged-in session).
- Manual verification at 320/375/768 widths (per project visual-regression convention) for both owner and caller roles: confirm 3 evenly-spaced tabs, correct Home target per role, More trigger reachable and working from the Home, Calls, *and* Inbox tabs specifically (the header-less-Inbox gap above), drawer lists the right role-filtered items.
- Confirm active-tab highlighting still matches on Home/Calls/Inbox across nested routes (e.g. `/dashboard/telecalling/scheduled` still highlights Calls).
