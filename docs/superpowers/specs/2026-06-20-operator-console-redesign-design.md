# Operator Console — Complete Redesign

**Date:** 2026-06-20
**Status:** Draft
**Scope:** Full operator console redesign — warm palette, sidebar layout, mirrored client dashboard, modular feature toggles, data management, grid view, sign out

---

## Problem

The operator console looks disconnected from the product it manages. It uses a cold gray/indigo theme while the product uses a warm, polished design language. The client detail page shows limited data in a basic 4-tab layout — the operator can't see the client's actual dashboard experience or control granular features (e.g., telecalling sub-items). There's no sign out, no grid view for clients, and no way to clear specific data types.

## Solution

Redesign the operator console to match the product's visual identity and mirror the client dashboard inside the client detail page, with read-only views of every section and per-feature toggle controls.

---

## 1. Design System — Warm Palette Migration

Replace all cold gray/indigo styling across operator pages with the product's warm palette:

| Token | Value | Replaces |
|---|---|---|
| `bg-surface` | `#faf8f5` | `bg-gray-50`, `bg-white` page backgrounds |
| `bg-surface-mid` | `#f0ece4` | `bg-gray-100`, hover states |
| `bg-white` | `#ffffff` | Cards, modals (keep as-is) |
| `text-ink` | `#1c1917` | `text-gray-900`, primary text |
| `text-ink-secondary` | `#78716c` | `text-gray-500`, `text-gray-600` |
| `text-ink-muted` | `#a8a29e` | `text-gray-400` |
| `border-warm` | `#e8e3db` | `border-gray-200`, `border-gray-300` |
| `border-subtle` | `#f0ece4` | `border-gray-100` |
| `primary` | `#5b21b6` | `indigo-600` buttons, links, active states |
| `primary-light` | `#f5f3ff` | `indigo-50` active nav backgrounds |
| `primary-muted` | `#ede9fe` | Badge backgrounds |
| `success` | `#059669` | Active/configured states |
| `warning` | `#d97706` | Incomplete/pending states |
| `danger` | `#e11d48` | Destructive actions, errors |

