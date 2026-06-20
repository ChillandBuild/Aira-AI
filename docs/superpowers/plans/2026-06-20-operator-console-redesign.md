# Operator Console Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the operator console with the product's warm palette, sidebar layout, mirrored client dashboard with read-only views, modular feature toggles (including telecalling sub-features), data management operations, grid/table view toggle, and sign out.

**Architecture:** Replace operator console's cold gray/indigo UI with the product's warm design tokens already defined in tailwind.config.ts (bg-background, bg-surface-mid, text-ink, border-border, text-primary, shadow-card, etc.). Convert the top navigation bar into a fixed sidebar layout. Rebuild the client detail page with a mirrored product sidebar containing feature toggles and read-only data views per section. All new backend endpoints follow the existing pattern in operator.py using `Depends(get_system_admin)`.

**Tech Stack:** Next.js 14 App Router (TypeScript, Tailwind CSS), FastAPI (Python, Pydantic), Supabase (PostgreSQL)

## Global Constraints

- All operator backend endpoints use `Depends(get_system_admin)` auth guard
- Never expose secret credential values — only status (configured/incomplete/not_configured)
- All destructive operations are audit-logged via `record_audit_event()`
- Use existing Tailwind design tokens from `frontend/tailwind.config.ts`: `background` (#faf8f5), `surface-mid` (#f0ece4), `primary` (#5b21b6), `primary-light` (#f5f3ff), `ink` (#1c1917), `ink-secondary` (#78716c), `ink-muted` (#a8a29e), `border` (#e8e3db), `border-subtle` (#f0ece4), `success` (#059669), `warning` (#d97706), `danger` (#e11d48)
- Use existing Tailwind shadows: `shadow-card`, `shadow-card-hover`, `shadow-sm`
- Use existing border radius: `rounded-card` (1.25rem), `rounded-xl`, `rounded-2xl`
- Font is Manrope via `font-display` / `font-body` classes (already configured)
- The `apiFetch` wrapper used in operator pages is defined inline (not from `lib/api.ts`), using `API_URL` and `getAuthHeaders` from `@/lib/api`
- Feature toggles in DB: `tenants.enabled_features text[]` — supports dot-notation for sub-features (e.g., `telecalling.dialer`)
- No test files required for frontend components (Next.js pages — test manually in browser)
- Commits go to the `main` branch in `c:\Users\vskee\Desktop\Aira.AI\Aira-Ai`

---

### Task 1: Backend — Fix health endpoint + add dashboard data endpoints + data clear endpoints

**Files:**
- Modify: `backend/app/routes/operator.py`

**Interfaces:**
- Produces: All new endpoints consumed by Tasks 5-6 frontend views:
  - `GET /api/v1/operator/clients/{tenant_id}/health` — FIXED: `delivery_error` → `delivery_error_title`
  - `GET /api/v1/operator/clients/{tenant_id}/dashboard/inbox` → `{ handover_count, conversations: [...] }`
  - `GET /api/v1/operator/clients/{tenant_id}/dashboard/leads` → `{ segments, total, recent: [...] }`
  - `GET /api/v1/operator/clients/{tenant_id}/dashboard/templates` → `{ total, approved, pending, templates: [...] }`
  - `GET /api/v1/operator/clients/{tenant_id}/dashboard/numbers` → `{ total, numbers: [...] }`
  - `GET /api/v1/operator/clients/{tenant_id}/dashboard/knowledge` → `{ total_docs, total_chunks, documents: [...] }`
  - `GET /api/v1/operator/clients/{tenant_id}/dashboard/analytics` → `{ messages_30d, delivery_rate, ... }`
  - `GET /api/v1/operator/clients/{tenant_id}/dashboard/telecalling?section=upload|dialer|scheduled|notes` → section-specific data
  - `GET /api/v1/operator/clients/{tenant_id}/clear/{data_type}/count` → `{ count, detail: {...} }`
  - `POST /api/v1/operator/clients/{tenant_id}/clear/{data_type}` → `{ deleted_count, detail }`
  - `PATCH /api/v1/operator/clients/{tenant_id}/features` — UPDATED: validate sub-features

- [ ] **Step 1: Fix the health endpoint bug**

The `client_health` endpoint at line 482 queries `delivery_error` which doesn't exist on the messages table. The actual columns are `delivery_error_code` (int) and `delivery_error_title` (text) from migration 061.

In `backend/app/routes/operator.py`, change the `recent_errors` query (around line 481):

```python
    recent_errors = (
        db.table("messages").select("id, delivery_error_title, created_at")
        .eq("tenant_id", tenant_id).eq("delivery_status", "failed")
        .order("created_at", desc=True).limit(10).execute()
    )
```

And update the return mapping (around line 501):

```python
        "recent_errors": [
            {"message_id": r["id"], "error": r.get("delivery_error_title"), "created_at": r["created_at"]}
            for r in (recent_errors.data or [])
        ],
```

- [ ] **Step 2: Update feature validation to accept sub-features**

In the `update_features` endpoint (line 182), expand the valid features set:

```python
    valid_features = {
        "whatsapp", "telecalling", "instagram", "facebook", "telegram",
        "telecalling.dialer", "telecalling.upload", "telecalling.scheduled", "telecalling.notes",
    }
```

Add auto-population logic: when `telecalling` is added and no sub-features exist, add all 4. When `telecalling` is removed, remove all sub-features:

```python
    if payload.features is not None:
        invalid = set(payload.features) - valid_features
        if invalid:
            raise HTTPException(status_code=400, detail=f"Invalid features: {', '.join(invalid)}")
        features = list(payload.features)
        tc_subs = {"telecalling.dialer", "telecalling.upload", "telecalling.scheduled", "telecalling.notes"}
        if "telecalling" in features and not (set(features) & tc_subs):
            features.extend(tc_subs)
        if "telecalling" not in features:
            features = [f for f in features if f not in tc_subs]
    elif payload.service is not None:
        features = _FEATURE_MAP[payload.service]
    else:
        raise HTTPException(status_code=400, detail="Provide 'features' or 'service'")
```

Also update `create_client` (line 104) to auto-add sub-features when telecalling is included:

```python
    features = _FEATURE_MAP[payload.service]
    tc_subs = ["telecalling.dialer", "telecalling.upload", "telecalling.scheduled", "telecalling.notes"]
    if "telecalling" in features:
        features = features + tc_subs
```

- [ ] **Step 3: Add dashboard data endpoints**

Add these endpoints to `backend/app/routes/operator.py`, each following the same pattern as existing endpoints (tenant existence check, `Depends(get_system_admin)`):

**Inbox endpoint:**
```python
@router.get("/clients/{tenant_id}/dashboard/inbox")
def client_dashboard_inbox(tenant_id: str, _admin: dict = Depends(get_system_admin)):
    db = get_supabase()
    tenant = db.table("tenants").select("id").eq("id", tenant_id).maybe_single().execute()
    if not tenant.data:
        raise HTTPException(status_code=404, detail="Tenant not found")

    handovers = db.table("chat_handovers").select("id", count="exact").eq("tenant_id", tenant_id).eq("status", "needs_human_attention").execute()

    convos = (
        db.table("conversations")
        .select("id, lead_id, last_message, last_message_at, channel")
        .eq("tenant_id", tenant_id)
        .order("last_message_at", desc=True)
        .limit(20)
        .execute()
    )

    lead_ids = [c["lead_id"] for c in (convos.data or []) if c.get("lead_id")]
    leads_map: dict = {}
    if lead_ids:
        leads = db.table("leads").select("id, name, phone").in_("id", lead_ids).execute()
        leads_map = {l["id"]: l for l in (leads.data or [])}

    conversations = []
    for c in (convos.data or []):
        lead = leads_map.get(c.get("lead_id"), {})
        conversations.append({
            "id": c["id"],
            "lead_name": lead.get("name", "Unknown"),
            "lead_phone": lead.get("phone"),
            "last_message": (c.get("last_message") or "")[:80],
            "channel": c.get("channel", "whatsapp"),
            "last_message_at": c.get("last_message_at"),
        })

    return {"handover_count": handovers.count or 0, "conversations": conversations}
```

**Leads endpoint:**
```python
@router.get("/clients/{tenant_id}/dashboard/leads")
def client_dashboard_leads(tenant_id: str, direction: str = "all", _admin: dict = Depends(get_system_admin)):
    db = get_supabase()
    tenant = db.table("tenants").select("id").eq("id", tenant_id).maybe_single().execute()
    if not tenant.data:
        raise HTTPException(status_code=404, detail="Tenant not found")

    base = db.table("leads").select("id", count="exact").eq("tenant_id", tenant_id).is_("deleted_at", "null")
    total = base.execute()
    seg_a = db.table("leads").select("id", count="exact").eq("tenant_id", tenant_id).is_("deleted_at", "null").eq("segment", "A").execute()
    seg_b = db.table("leads").select("id", count="exact").eq("tenant_id", tenant_id).is_("deleted_at", "null").eq("segment", "B").execute()
    seg_c = db.table("leads").select("id", count="exact").eq("tenant_id", tenant_id).is_("deleted_at", "null").eq("segment", "C").execute()
    seg_d = db.table("leads").select("id", count="exact").eq("tenant_id", tenant_id).is_("deleted_at", "null").eq("segment", "D").execute()

    q = db.table("leads").select("id, name, phone, segment, score, source, created_at, opt_in_source").eq("tenant_id", tenant_id).is_("deleted_at", "null")
    if direction == "inbound":
        q = q.in_("opt_in_source", ["organic", "meta_ads", "instagram", "facebook", "telegram"])
    elif direction == "outbound":
        q = q.eq("opt_in_source", "csv")
    recent = q.order("created_at", desc=True).limit(20).execute()

    return {
        "total": total.count or 0,
        "segments": {"A": seg_a.count or 0, "B": seg_b.count or 0, "C": seg_c.count or 0, "D": seg_d.count or 0},
        "recent": recent.data or [],
    }
```

**Templates endpoint:**
```python
@router.get("/clients/{tenant_id}/dashboard/templates")
def client_dashboard_templates(tenant_id: str, _admin: dict = Depends(get_system_admin)):
    db = get_supabase()
    tenant = db.table("tenants").select("id").eq("id", tenant_id).maybe_single().execute()
    if not tenant.data:
        raise HTTPException(status_code=404, detail="Tenant not found")

    templates = (
        db.table("meta_templates")
        .select("id, name, status, category, language, updated_at")
        .eq("tenant_id", tenant_id)
        .order("updated_at", desc=True)
        .execute()
    )
    data = templates.data or []
    approved = sum(1 for t in data if t.get("status") == "APPROVED")
    pending = sum(1 for t in data if t.get("status") == "PENDING")

    return {"total": len(data), "approved": approved, "pending": pending, "templates": data}
```

**Numbers endpoint:**
```python
@router.get("/clients/{tenant_id}/dashboard/numbers")
def client_dashboard_numbers(tenant_id: str, _admin: dict = Depends(get_system_admin)):
    db = get_supabase()
    tenant = db.table("tenants").select("id").eq("id", tenant_id).maybe_single().execute()
    if not tenant.data:
        raise HTTPException(status_code=404, detail="Tenant not found")

    numbers = (
        db.table("phone_numbers")
        .select("id, phone_number, display_name, quality_rating, status, messaging_limit_tier")
        .eq("tenant_id", tenant_id)
        .order("created_at", desc=True)
        .execute()
    )
    data = numbers.data or []
    active = sum(1 for n in data if n.get("status") == "active")

    return {"total": len(data), "active": active, "numbers": data}
```

**Knowledge endpoint:**
```python
@router.get("/clients/{tenant_id}/dashboard/knowledge")
def client_dashboard_knowledge(tenant_id: str, _admin: dict = Depends(get_system_admin)):
    db = get_supabase()
    tenant = db.table("tenants").select("id").eq("id", tenant_id).maybe_single().execute()
    if not tenant.data:
        raise HTTPException(status_code=404, detail="Tenant not found")

    docs = (
        db.table("knowledge_documents")
        .select("id, title, file_type, created_at")
        .eq("tenant_id", tenant_id)
        .order("created_at", desc=True)
        .execute()
    )
    total_chunks = db.table("knowledge_chunks").select("id", count="exact").eq("tenant_id", tenant_id).execute()

    doc_data = []
    for d in (docs.data or []):
        chunk_count = db.table("knowledge_chunks").select("id", count="exact").eq("document_id", d["id"]).execute()
        doc_data.append({**d, "chunk_count": chunk_count.count or 0})

    return {"total_docs": len(docs.data or []), "total_chunks": total_chunks.count or 0, "documents": doc_data}
```

**Analytics endpoint:**
```python
@router.get("/clients/{tenant_id}/dashboard/analytics")
def client_dashboard_analytics(tenant_id: str, _admin: dict = Depends(get_system_admin)):
    from datetime import datetime, timezone, timedelta
    db = get_supabase()
    tenant = db.table("tenants").select("id, enabled_features").eq("id", tenant_id).maybe_single().execute()
    if not tenant.data:
        raise HTTPException(status_code=404, detail="Tenant not found")

    thirty_days_ago = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()

    total_msgs = db.table("messages").select("id", count="exact").eq("tenant_id", tenant_id).gte("created_at", thirty_days_ago).execute()
    delivered = db.table("messages").select("id", count="exact").eq("tenant_id", tenant_id).eq("direction", "outbound").eq("delivery_status", "delivered").gte("created_at", thirty_days_ago).execute()
    sent = db.table("messages").select("id", count="exact").eq("tenant_id", tenant_id).eq("direction", "outbound").gte("created_at", thirty_days_ago).execute()
    avg_score_rows = db.table("leads").select("score").eq("tenant_id", tenant_id).is_("deleted_at", "null").not_.is_("score", "null").execute()

    sent_count = sent.count or 0
    delivered_count = delivered.count or 0
    delivery_rate = round((delivered_count / sent_count) * 100, 1) if sent_count > 0 else 0
    scores = [r["score"] for r in (avg_score_rows.data or []) if r.get("score") is not None]
    avg_score = round(sum(scores) / len(scores), 1) if scores else 0

    result: dict = {
        "messages_30d": total_msgs.count or 0,
        "delivery_rate": delivery_rate,
        "avg_score": avg_score,
    }

    if "telecalling" in (tenant.data.get("enabled_features") or []):
        calls = db.table("call_logs").select("id", count="exact").eq("tenant_id", tenant_id).gte("created_at", thirty_days_ago).execute()
        connected = db.table("call_logs").select("id", count="exact").eq("tenant_id", tenant_id).eq("disposition", "answered").gte("created_at", thirty_days_ago).execute()
        call_count = calls.count or 0
        connect_count = connected.count or 0
        result["total_calls"] = call_count
        result["connect_rate"] = round((connect_count / call_count) * 100, 1) if call_count > 0 else 0

    return result
```

**Telecalling endpoint:**
```python
@router.get("/clients/{tenant_id}/dashboard/telecalling")
def client_dashboard_telecalling(tenant_id: str, section: str = "dialer", _admin: dict = Depends(get_system_admin)):
    from datetime import datetime, timezone, timedelta
    db = get_supabase()
    tenant = db.table("tenants").select("id").eq("id", tenant_id).maybe_single().execute()
    if not tenant.data:
        raise HTTPException(status_code=404, detail="Tenant not found")

    if section == "upload":
        batches = (
            db.table("telecalling_upload_batches")
            .select("id, file_name, lead_count, created_at, status")
            .eq("tenant_id", tenant_id)
            .order("created_at", desc=True)
            .limit(20)
            .execute()
        )
        total = db.table("telecalling_upload_batches").select("id", count="exact").eq("tenant_id", tenant_id).execute()
        return {"total_batches": total.count or 0, "batches": batches.data or []}

    elif section == "dialer":
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0).isoformat()
        calls_today = db.table("call_logs").select("id", count="exact").eq("tenant_id", tenant_id).gte("created_at", today).execute()
        connected_today = db.table("call_logs").select("id", count="exact").eq("tenant_id", tenant_id).eq("disposition", "answered").gte("created_at", today).execute()
        recent_calls = (
            db.table("call_logs")
            .select("id, lead_id, caller_id, duration_seconds, disposition, created_at")
            .eq("tenant_id", tenant_id)
            .order("created_at", desc=True)
            .limit(20)
            .execute()
        )
        call_count = calls_today.count or 0
        connect_count = connected_today.count or 0
        return {
            "calls_today": call_count,
            "connect_rate": round((connect_count / call_count) * 100, 1) if call_count > 0 else 0,
            "recent_calls": recent_calls.data or [],
        }

    elif section == "scheduled":
        pending = (
            db.table("follow_up_jobs")
            .select("id, lead_id, scheduled_for, cadence, created_at")
            .eq("tenant_id", tenant_id)
            .eq("status", "pending")
            .order("scheduled_for")
            .limit(20)
            .execute()
        )
        total = db.table("follow_up_jobs").select("id", count="exact").eq("tenant_id", tenant_id).eq("status", "pending").execute()
        return {"pending_count": total.count or 0, "scheduled": pending.data or []}

    elif section == "notes":
        notes = (
            db.table("lead_notes")
            .select("id, lead_id, note, author_name, created_at")
            .eq("tenant_id", tenant_id)
            .order("created_at", desc=True)
            .limit(20)
            .execute()
        )
        total = db.table("lead_notes").select("id", count="exact").eq("tenant_id", tenant_id).execute()
        return {"total_notes": total.count or 0, "notes": notes.data or []}

    raise HTTPException(status_code=400, detail="Invalid section. Use: upload, dialer, scheduled, notes")
```

- [ ] **Step 4: Add data clear endpoints**

```python
_CLEAR_TABLES: dict[str, list[str]] = {
    "broadcasts": ["broadcast_recipients", "broadcast_lead_scores", "broadcast_failed_contacts", "broadcast_tags", "scheduled_broadcasts"],
    "messages": ["messages"],
    "call_logs": ["call_logs"],
    "leads": [],  # handled by existing wipe-leads
    "knowledge": ["knowledge_chunks", "knowledge_documents"],
    "templates": ["meta_templates"],
    "analytics": ["whatsapp_insights_snapshots"],
}


@router.get("/clients/{tenant_id}/clear/{data_type}/count")
def clear_count(tenant_id: str, data_type: str, _admin: dict = Depends(get_system_admin)):
    db = get_supabase()
    if data_type not in _CLEAR_TABLES:
        raise HTTPException(status_code=400, detail=f"Invalid data type: {data_type}")
    tenant = db.table("tenants").select("id").eq("id", tenant_id).maybe_single().execute()
    if not tenant.data:
        raise HTTPException(status_code=404, detail="Tenant not found")

    if data_type == "leads":
        count = db.table("leads").select("id", count="exact").eq("tenant_id", tenant_id).is_("deleted_at", "null").execute()
        return {"count": count.count or 0, "detail": {"leads": count.count or 0}}

    detail: dict = {}
    total = 0
    for table in _CLEAR_TABLES[data_type]:
        c = db.table(table).select("id", count="exact").eq("tenant_id", tenant_id).execute()
        detail[table] = c.count or 0
        total += c.count or 0
    return {"count": total, "detail": detail}


@router.post("/clients/{tenant_id}/clear/{data_type}")
def clear_data(tenant_id: str, data_type: str, _admin: dict = Depends(get_system_admin)):
    db = get_supabase()
    if data_type not in _CLEAR_TABLES:
        raise HTTPException(status_code=400, detail=f"Invalid data type: {data_type}")
    tenant = db.table("tenants").select("id, name").eq("id", tenant_id).maybe_single().execute()
    if not tenant.data:
        raise HTTPException(status_code=404, detail="Tenant not found")

    if data_type == "leads":
        # Reuse existing wipe logic
        for table in ("messages", "lead_notes", "chat_handovers", "follow_up_jobs", "bookings",
                       "broadcast_recipients", "broadcast_lead_scores", "broadcast_failed_contacts",
                       "broadcast_tags", "scheduled_broadcasts"):
            try:
                db.table(table).delete().eq("tenant_id", tenant_id).execute()
            except Exception as e:
                logger.warning("clear leads: could not clear %s: %s", table, e)
        result = db.table("leads").delete().eq("tenant_id", tenant_id).execute()
        deleted = len(result.data or [])
    else:
        deleted = 0
        tables = _CLEAR_TABLES[data_type]
        for table in tables:
            try:
                result = db.table(table).delete().eq("tenant_id", tenant_id).execute()
                deleted += len(result.data or [])
            except Exception as e:
                logger.warning("clear %s: could not clear %s: %s", data_type, table, e)

    logger.warning("OPERATOR CLEAR %s: %d records deleted for tenant %s", data_type, deleted, tenant_id)
    record_audit_event(
        db,
        tenant_id=tenant_id,
        actor_user_id=_admin.get("user_id"),
        actor_role="system_admin",
        action=f"operator.data_cleared:{data_type}",
        target_type="tenant",
        target_id=tenant_id,
        metadata={"data_type": data_type, "deleted_count": deleted, "tenant_name": tenant.data["name"]},
    )
    return {"deleted_count": deleted, "data_type": data_type}
```

- [ ] **Step 5: Verify by starting the backend**

Run: `cd backend && python -c "from app.routes.operator import router; print('OK: endpoints registered')"` (or run the FastAPI server)

- [ ] **Step 6: Commit**

```bash
git add backend/app/routes/operator.py
git commit -m "feat(operator): fix health endpoint, add dashboard data + data clear endpoints + sub-feature validation"
```

---

### Task 2: Operator console layout — sidebar + sign out + warm palette

**Files:**
- Modify: `frontend/app/operator/(console)/layout.tsx` (rewrite)
- Create: `frontend/app/operator/(console)/components/operator-sidebar.tsx`

**Interfaces:**
- Consumes: Supabase auth session for sign out
- Produces: Layout shell with sidebar that Tasks 3-6 render inside

- [ ] **Step 1: Create the operator sidebar component**

Create `frontend/app/operator/(console)/components/operator-sidebar.tsx`:

```tsx
"use client";
import { usePathname, useRouter } from "next/navigation";
import { LayoutGrid, Clock, LogOut } from "lucide-react";
import { createClient } from "@/lib/supabase/client";

const NAV_ITEMS = [
  { href: "/operator", icon: LayoutGrid, label: "Clients" },
  { href: "/operator/scheduler", icon: Clock, label: "Schedulers" },
];

export function OperatorSidebar({ userEmail }: { userEmail: string }) {
  const pathname = usePathname();
  const router = useRouter();

  async function handleSignOut() {
    const supabase = createClient();
    await supabase.auth.signOut();
    router.push("/operator/login");
  }

  return (
    <aside className="fixed left-0 top-0 w-[240px] h-screen bg-white border-r border-border flex flex-col z-40">
      {/* Header */}
      <div className="px-6 py-5 border-b border-border-subtle">
        <div className="flex items-center gap-2">
          <span className="text-lg font-bold text-ink font-display">
            Aira <span className="text-primary">AI</span>
          </span>
        </div>
        <span className="inline-block mt-1.5 text-[10px] font-semibold text-primary uppercase tracking-[0.15em] bg-primary-light rounded px-2 py-0.5">
          Operator
        </span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4 space-y-1">
        {NAV_ITEMS.map((item) => {
          const isActive = item.href === "/operator"
            ? pathname === "/operator"
            : pathname.startsWith(item.href);
          return (
            <a
              key={item.href}
              href={item.href}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 ${
                isActive
                  ? "bg-primary-light text-primary border-l-[3px] border-primary"
                  : "text-ink-secondary hover:bg-surface-mid hover:text-ink"
              }`}
            >
              <item.icon size={18} />
              {item.label}
            </a>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="px-4 py-4 border-t border-border-subtle">
        <p className="text-xs text-ink-muted truncate mb-2">{userEmail}</p>
        <button
          onClick={handleSignOut}
          className="flex items-center gap-2 w-full px-3 py-2 rounded-xl text-sm text-ink-secondary hover:text-danger hover:bg-red-50 transition-all duration-200"
        >
          <LogOut size={16} />
          Sign Out
        </button>
      </div>
    </aside>
  );
}
```

- [ ] **Step 2: Rewrite the operator layout**

Rewrite `frontend/app/operator/(console)/layout.tsx`:

```tsx
import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { OperatorSidebar } from "./components/operator-sidebar";

