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

- A menu-icon button is added to `AppHeader.tsx`, next to `NotificationBell` / `ProfileMenu` (mobile-only, `md:hidden`, mirroring how those two are already always visible in the header).
- Tapping it opens a new `MoreDrawer` component: a right-side slide-in panel (backdrop-tap or swipe-to-dismiss), listing today's `MORE_ITEMS`, filtered through the existing `isVisible()` role/feature gate — same visibility rules as today, just a different container and trigger location instead of the current centered bottom-sheet grid.
- The bottom nav's `isMoreOpen` state, backdrop, and grid-sheet markup are removed from `MobileDashboardNav.tsx` and move into `MoreDrawer.tsx`.

### 3. Small cleanup: profile/Overview naming

`AppHeader.tsx` already renders the title "Overview" for `/dashboard/profile` when `role !== "owner"` — this stays as-is. No route rename is in scope (`/dashboard/profile` keeps its path since it's linked from `ProfileMenu` for owners too); this spec only confirms the existing title override is correct and is the thing Home now points to for callers.

## Files touched

- `components/MobileDashboardNav.tsx` — rewritten down to just the 3-tab grid (Home/Calls/Inbox) with role-aware Home target. `MORE_ITEMS`, `isVisible()`, and the bottom-sheet/backdrop markup are removed from this file entirely (they move to `MoreDrawer.tsx`, below).
- `components/MoreDrawer.tsx` (new) — owns `MORE_ITEMS` and `isVisible()` (moved from the old nav file), renders the right-side drawer, and is opened/closed via props from `AppHeader`.
- `lib/utils.ts` — add the small `isActive(pathname, href)` prefix-match helper here (currently duplicated inline in the nav file), so both `MobileDashboardNav` and `MoreDrawer` import the same one-line utility instead of redefining it.
- `components/AppHeader.tsx` — add mobile-only More trigger button next to `NotificationBell`/`ProfileMenu`, holding the `isMoreOpen` state and rendering `<MoreDrawer />`.

## Testing

- Manual verification at 320/375/768 widths (per project visual-regression convention) for both owner and caller roles: confirm 3 evenly-spaced tabs, correct Home target per role, drawer opens/closes correctly and lists the right role-filtered items.
- Confirm active-tab highlighting still matches on Home/Calls/Inbox across nested routes (e.g. `/dashboard/telecalling/scheduled` still highlights Calls).