**Font:** Manrope (inherited from product's globals.css — already loaded).

**Shadows:** Use `shadow-sm` on cards with warm border, `shadow-md` on hover for elevation. Cards use `rounded-2xl` (matching product).

**Transitions:** All interactive elements get `transition-all duration-200` for hover/focus states.

---

## 2. Operator Console Layout (Shell)

**Current:** Horizontal top nav bar with gray styling.
**New:** Full sidebar layout matching the product.

### Sidebar (240px, fixed left)

```
┌──────────────────────┐
│  Aira AI              │
│  ┌─────────────────┐ │
│  │ OPERATOR         │ │
│  └─────────────────┘ │
│                       │
│  📊 Clients           │
│  ⏱  Schedulers        │
│                       │
│                       │
│                       │
│                       │
│                       │
│                       │
│  ─────────────────── │
│  user@email.com       │
│  [Sign Out]           │
└──────────────────────┘
```

**Header:** "Aira" in script font + "AI" in primary purple (matching product). Below: "OPERATOR" badge in uppercase, small, muted purple background.

**Nav items:**
- **Clients** — `LayoutGrid` icon → `/operator`
- **Schedulers** — `Clock` icon → `/operator/scheduler`
- Active state: `bg-primary-light` background + `text-primary` + left border accent (3px primary)
- Hover state: `bg-surface-mid`

**Footer:**
- Current user email (truncated, `text-ink-muted`, small)
- **Sign Out** button — `LogOut` icon + "Sign Out" text, `text-ink-secondary`, hover `text-danger`
- Calls `supabase.auth.signOut()` → redirect to `/operator/login`

**Main content:** `ml-[240px]`, `bg-surface` (#faf8f5), `min-h-screen`. Content wrapper: `max-w-6xl mx-auto px-8 py-8`.

### Layout File Change

`frontend/app/operator/(console)/layout.tsx` — Convert from server component to client component (needs Supabase client for sign out). Auth check moves to a `useEffect` pattern or remains server-side with the sidebar as a client child component.

---

## 3. Clients List Page — Grid + Table Views

### View Toggle

Header row with title + description on left, view toggle + "New Client" button on right.

View toggle: Two icon buttons (list icon / grid icon) side by side, the active one highlighted with `bg-primary text-white`, inactive with `bg-white text-ink-secondary`. Persisted in `localStorage` as `operator-clients-view`.

### Grid View (Card Layout)

Responsive grid: `grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6`

Each card:
```
┌─────────────────────────────────┐
│                    [active] ●   │
│  Astrotamil                     │
│  00000000-0000...   📋          │
│                                 │
│  [WA] [IG] [FB] [TG] [TC]     │
│                                 │
│  Created: 23/5/2026             │
│  ──────────────────────────     │
│  🔑  ⏸  🗑                     │
└─────────────────────────────────┘
```

- **Card:** `bg-white rounded-2xl border border-warm shadow-sm hover:shadow-md transition-all duration-200 cursor-pointer`
- **Status badge:** Top-right, green dot + "active" or red dot + "suspended"
- **Client name:** `text-lg font-semibold text-ink`
- **Tenant ID:** Truncated mono, copy button
- **Feature badges:** Same purple pill badges as current (WA, IG, FB, TG, TC)
- **Created date:** `text-sm text-ink-secondary`
- **Divider:** `border-t border-subtle`
- **Action icons:** Bottom row, subtle icons. `e.stopPropagation()` on each.
  - Reset password (Key icon)
  - Suspend/Activate (PowerOff/Power icon)
  - Wipe leads (Trash2 icon, text-danger on hover)
- **Click:** Entire card navigates to `/operator/client/[id]`

### Table View

Same as current but restyled with warm palette:
- Table header: `bg-surface-mid text-ink-secondary uppercase text-xs tracking-wider`
- Row hover: `hover:bg-surface-mid/50`
- Borders: `border-warm`
- Status badges: green/red with dot indicator
- Feature badges: purple pills

### Warm-Styled Create Client Modal

Same fields (company name, email, password, feature checkboxes) but:
- Modal background: `bg-white rounded-2xl shadow-xl`
- Overlay: `bg-black/40 backdrop-blur-sm`
- Input styling: `border-warm rounded-xl focus:ring-primary/20 focus:border-primary`
- Feature checkboxes: styled toggle pills instead of plain checkboxes
- Button: `bg-primary hover:bg-primary-dark text-white rounded-xl`

---

## 4. Client Detail Page — Mirrored Dashboard

The centerpiece of the redesign. When clicking a client, the operator sees a layout that mirrors the product dashboard.

### Page Structure

```
┌────────────────────────────────────────────────────────────────┐
│  ← Back to Clients                                             │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Astrotamil          [active] [WA] [IG] [FB] [TG] [TC]  │  │
│  │  00000000-0000-... 📋   Owner: user@email.com            │  │
│  │  Created 23/5/2026                                        │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                │
│  ┌──────────┬───────────────────────────────────────────────┐  │
│  │ Sidebar  │  Content Area                                  │  │
│  │ (200px)  │                                                │  │
│  │          │  (Read-only view of selected section)          │  │
│  │ Overview │                                                │  │
│  │ Inbox    │                                                │  │
│  │ Convers. │                                                │  │
│  │ Segments │                                                │  │
│  │ Inbound  │                                                │  │
│  │ Outbound │                                                │  │
│  │ Template │                                                │  │
│  │ Numbers  │                                                │  │
│  │ Knowled. │                                                │  │
│  │ Analytic │                                                │  │
│  │ Team     │                                                │  │
│  │ Telecall.│                                                │  │
│  │  ├Upload │                                                │  │
│  │  ├Dialer │                                                │  │
│  │  ├Schedu.│                                                │  │
│  │  └Notes  │                                                │  │
│  │──────────│                                                │  │
│  │ OPERATOR │                                                │  │
│  │ Config   │                                                │  │
│  │ Health   │                                                │  │
│  │ Manage   │                                                │  │
│  │ Data Ops │                                                │  │
│  └──────────┴───────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────┘
```

### Client Header (Always Visible)

Above the sidebar/content split. Shows:
- Back link: `← Back to Clients` with hover underline
- Client name: `text-2xl font-bold text-ink`
- Status badge: green/red dot + text
- Feature badges: purple pills
- Tenant ID: mono, truncated, copy button
- Owner email: `text-ink-secondary`
- Created date: `text-ink-muted text-sm`

Card styling: `bg-white rounded-2xl border border-warm p-6`

### Client Sidebar (Left, 200px)

Mirrors the product sidebar nav items exactly, with two additions:

**Product section** (top):
Each item has the same icon as the product sidebar, same labels, same order. Items that are disabled (toggled off) appear with `opacity-40 line-through` styling but remain clickable for the operator.

Each nav item has a small toggle switch on its right side:
- Toggle ON: item is enabled for the client (visible in their sidebar)
- Toggle OFF: item is hidden from the client's sidebar
- Toggle animation: smooth slide with `transition-all duration-200`
- Toggle calls `PATCH /api/v1/operator/clients/{tenant_id}/features` with updated array

**Feature toggle mapping:**

| Sidebar Item | Feature Key | Parent Feature |
|---|---|---|
| Inbox | `whatsapp` | — |
| Conversations | (always on) | — |
| Segments | (always on) | — |
| Inbound Leads | Controlled by channel features | whatsapp/instagram/facebook/telegram |
| Outbound Leads | `whatsapp` | — |
| Templates | `whatsapp` | — |
| Numbers Pool | `whatsapp` | — |
| Knowledge Base | (always on) | — |
| Analytics | (always on) | — |
| Team | (always on) | — |
| Telecalling | `telecalling` | — |
| ├ Upload | `telecalling.upload` | telecalling |
| ├ Dialer | `telecalling.dialer` | telecalling |
| ├ Scheduled Calls | `telecalling.scheduled` | telecalling |
| └ Call Notes | `telecalling.notes` | telecalling |

**Items marked "(always on)"** don't get toggles — they're core features available to every client.

**Telecalling sub-features:** When the parent `telecalling` toggle is off, all children are disabled and their toggles are locked. When `telecalling` is on, each child can be individually toggled.

**Operator section** (below divider, labeled "OPERATOR"):
- Configuration (Wrench icon)
- Health (Activity icon)
- Management (Settings icon)
- Data Ops (Database icon)

These don't have toggles — they're operator-only sections.

**Active state:** Same as product sidebar — `bg-primary-light` + `text-primary` + left border accent.

### Sub-feature DB Schema Change

Expand `enabled_features text[]` to support dot-notation sub-features:

Current: `["whatsapp", "telecalling", "instagram", "facebook", "telegram"]`
New: `["whatsapp", "telecalling", "telecalling.dialer", "telecalling.upload", "telecalling.scheduled", "telecalling.notes", "instagram", "facebook", "telegram"]`

When `telecalling` is first enabled, all 4 sub-features are auto-added. Toggling off `telecalling` removes all sub-features. The product sidebar checks for `telecalling.dialer`, `telecalling.upload`, etc. in addition to the parent `telecalling` feature.

**Migration needed:** No schema change (still `text[]`). Only logic changes:
1. Backend: validate sub-features, auto-populate on parent enable
2. Frontend sidebar: check sub-features for visibility
3. Operator: toggle UI for sub-features

---

## 5. Read-Only Section Views

Each sidebar item, when clicked, shows a read-only summary in the content area. Data loads lazily on section select with skeleton loading states.

### Overview (Default View)

Existing stat cards (total leads, active leads, messages sent/received 30d, team members, last activity) restyled with warm palette. Each card gets:
- `bg-white rounded-2xl border border-warm p-5`
- Icon in muted primary circle
- Label: `text-xs uppercase tracking-wider text-ink-muted`
- Value: `text-2xl font-bold text-ink`
- Grid: `grid-cols-2 lg:grid-cols-3 gap-4`

### Inbox

- Stat: open handover count
- Table: recent 20 conversations with handover status, lead name, last message preview (truncated 80 chars), channel badge, time ago
- Empty state: "No inbox conversations" with Inbox icon

**Backend:** `GET /api/v1/operator/clients/{tenant_id}/dashboard/inbox`

### Conversations

- Stat: total conversation count
- Table: recent 20 conversations with lead name, last message, channel, message count, last active time
- Empty state: "No conversations yet"

**Backend:** `GET /api/v1/operator/clients/{tenant_id}/dashboard/conversations`

### Segments (Leads)

- 4 stat cards: Segment A (Hot), B (Warm), C (Cold), D (Disqualified) with counts and color-coded badges
- Total leads count
- Recent 10 leads table: name, phone, segment badge, score, source, created date

**Backend:** `GET /api/v1/operator/clients/{tenant_id}/dashboard/leads`

### Inbound Leads

- Stat: total inbound count
- Table: recent 20 inbound leads with name, phone, channel, source, segment, created date
- Filter: by channel (all/whatsapp/instagram/facebook/telegram)

**Backend:** Uses same `/dashboard/leads` endpoint with `?direction=inbound`

### Outbound Leads

- Stat: total outbound count (CSV uploaded)
- Table: recent 20 outbound leads with name, phone, batch, segment, created date

**Backend:** Uses same `/dashboard/leads` endpoint with `?direction=outbound`

### Templates

- Stat: total templates, approved count, pending count
- Table: all templates with name, status (approved/pending/rejected badge), category, language, last synced
- Empty state: "No templates created"

**Backend:** `GET /api/v1/operator/clients/{tenant_id}/dashboard/templates`

### Numbers Pool

- Stat: total numbers, active count
- Table: phone numbers with number, display name, quality rating badge (GREEN/YELLOW/RED), status, messaging limit tier
- Empty state: "No phone numbers configured"

**Backend:** `GET /api/v1/operator/clients/{tenant_id}/dashboard/numbers`

### Knowledge Base

- Stat: total documents, total chunks
- Table: documents with title, chunk count, created date, file type
- Empty state: "No knowledge base documents"

**Backend:** `GET /api/v1/operator/clients/{tenant_id}/dashboard/knowledge`

### Analytics

- Key metrics cards: Total messages (30d), Delivery rate, Response rate, Avg score
- Telecalling stats (if enabled): Total calls, Connect rate, Avg duration
- No charts — numbers only for operator overview

**Backend:** `GET /api/v1/operator/clients/{tenant_id}/dashboard/analytics`

### Team

Existing team view restyled. Owner info card + callers table with name, role, active status, score, shift hours.

**Backend:** Existing `GET /api/v1/operator/clients/{tenant_id}/team`

### Telecalling Sub-Views

Each telecalling sub-item gets its own content view:

**Upload:**
- Stat: total upload batches, total leads uploaded
- Table: upload history with batch name, lead count, assigned caller, date, status

**Dialer:**
- Stat: total calls today, connect rate
- Table: recent 20 call logs with lead name, caller, duration, outcome badge, date

**Scheduled Calls:**
- Stat: pending callbacks count
- Table: upcoming scheduled calls with lead name, assigned caller, scheduled time, type

**Call Notes:**
- Stat: total notes
- Table: recent 20 notes with lead name, caller, note preview (truncated), date

**Backend:** `GET /api/v1/operator/clients/{tenant_id}/dashboard/telecalling?section=upload|dialer|scheduled|notes`

---

## 6. Operator-Only Sections

### Configuration (Existing, Restyled)

Feature toggles are now in the sidebar (moved out of this view). This section keeps:
- Credential status cards (WhatsApp, TeleCMI, Groq, Razorpay) with configured/incomplete/not_configured badges
- Key settings summary (AI auto-reply, re-engagement, booking config)

All restyled with warm palette.

### Health (Existing, Restyled)

Existing health view restyled:
- Channel health cards with status dots (green pulse animation for healthy, red for unhealthy)
- Token status with icon
- Delivery stats (7d) with progress bar for success rate
- Recent errors table
- Open incidents table

### Management (Existing, Restyled)

Actions restyled:
- Reset Owner Password: `bg-white border border-warm hover:border-primary` card with Key icon
- Suspend/Activate: Same card style, PowerOff icon, amber/green depending on current state
- Wipe All Leads: `border-danger/30 hover:border-danger` card with Trash2 icon, red text

Owner info card + team members table (existing).

### Data Ops (NEW)

Dedicated data management section with clear/delete operations.

**Layout:** Grid of action cards, each showing:
- Icon + data type name
- Record count (fetched on section load)
- "Clear" button
- Description of what will be deleted

**Data types:**

| Data Type | Icon | What Gets Deleted | Audit Event |
|---|---|---|---|
| Broadcast History | `Radio` | broadcasts + broadcast_recipients + broadcast_lead_scores | `data_clear:broadcasts` |
| Message History | `MessageSquare` | All messages for tenant | `data_clear:messages` |
| Call Logs | `PhoneCall` | All call_logs entries | `data_clear:call_logs` |
| Lead Data | `Users` | All leads + associated data (existing wipe) | `data_clear:leads` |
| Knowledge Base | `BookOpen` | knowledge_documents + knowledge_chunks + embeddings | `data_clear:knowledge` |
| Templates Cache | `FileCheck` | Cached meta_templates (not Meta-approved) | `data_clear:templates` |
| Analytics Data | `BarChart2` | analytics snapshots (whatsapp_insights_snapshots) | `data_clear:analytics` |

**Confirmation dialog:**

Each clear action opens a modal:
```
┌─────────────────────────────────────────┐
│  ⚠️  Clear Broadcast History            │
│                                          │
│  This will permanently delete:           │
│  • 47 broadcasts                         │
│  • 12,340 recipient records              │
│  • 47 lead score records                 │
│                                          │
│  This action cannot be undone.           │
│                                          │
│  Type "Astrotamil" to confirm:           │
│  ┌──────────────────────────────┐       │
│  │                              │       │
│  └──────────────────────────────┘       │
│                                          │
│  [Cancel]              [Delete Forever]  │
└─────────────────────────────────────────┘
```

- Modal: `bg-white rounded-2xl shadow-xl`
- Warning icon: amber background circle
- Count of records: bold, fetched from a count endpoint
- Type-to-confirm: must exactly match client name
- Delete button: `bg-danger text-white`, disabled until name typed correctly
- Cancel button: `bg-white border border-warm`

**Backend endpoints:**

```
POST /api/v1/operator/clients/{tenant_id}/clear/{data_type}
  data_type: broadcasts | messages | call_logs | leads | knowledge | templates | analytics
  Response: { deleted_count: number, detail: string }
  Auth: system_admin
  Audit: logged with data_type and counts

GET /api/v1/operator/clients/{tenant_id}/clear/{data_type}/count
  Response: { count: number, detail: { [table]: number } }
  Auth: system_admin
```

---

## 7. Sign Out

**Location:** Operator sidebar footer.

**Implementation:**
- Display current user email (fetched from Supabase auth session)
- "Sign Out" button with `LogOut` icon
- Clicking calls `supabase.auth.signOut()`
- Redirects to `/operator/login`
- Button styling: `text-ink-secondary hover:text-danger transition-colors`

---

## 8. Skeleton Loading States

Every section view shows a skeleton while data loads:
- Stat cards: pulsing gray rectangles matching card dimensions
- Tables: 5 rows of pulsing horizontal bars
- Animation: `animate-pulse bg-surface-mid rounded`

---

## 9. Files Changed

### New Files

| File | Purpose |
|---|---|
| `frontend/app/operator/(console)/client/[id]/page.tsx` | Rewritten — main layout with sidebar + content |
| `frontend/app/operator/(console)/client/[id]/sidebar.tsx` | Client detail sidebar with toggles |
| `frontend/app/operator/(console)/client/[id]/views/overview.tsx` | Overview stats view |
| `frontend/app/operator/(console)/client/[id]/views/inbox.tsx` | Inbox + conversations view |
| `frontend/app/operator/(console)/client/[id]/views/leads.tsx` | Segments, inbound, outbound leads |
| `frontend/app/operator/(console)/client/[id]/views/content.tsx` | Templates + Knowledge Base + Numbers |
| `frontend/app/operator/(console)/client/[id]/views/analytics.tsx` | Analytics snapshot |
| `frontend/app/operator/(console)/client/[id]/views/team.tsx` | Team members |
| `frontend/app/operator/(console)/client/[id]/views/telecalling.tsx` | All telecalling sub-views |
| `frontend/app/operator/(console)/client/[id]/views/config.tsx` | Configuration/credentials |
| `frontend/app/operator/(console)/client/[id]/views/health.tsx` | Health monitoring |
| `frontend/app/operator/(console)/client/[id]/views/management.tsx` | Actions + owner info |
| `frontend/app/operator/(console)/client/[id]/views/data-ops.tsx` | Data clear operations |
| `frontend/app/operator/(console)/client/[id]/components/confirm-dialog.tsx` | Type-to-confirm dialog |
| `frontend/app/operator/(console)/client/[id]/components/stat-card.tsx` | Reusable stat card |
| `frontend/app/operator/(console)/client/[id]/components/skeleton.tsx` | Loading skeletons |
| `frontend/app/operator/(console)/components/operator-sidebar.tsx` | Operator console sidebar |

### Modified Files

| File | Change |
|---|---|
| `frontend/app/operator/(console)/layout.tsx` | Replace top nav with sidebar layout, add sign out |
| `frontend/app/operator/(console)/page.tsx` | Add grid view toggle, restyle with warm palette |
| `frontend/app/operator/login/page.tsx` | Restyle login page with warm palette |
| `backend/app/routes/operator.py` | Add dashboard data endpoints, data clear endpoints, sub-feature validation |
| `frontend/components/sidebar.tsx` | Check sub-features (telecalling.dialer etc.) for visibility |

### DB Migration

One new migration for sub-feature support:
- Backfill existing tenants that have `telecalling` to also have `telecalling.dialer`, `telecalling.upload`, `telecalling.scheduled`, `telecalling.notes`
- No schema change (still `text[]`)

---

## 10. Design Constraints

- **No secret exposure:** Config view shows credential status, never actual values
- **System admin only:** All endpoints use `Depends(get_system_admin)`
- **Read-only dashboard:** Operator cannot modify client data through dashboard views — only through explicit management actions
- **Audit trail:** All data clear operations are audit-logged with counts
- **Type-to-confirm:** Destructive data operations require typing the client name
- **Feature toggles are immediate:** Changes to enabled features take effect on the client's next page load
- **Warm palette everywhere:** No cold grays remain in the operator console
- **Skeleton loading:** Every async data load shows a skeleton, never a spinner or blank
- **Product sidebar parity:** The client detail sidebar must match the product sidebar's items, icons, and order exactly