export default async function OperatorLayout({ children }: { children: React.ReactNode }) {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) redirect("/operator/login");

  const { data: { session } } = await supabase.auth.getSession();
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  try {
    const meRes = await fetch(`${apiUrl}/api/v1/operator/me`, {
      headers: { Authorization: `Bearer ${session?.access_token}` },
      cache: "no-store",
    });
    if (meRes.ok) {
      const me = await meRes.json();
      if (!me.is_system_admin) redirect("/dashboard");
    } else {
      redirect("/dashboard");
    }
  } catch {
    redirect("/dashboard");
  }

  return (
    <div className="min-h-screen bg-background">
      <OperatorSidebar userEmail={user.email || ""} />
      <main className="ml-[240px] min-h-screen">
        <div className="max-w-6xl mx-auto px-8 py-8">{children}</div>
      </main>
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/app/operator/\(console\)/layout.tsx frontend/app/operator/\(console\)/components/operator-sidebar.tsx
git commit -m "feat(operator): replace top nav with sidebar layout + sign out"
```

---

### Task 3: Clients list page — grid view + warm palette restyle

**Files:**
- Modify: `frontend/app/operator/(console)/page.tsx` (rewrite)

**Interfaces:**
- Consumes: `GET /api/v1/operator/clients` (existing)
- Produces: Grid/table view toggle, warm-styled client cards

- [ ] **Step 1: Rewrite the clients list page**

Rewrite `frontend/app/operator/(console)/page.tsx` with:

1. View toggle (grid/table) stored in `localStorage` key `operator-clients-view`
2. Grid view: `grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6`, each card with warm styling
3. Table view: existing table restyled with warm palette tokens
4. Create modal restyled with warm palette
5. All `bg-gray-*` → warm tokens, `indigo-*` → `primary`

The full component should:
- Use `useState<"grid" | "table">` for view mode, initialized from localStorage
- Grid cards: `bg-white rounded-card border border-border shadow-card hover:shadow-card-hover transition-all duration-200 cursor-pointer`
- Card content: client name (`text-ink font-semibold`), tenant ID (mono, truncated, copy button), feature badges (`bg-primary-muted text-primary`), status dot + badge, created date, action icons at bottom
- Table: header row `bg-surface-mid text-ink-secondary`, rows `hover:bg-surface-mid/50`, borders `border-border`
- "New Client" button: `bg-primary hover:bg-primary-dark`
- Create modal: `bg-white rounded-card shadow-xl`, overlay `bg-black/40 backdrop-blur-sm`, inputs `border-border rounded-xl focus:ring-primary/20 focus:border-primary`
- Feature checkboxes in create modal: styled as toggle pills
- Error alerts: `bg-red-50 border-danger/20 text-danger`
- Success/temp password: `bg-green-50 border-success/20`

Key styling details for grid cards:
```tsx
<div className="bg-white rounded-card border border-border shadow-card hover:shadow-card-hover transition-all duration-200 cursor-pointer p-5"
     onClick={() => router.push(`/operator/client/${client.id}`)}>
  <div className="flex items-start justify-between mb-3">
    <div>
      <h3 className="text-base font-semibold text-ink">{client.name}</h3>
      <p className="text-xs text-ink-muted font-mono mt-0.5">{client.id.slice(0, 8)}…</p>
    </div>
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium ${
      client.status === "active" ? "bg-green-50 text-success" : "bg-red-50 text-danger"
    }`}>
      <span className={`w-1.5 h-1.5 rounded-full ${client.status === "active" ? "bg-success" : "bg-danger"}`} />
      {client.status}
    </span>
  </div>
  <div className="flex flex-wrap gap-1 mb-3">
    {(client.enabled_features || []).filter(f => !f.includes(".")).map(f => (
      <span key={f} className="px-2 py-0.5 rounded-full text-[11px] font-medium bg-primary-muted text-primary">
        {{"whatsapp":"WA","telecalling":"TC","instagram":"IG","facebook":"FB","telegram":"TG"}[f] || f}
      </span>
    ))}
  </div>
  <p className="text-xs text-ink-muted mb-3">Created {new Date(client.created_at).toLocaleDateString("en-IN")}</p>
  <div className="border-t border-border-subtle pt-3 flex items-center gap-2">
    {/* action buttons with e.stopPropagation() */}
  </div>
</div>
```

View toggle buttons:
```tsx
<div className="flex bg-surface-mid rounded-lg p-0.5">
  <button onClick={() => setView("table")}
    className={`p-2 rounded-md transition-all ${view === "table" ? "bg-primary text-white shadow-sm" : "text-ink-secondary hover:text-ink"}`}>
    <List size={16} />
  </button>
  <button onClick={() => setView("grid")}
    className={`p-2 rounded-md transition-all ${view === "grid" ? "bg-primary text-white shadow-sm" : "text-ink-secondary hover:text-ink"}`}>
    <LayoutGrid size={16} />
  </button>
</div>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/app/operator/\(console\)/page.tsx
git commit -m "feat(operator): grid/table view toggle + warm palette restyle for clients list"
```

---

### Task 4: Client detail page — shell + mirrored sidebar with feature toggles

**Files:**
- Create: `frontend/app/operator/(console)/client/[id]/page.tsx` (rewrite from scratch)
- Create: `frontend/app/operator/(console)/client/[id]/sidebar.tsx`
- Create: `frontend/app/operator/(console)/client/[id]/components/stat-card.tsx`
- Create: `frontend/app/operator/(console)/client/[id]/components/skeleton.tsx`

**Interfaces:**
- Consumes: `GET /api/v1/operator/clients/{id}/overview` (existing), `PATCH /api/v1/operator/clients/{id}/features` (existing, updated in Task 1)
- Produces: Page shell with sidebar + content area that Task 5 & 6 views render into. Exports `SectionType` union type, `apiFetch` helper, and shared component types.

- [ ] **Step 1: Create the shared stat card component**

Create `frontend/app/operator/(console)/client/[id]/components/stat-card.tsx`:

```tsx
export function StatCard({ icon, label, value }: { icon: React.ReactNode; label: string; value: string | number }) {
  return (
    <div className="bg-white rounded-card border border-border p-5 shadow-sm">
      <div className="flex items-center gap-2 text-ink-muted mb-2">
        {icon}
        <span className="text-xs font-medium uppercase tracking-wider font-label">{label}</span>
      </div>
      <p className="text-2xl font-bold text-ink">{typeof value === "number" ? value.toLocaleString() : value}</p>
    </div>
  );
}
```

- [ ] **Step 2: Create the skeleton loading component**

Create `frontend/app/operator/(console)/client/[id]/components/skeleton.tsx`:

```tsx
export function SkeletonCard() {
  return (
    <div className="bg-white rounded-card border border-border p-5 shadow-sm animate-pulse">
      <div className="h-3 bg-surface-mid rounded w-24 mb-3" />
      <div className="h-7 bg-surface-mid rounded w-16" />
    </div>
  );
}

export function SkeletonTable({ rows = 5 }: { rows?: number }) {
  return (
    <div className="bg-white rounded-card border border-border overflow-hidden animate-pulse">
      <div className="px-5 py-3 border-b border-border-subtle">
        <div className="h-4 bg-surface-mid rounded w-32" />
      </div>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="px-5 py-3 border-b border-border-subtle last:border-0 flex gap-4">
          <div className="h-3 bg-surface-mid rounded w-28" />
          <div className="h-3 bg-surface-mid rounded w-20" />
          <div className="h-3 bg-surface-mid rounded w-16" />
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 3: Create the client detail sidebar**

Create `frontend/app/operator/(console)/client/[id]/sidebar.tsx`:

This sidebar mirrors the product sidebar. It has two sections:
1. **Product section** — items matching the product's sidebar (Overview, Inbox, Conversations, Segments, etc.) with toggle switches
2. **Operator section** — Configuration, Health, Management, Data Ops (no toggles)

```tsx
"use client";
import {
  LayoutDashboard, Inbox, MessageSquare, Users, RadioTower, Upload,
  FileCheck, Layers, BookOpen, BarChart2, Phone, Calendar, StickyNote,
  Wrench, Activity, Settings, Database, ChevronDown, ChevronRight,
} from "lucide-react";

export type SectionType =
  | "overview" | "inbox" | "conversations" | "segments"
  | "inbound" | "outbound" | "templates" | "numbers"
  | "knowledge" | "analytics" | "team"
  | "tc-upload" | "tc-dialer" | "tc-scheduled" | "tc-notes"
  | "config" | "health" | "management" | "data-ops";

type NavItem = {
  key: SectionType;
  icon: typeof LayoutDashboard;
  label: string;
  featureKey?: string;   // which feature controls this item
  alwaysOn?: boolean;    // no toggle — always available
};

const PRODUCT_NAV: NavItem[] = [
  { key: "overview", icon: LayoutDashboard, label: "Overview", alwaysOn: true },
  { key: "inbox", icon: Inbox, label: "Inbox", featureKey: "whatsapp" },
  { key: "conversations", icon: MessageSquare, label: "Conversations", alwaysOn: true },
  { key: "segments", icon: Users, label: "Segments", alwaysOn: true },
  { key: "inbound", icon: RadioTower, label: "Inbound Leads", featureKey: "whatsapp" },
  { key: "outbound", icon: Upload, label: "Outbound Leads", featureKey: "whatsapp" },
  { key: "templates", icon: FileCheck, label: "Templates", featureKey: "whatsapp" },
  { key: "numbers", icon: Layers, label: "Numbers Pool", featureKey: "whatsapp" },
  { key: "knowledge", icon: BookOpen, label: "Knowledge Base", alwaysOn: true },
  { key: "analytics", icon: BarChart2, label: "Analytics", alwaysOn: true },
  { key: "team", icon: Users, label: "Team", alwaysOn: true },
];

const TC_SUB_NAV: { key: SectionType; icon: typeof Phone; label: string; featureKey: string }[] = [
  { key: "tc-upload", icon: Upload, label: "Upload", featureKey: "telecalling.upload" },
  { key: "tc-dialer", icon: Phone, label: "Dialer", featureKey: "telecalling.dialer" },
  { key: "tc-scheduled", icon: Calendar, label: "Scheduled Calls", featureKey: "telecalling.scheduled" },
  { key: "tc-notes", icon: StickyNote, label: "Call Notes", featureKey: "telecalling.notes" },
];

const OPERATOR_NAV: NavItem[] = [
  { key: "config", icon: Wrench, label: "Configuration", alwaysOn: true },
  { key: "health", icon: Activity, label: "Health", alwaysOn: true },
  { key: "management", icon: Settings, label: "Management", alwaysOn: true },
  { key: "data-ops", icon: Database, label: "Data Ops", alwaysOn: true },
];

interface SidebarProps {
  activeSection: SectionType;
  onSectionChange: (s: SectionType) => void;
  enabledFeatures: string[];
  onToggleFeature: (feature: string) => void;
  featureUpdating: boolean;
}

export function ClientDetailSidebar({
  activeSection, onSectionChange, enabledFeatures, onToggleFeature, featureUpdating
}: SidebarProps) {
  const [tcExpanded, setTcExpanded] = useState(true);

  const isEnabled = (key: string) => enabledFeatures.includes(key);

  function FeatureToggle({ featureKey, disabled }: { featureKey: string; disabled?: boolean }) {
    const on = isEnabled(featureKey);
    return (
      <button
        disabled={featureUpdating || disabled}
        onClick={(e) => { e.stopPropagation(); onToggleFeature(featureKey); }}
        className={`relative w-9 h-5 rounded-full transition-all duration-200 flex-shrink-0 ${
          on ? "bg-primary" : "bg-ink-muted/30"
        } ${(featureUpdating || disabled) ? "opacity-40 cursor-not-allowed" : "cursor-pointer"}`}
      >
        <span className={`absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full transition-transform duration-200 shadow-sm ${on ? "translate-x-4" : ""}`} />
      </button>
    );
  }

  function NavItemRow({ item, indent }: { item: NavItem | typeof TC_SUB_NAV[0]; indent?: boolean }) {
    const active = activeSection === item.key;
    const featureKey = "featureKey" in item ? item.featureKey : undefined;
    const disabled = featureKey ? !isEnabled(featureKey) : false;
    const alwaysOn = "alwaysOn" in item && item.alwaysOn;

    return (
      <div
        onClick={() => onSectionChange(item.key)}
        className={`flex items-center justify-between px-3 py-2 rounded-xl cursor-pointer transition-all duration-200 group ${
          indent ? "ml-4" : ""
        } ${active ? "bg-primary-light text-primary" : disabled ? "opacity-40" : "text-ink-secondary hover:bg-surface-mid hover:text-ink"}`}
      >
        <div className="flex items-center gap-2.5 min-w-0">
          <item.icon size={16} className="flex-shrink-0" />
          <span className={`text-sm font-medium truncate ${disabled && !active ? "line-through" : ""}`}>{item.label}</span>
        </div>
        {featureKey && !alwaysOn && <FeatureToggle featureKey={featureKey} disabled={featureKey.startsWith("telecalling.") && !isEnabled("telecalling")} />}
      </div>
    );
  }

  return (
    <div className="w-[200px] flex-shrink-0 border-r border-border-subtle pr-2 space-y-1">
      {/* Product sections */}
      {PRODUCT_NAV.map(item => (
        <NavItemRow key={item.key} item={item} />
      ))}

      {/* Telecalling group */}
      <div>
        <div
          onClick={() => setTcExpanded(!tcExpanded)}
          className={`flex items-center justify-between px-3 py-2 rounded-xl cursor-pointer transition-all duration-200 ${
            ["tc-upload", "tc-dialer", "tc-scheduled", "tc-notes"].includes(activeSection)
              ? "bg-primary-light text-primary" : isEnabled("telecalling") ? "text-ink-secondary hover:bg-surface-mid hover:text-ink" : "text-ink-secondary opacity-40"
          }`}
        >
          <div className="flex items-center gap-2.5">
            <Phone size={16} />
            <span className="text-sm font-medium">Telecalling</span>
          </div>
          <div className="flex items-center gap-2">
            <FeatureToggle featureKey="telecalling" />
            {tcExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </div>
        </div>
        {tcExpanded && isEnabled("telecalling") && (
          <div className="mt-1 space-y-0.5">
            {TC_SUB_NAV.map(item => (
              <NavItemRow key={item.key} item={item} indent />
            ))}
          </div>
        )}
      </div>

      {/* Divider + Operator sections */}
      <div className="pt-3 mt-3 border-t border-border-subtle">
        <p className="px-3 py-1 text-[10px] font-semibold text-ink-muted uppercase tracking-widest">Operator</p>
        {OPERATOR_NAV.map(item => (
          <NavItemRow key={item.key} item={item} />
        ))}
      </div>
    </div>
  );
}
```

Note: add `import { useState } from "react";` at the top.

- [ ] **Step 4: Create the main client detail page**

Create `frontend/app/operator/(console)/client/[id]/page.tsx`:

This is the shell that holds the header, sidebar, and content area. It:
- Fetches overview data on mount (for header info)
- Manages `activeSection` state
- Passes feature toggle callbacks to sidebar
- Lazily renders the selected section's view component
- Initially just renders Overview; other views are added in Tasks 5-6

```tsx
"use client";
import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { API_URL, getAuthHeaders } from "@/lib/api";
import { ClientDetailSidebar, type SectionType } from "./sidebar";

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const auth = await getAuthHeaders();
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...auth, ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail || "Request failed");
  }
  return res.json() as Promise<T>;
}

interface OverviewData {
  tenant: { id: string; name: string; status: string; enabled_features: string[]; created_at: string };
  owner: { user_id: string | null; email: string | null };
  stats: { total_leads: number; active_leads: number; messages_sent_30d: number; messages_received_30d: number; team_members: number; last_activity: string | null };
}

export { apiFetch };
export type { OverviewData };

export default function ClientDetailPage() {
  const { id: tenantId } = useParams<{ id: string }>();
  const router = useRouter();
  const [section, setSection] = useState<SectionType>("overview");
  const [overview, setOverview] = useState<OverviewData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [featureUpdating, setFeatureUpdating] = useState(false);

  const loadOverview = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiFetch<OverviewData>(`/api/v1/operator/clients/${tenantId}/overview`);
      setOverview(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, [tenantId]);

  useEffect(() => { loadOverview(); }, [loadOverview]);

  async function handleToggleFeature(feature: string) {
    if (!overview) return;
    setFeatureUpdating(true);
    const current = overview.tenant.enabled_features;
    let updated: string[];

    if (feature === "telecalling") {
      const tcSubs = ["telecalling.dialer", "telecalling.upload", "telecalling.scheduled", "telecalling.notes"];
      if (current.includes("telecalling")) {
        updated = current.filter(f => f !== "telecalling" && !tcSubs.includes(f));
      } else {
        updated = [...current, "telecalling", ...tcSubs];
      }
    } else {
      updated = current.includes(feature)
        ? current.filter(f => f !== feature)
        : [...current, feature];
    }

    try {
      await apiFetch(`/api/v1/operator/clients/${tenantId}/features`, {
        method: "PATCH",
        body: JSON.stringify({ features: updated }),
      });
      setOverview({ ...overview, tenant: { ...overview.tenant, enabled_features: updated } });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update features");
    } finally {
      setFeatureUpdating(false);
    }
  }

  if (loading && !overview) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-pulse text-ink-muted text-sm">Loading…</div>
      </div>
    );
  }

  const tenant = overview?.tenant;

  return (
    <div>
      {/* Back */}
      <button onClick={() => router.push("/operator")} className="flex items-center gap-1.5 text-sm text-ink-secondary hover:text-ink transition-colors mb-4">
        <ArrowLeft size={14} /> Back to Clients
      </button>

      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-danger/20 rounded-xl text-sm text-danger flex items-center justify-between">
          {error}
          <button onClick={() => setError(null)} className="text-xs underline ml-2">dismiss</button>
        </div>
      )}

      {/* Header Card */}
      {tenant && (
        <div className="bg-white rounded-card border border-border p-6 mb-6 shadow-sm">
          <div className="flex items-start justify-between">
            <div>
              <h1 className="text-2xl font-bold text-ink font-display">{tenant.name}</h1>
              <p className="text-xs text-ink-muted font-mono mt-1">
                {tenant.id}
                <button onClick={() => navigator.clipboard.writeText(tenant.id)} className="ml-2 text-ink-muted hover:text-ink transition-colors" title="Copy ID">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>
                </button>
              </p>
              {overview?.owner?.email && <p className="text-sm text-ink-secondary mt-2">Owner: {overview.owner.email}</p>}
              <p className="text-xs text-ink-muted mt-1">Created {new Date(tenant.created_at).toLocaleDateString("en-IN")}</p>
            </div>
            <div className="flex items-center gap-2 flex-wrap justify-end">
              <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium ${
                tenant.status === "active" ? "bg-green-50 text-success" : "bg-red-50 text-danger"
              }`}>
                <span className={`w-1.5 h-1.5 rounded-full ${tenant.status === "active" ? "bg-success" : "bg-danger"}`} />
                {tenant.status}
              </span>
              {tenant.enabled_features.filter(f => !f.includes(".")).map(f => (
                <span key={f} className="px-2 py-0.5 rounded-full text-xs font-medium bg-primary-muted text-primary">
                  {{"whatsapp":"WhatsApp","telecalling":"Telecalling","instagram":"Instagram","facebook":"Facebook","telegram":"Telegram"}[f] || f}
                </span>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Sidebar + Content */}
      <div className="flex gap-6">
        <ClientDetailSidebar
          activeSection={section}
          onSectionChange={setSection}
          enabledFeatures={tenant?.enabled_features || []}
          onToggleFeature={handleToggleFeature}
          featureUpdating={featureUpdating}
        />
        <div className="flex-1 min-w-0">
          {/* Section views rendered here — placeholder for now, implemented in Tasks 5-6 */}
          <SectionContent section={section} tenantId={tenantId} overview={overview} onReload={loadOverview} setError={setError} />
        </div>
      </div>
    </div>
  );
}

// Placeholder — Tasks 5 & 6 will build out each section
function SectionContent({ section, tenantId, overview, onReload, setError }: {
  section: SectionType; tenantId: string; overview: OverviewData | null;
  onReload: () => void; setError: (e: string | null) => void;
}) {
  // Overview section is built inline as the default view
  if (section === "overview" && overview) {
    const { OverviewView } = require("./views/overview");
    return <OverviewView stats={overview.stats} />;
  }
  return (
    <div className="flex items-center justify-center h-48 text-ink-muted text-sm">
      Loading {section}…
    </div>
  );
}
```

- [ ] **Step 5: Create the overview view**

Create `frontend/app/operator/(console)/client/[id]/views/overview.tsx`:

```tsx
"use client";
import { Users, Activity, MessageSquare, Clock } from "lucide-react";
import { StatCard } from "../components/stat-card";

function relTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const s = Math.abs(diff) / 1000;
  if (s < 60) return `${Math.round(s)}s ago`;
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
}

interface Stats {
  total_leads: number; active_leads: number;
  messages_sent_30d: number; messages_received_30d: number;
  team_members: number; last_activity: string | null;
}

export function OverviewView({ stats }: { stats: Stats }) {
  return (
    <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
      <StatCard icon={<Users size={18} />} label="Total Leads" value={stats.total_leads} />
      <StatCard icon={<Activity size={18} />} label="Active Leads (A+B)" value={stats.active_leads} />
      <StatCard icon={<MessageSquare size={18} />} label="Msgs Sent (30d)" value={stats.messages_sent_30d} />
      <StatCard icon={<MessageSquare size={18} />} label="Msgs Received (30d)" value={stats.messages_received_30d} />
      <StatCard icon={<Users size={18} />} label="Team Members" value={stats.team_members} />
      <StatCard icon={<Clock size={18} />} label="Last Activity" value={stats.last_activity ? relTime(stats.last_activity) : "—"} />
    </div>
  );
}
```

- [ ] **Step 6: Commit**

```bash
git add frontend/app/operator/\(console\)/client/\[id\]/
git commit -m "feat(operator): client detail page shell with mirrored sidebar + feature toggles"
```

---

### Task 5: Client detail page — all read-only dashboard views

**Files:**
- Create: `frontend/app/operator/(console)/client/[id]/views/inbox.tsx`
- Create: `frontend/app/operator/(console)/client/[id]/views/leads.tsx`
- Create: `frontend/app/operator/(console)/client/[id]/views/content.tsx` (Templates + Numbers + Knowledge)
- Create: `frontend/app/operator/(console)/client/[id]/views/analytics.tsx`
- Create: `frontend/app/operator/(console)/client/[id]/views/team.tsx`
- Create: `frontend/app/operator/(console)/client/[id]/views/telecalling.tsx`
- Modify: `frontend/app/operator/(console)/client/[id]/page.tsx` — wire up all views in `SectionContent`

**Interfaces:**
- Consumes: All dashboard endpoints from Task 1, team endpoint (existing), `apiFetch` from Task 4
- Produces: Complete set of read-only section views

Each view follows the same pattern:
1. Accept `tenantId` as prop
2. Fetch data on mount with `apiFetch`
3. Show skeleton while loading
4. Render data with warm-palette styled cards and tables

- [ ] **Step 1: Create inbox view**

`views/inbox.tsx` — Shows handover count stat + recent conversations table.

Key elements:
- Stat card with `Inbox` icon showing `handover_count`
- Table: Lead Name, Last Message (truncated), Channel badge, Time ago
- Empty state: "No conversations yet" centered with Inbox icon
- Uses `SkeletonTable` while loading

- [ ] **Step 2: Create leads view**

`views/leads.tsx` — Accepts a `subSection` prop: `"segments"` (default), `"inbound"`, `"outbound"`.

Key elements:
- Segments: 4 stat cards (A/Hot green, B/Warm amber, C/Cold blue, D/Disqualified gray) + total
- Recent leads table: Name, Phone, Segment badge (color-coded), Score, Source, Date
- Inbound/Outbound: pass `?direction=inbound` or `?direction=outbound` query param
- All use warm palette tokens

- [ ] **Step 3: Create content view**

`views/content.tsx` — Accepts `subSection` prop: `"templates"`, `"numbers"`, `"knowledge"`.

Templates:
- Stats: total, approved (green), pending (amber)
- Table: Name, Status badge (APPROVED green / PENDING amber / REJECTED red), Category, Language, Last Synced

Numbers:
- Stats: total, active
- Table: Number, Display Name, Quality badge (GREEN/YELLOW/RED), Status, Messaging Limit

Knowledge:
- Stats: total docs, total chunks
- Table: Title, Chunks, File Type, Created Date

- [ ] **Step 4: Create analytics view**

`views/analytics.tsx` — Key metrics in stat cards.

Cards: Messages 30d, Delivery Rate %, Avg Score. If telecalling enabled: Total Calls, Connect Rate %.

- [ ] **Step 5: Create team view**

`views/team.tsx` — Owner info + callers table. Port existing management tab's team section with warm palette.

- [ ] **Step 6: Create telecalling view**

`views/telecalling.tsx` — Accepts `subSection` prop: `"upload"`, `"dialer"`, `"scheduled"`, `"notes"`.

Each sub-section: stat card(s) + data table. Maps `tc-upload` → `?section=upload`, etc.

Upload: batches table (filename, lead count, date, status)
Dialer: calls today stat + recent calls table (lead, caller, duration, disposition badge, date)
Scheduled: pending count + upcoming table (lead, caller, scheduled time)
Notes: total notes + recent table (lead, caller, note preview, date)

- [ ] **Step 7: Wire up all views in page.tsx**

Update the `SectionContent` component in `page.tsx` to dynamically import and render each view based on the active section. Use lazy state management — each view fetches its own data on mount:

```tsx
function SectionContent({ section, tenantId, overview, onReload, setError }: Props) {
  switch (section) {
    case "overview": return overview ? <OverviewView stats={overview.stats} /> : null;
    case "inbox": case "conversations": return <InboxView tenantId={tenantId} />;
    case "segments": return <LeadsView tenantId={tenantId} subSection="segments" />;
    case "inbound": return <LeadsView tenantId={tenantId} subSection="inbound" />;
    case "outbound": return <LeadsView tenantId={tenantId} subSection="outbound" />;
    case "templates": return <ContentView tenantId={tenantId} subSection="templates" />;
    case "numbers": return <ContentView tenantId={tenantId} subSection="numbers" />;
    case "knowledge": return <ContentView tenantId={tenantId} subSection="knowledge" />;
    case "analytics": return <AnalyticsView tenantId={tenantId} />;
    case "team": return <TeamView tenantId={tenantId} />;
    case "tc-upload": return <TelecallingView tenantId={tenantId} subSection="upload" />;
    case "tc-dialer": return <TelecallingView tenantId={tenantId} subSection="dialer" />;
    case "tc-scheduled": return <TelecallingView tenantId={tenantId} subSection="scheduled" />;
    case "tc-notes": return <TelecallingView tenantId={tenantId} subSection="notes" />;
    case "config": return <ConfigView tenantId={tenantId} />;
    case "health": return <HealthView tenantId={tenantId} />;
    case "management": return <ManagementView tenantId={tenantId} overview={overview} onReload={onReload} setError={setError} />;
    case "data-ops": return <DataOpsView tenantId={tenantId} clientName={overview?.tenant.name || ""} />;
    default: return null;
  }
}
```

- [ ] **Step 8: Commit**

```bash
git add frontend/app/operator/\(console\)/client/\[id\]/
git commit -m "feat(operator): all read-only dashboard views (inbox, leads, content, analytics, team, telecalling)"
```

---

### Task 6: Client detail page — operator sections (config, health, management, data ops)

**Files:**
- Create: `frontend/app/operator/(console)/client/[id]/views/config.tsx`
- Create: `frontend/app/operator/(console)/client/[id]/views/health.tsx`
- Create: `frontend/app/operator/(console)/client/[id]/views/management.tsx`
- Create: `frontend/app/operator/(console)/client/[id]/views/data-ops.tsx`
- Create: `frontend/app/operator/(console)/client/[id]/components/confirm-dialog.tsx`

**Interfaces:**
- Consumes: Config, health (fixed in Task 1), team endpoints, data clear endpoints from Task 1
- Produces: All operator-only views

- [ ] **Step 1: Create the type-to-confirm dialog**

`components/confirm-dialog.tsx`:

```tsx
"use client";
import { useState } from "react";
import { AlertTriangle, X } from "lucide-react";

interface ConfirmDialogProps {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  description: string;
  details: { label: string; count: number }[];
  confirmText: string;
  loading?: boolean;
}

export function ConfirmDialog({ open, onClose, onConfirm, title, description, details, confirmText, loading }: ConfirmDialogProps) {
  const [typed, setTyped] = useState("");
  if (!open) return null;

  return (
    <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-card shadow-xl w-full max-w-md p-6">
        <div className="flex items-start justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-warning/10 flex items-center justify-center">
              <AlertTriangle size={20} className="text-warning" />
            </div>
            <h3 className="text-lg font-bold text-ink">{title}</h3>
          </div>
          <button onClick={onClose} className="text-ink-muted hover:text-ink"><X size={18} /></button>
        </div>

        <p className="text-sm text-ink-secondary mb-3">{description}</p>

        {details.length > 0 && (
          <ul className="text-sm text-ink mb-4 space-y-1">
            {details.map(d => (
              <li key={d.label} className="flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-danger" />
                <span className="font-medium">{d.count.toLocaleString()}</span> {d.label}
              </li>
            ))}
          </ul>
        )}

        <p className="text-sm text-ink-secondary mb-2">
          Type <span className="font-mono font-bold text-ink">{confirmText}</span> to confirm:
        </p>
        <input
          value={typed}
          onChange={e => setTyped(e.target.value)}
          className="w-full border border-border rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-danger/20 focus:border-danger mb-4 font-mono"
          placeholder={confirmText}
        />

        <div className="flex gap-3">
          <button onClick={onClose} className="flex-1 px-4 py-2.5 border border-border text-sm text-ink-secondary rounded-xl hover:bg-surface-mid transition-colors">
            Cancel
          </button>
          <button
            onClick={() => { onConfirm(); setTyped(""); }}
            disabled={typed !== confirmText || loading}
            className="flex-1 px-4 py-2.5 bg-danger text-white text-sm font-medium rounded-xl hover:bg-danger/90 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {loading ? "Deleting…" : "Delete Forever"}
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create config view**

`views/config.tsx` — Port existing config tab with warm palette. Feature toggles are now in the sidebar (remove from here). Keep:
- Credential status cards (WhatsApp, TeleCMI, Groq, Razorpay)
- Key settings summary (AI auto-reply, re-engagement, booking)
- All styled with warm tokens

- [ ] **Step 3: Create health view**

`views/health.tsx` — Port existing health tab with warm palette. Fix the rendering to handle the updated response (uses `delivery_error_title` from the fixed endpoint).

Key elements:
- Channel health cards with animated green dot for healthy (`animate-pulse`)
- Token status
- Delivery stats with visual bar for success rate
- Recent errors table
- Open incidents table

- [ ] **Step 4: Create management view**

`views/management.tsx` — Port existing management tab. Actions, owner info, team table. All warm palette.

Action cards styled as individual cards:
```tsx
<div className="bg-white rounded-card border border-border p-4 hover:shadow-card transition-all">
  <button onClick={...} className="flex items-center gap-3">
    <div className="w-10 h-10 rounded-xl bg-primary-light flex items-center justify-center">
      <Key size={18} className="text-primary" />
    </div>
    <div className="text-left">
      <p className="text-sm font-medium text-ink">Reset Owner Password</p>
      <p className="text-xs text-ink-muted">Generate a temporary password</p>
    </div>
  </button>
</div>
```

- [ ] **Step 5: Create data ops view**

`views/data-ops.tsx` — Grid of data type cards, each with:
- Icon + name + record count (fetched from `/clear/{type}/count`)
- "Clear" button that opens ConfirmDialog

Data types: broadcasts, messages, call_logs, leads, knowledge, templates, analytics.

Each card:
```tsx
<div className="bg-white rounded-card border border-border p-5 shadow-sm">
  <div className="flex items-center gap-3 mb-3">
    <div className="w-10 h-10 rounded-xl bg-danger/5 flex items-center justify-center">
      <Radio size={18} className="text-danger" />
    </div>
    <div>
      <p className="text-sm font-medium text-ink">Broadcast History</p>
      <p className="text-xs text-ink-muted">{count} records</p>
    </div>
  </div>
  <button onClick={() => openConfirm("broadcasts")}
    className="w-full px-3 py-2 border border-danger/20 text-danger text-sm rounded-xl hover:bg-red-50 transition-colors">
    Clear Data
  </button>
</div>
```

- [ ] **Step 6: Commit**

```bash
git add frontend/app/operator/\(console\)/client/\[id\]/
git commit -m "feat(operator): operator sections — config, health (fixed), management, data ops with confirm dialog"
```

---

### Task 7: Product sidebar — sub-feature gating for telecalling

**Files:**
- Modify: `frontend/components/sidebar.tsx`

**Interfaces:**
- Consumes: `enabledFeatures` from `useAuthRole()` (includes dot-notation sub-features after Task 1 backend changes)
- Produces: Sidebar respects `telecalling.dialer`, `telecalling.upload`, etc.

- [ ] **Step 1: Update telecalling sub-item visibility**

In `frontend/components/sidebar.tsx`, the `TELECALLING_ITEMS` array currently shows all 4 items when `telecalling` is in `enabledFeatures`. Update to check for sub-features:

Before the `TELECALLING_ITEMS` constant, add a feature key mapping:

```tsx
const TC_FEATURE_MAP: Record<string, string> = {
  "/dashboard/telecalling/upload": "telecalling.upload",
  "/dashboard/telecalling": "telecalling.dialer",
  "/dashboard/telecalling/scheduled": "telecalling.scheduled",
  "/dashboard/notes": "telecalling.notes",
};
```

In the telecalling group rendering section, filter items:

```tsx
const visibleTcItems = TELECALLING_ITEMS.filter(item => {
  const featureKey = TC_FEATURE_MAP[item.href];
  return !featureKey || enabledFeatures.includes(featureKey);
});
```

Then render `visibleTcItems` instead of `TELECALLING_ITEMS`.

Also: if the parent `telecalling` is enabled but no sub-features exist in `enabledFeatures` (backwards compatibility for tenants not yet migrated), show all items (the old behavior).

```tsx
const hasTcSubFeatures = enabledFeatures.some(f => f.startsWith("telecalling."));
const visibleTcItems = hasTcSubFeatures
  ? TELECALLING_ITEMS.filter(item => {
      const featureKey = TC_FEATURE_MAP[item.href];
      return !featureKey || enabledFeatures.includes(featureKey);
    })
  : TELECALLING_ITEMS;
```

- [ ] **Step 2: Commit**

```bash
git add frontend/components/sidebar.tsx
git commit -m "feat(sidebar): gate telecalling sub-items by sub-feature flags"
```

---

### Task 8: Operator login page warm restyle + migration for sub-feature backfill

**Files:**
- Modify: `frontend/app/operator/login/page.tsx`
- Create: `backend/supabase/migrations/115_telecalling_subfeatures_backfill.sql`

**Interfaces:**
- Consumes: None
- Produces: Warm-styled login page, existing telecalling tenants get sub-features backfilled

- [ ] **Step 1: Restyle the operator login page**

Update `frontend/app/operator/login/page.tsx` to use warm palette tokens:
- Page background: `bg-background`
- Card: `bg-white rounded-card shadow-card border border-border`
- Input: `border-border rounded-xl focus:ring-primary/20 focus:border-primary`
- Button: `bg-primary hover:bg-primary-dark text-white rounded-xl`
- "Aira AI" branding with primary purple

- [ ] **Step 2: Create the sub-feature backfill migration**

Create `backend/supabase/migrations/115_telecalling_subfeatures_backfill.sql`:

```sql
-- Migration 115: Backfill telecalling sub-features for existing tenants
-- Tenants with 'telecalling' in enabled_features get all 4 sub-features added

UPDATE tenants
SET enabled_features = enabled_features || ARRAY['telecalling.dialer', 'telecalling.upload', 'telecalling.scheduled', 'telecalling.notes']
WHERE 'telecalling' = ANY(enabled_features)
  AND NOT 'telecalling.dialer' = ANY(enabled_features);
```

- [ ] **Step 3: Commit**

```bash
git add frontend/app/operator/login/page.tsx backend/supabase/migrations/115_telecalling_subfeatures_backfill.sql
git commit -m "feat(operator): warm palette login page + telecalling sub-feature backfill migration"
```
