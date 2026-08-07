# Consultations Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give staff a dedicated dashboard page listing every Paid Expert Handoff lead — split into "gave details, awaiting payment" and "paid" — with in-place WhatsApp reply.

**Architecture:** One new authenticated backend endpoint reads the existing `expert_handoff_sessions` table (no new tables). One new frontend page renders a two-pane list+detail layout, reusing the existing `ChatThread` component for messaging rather than building new reply logic. Payment confirmation gets one new side effect: a `notify_pool` ping to staff.

**Tech Stack:** FastAPI (backend/app), Next.js 14 (frontend/app/dashboard), existing `ChatThread`/`sidebar.tsx` components.

## Global Constraints

- No `chat_handovers` row, no WhatsApp staff alert for this feature — `notify_pool` only (spec D6). This supersedes an earlier interrupted attempt that used `chat_handovers`; that dead code must be removed, not left alongside the new approach.
- Unpaid bucket = `status = 'awaiting_payment'` only, not partial/mid-collection sessions (spec D2).
- Reuse `conversations.view`/`conversations.reply` permissions — no new RBAC entries (spec D4).
- Reuse `ChatThread` for messaging — no new send-message code (spec D3).

---

## File Structure

| File | Responsibility |
|---|---|
| `backend/tests/test_expert_handoff.py` | **Modify** — remove the interrupted `chat_handovers` test, add a `notify_pool` test |
| `backend/app/services/expert_handoff.py` | **Modify** — `confirm_expert_handoff_payment` calls `notify_pool` on payment |
| `backend/app/routes/expert_handoff.py` | **Modify** — add authenticated `router` with `GET /sessions` |
| `backend/app/main.py` | **Modify** — register the new authenticated router |
| `backend/tests/test_expert_handoff_sessions_route.py` | **Create** — tests for the new list endpoint |
| `frontend/lib/api.ts` | **Modify** — add `api.expertHandoff.listSessions` |
| `frontend/app/dashboard/consultations/ConsultationDetails.tsx` | **Create** — collected-fields summary card |
| `frontend/app/dashboard/consultations/page.tsx` | **Create** — the two-pane list+detail page |
| `frontend/components/sidebar.tsx` | **Modify** — add the "Consultations" nav entry |

---

## Task 1: Replace the interrupted chat_handovers wiring with notify_pool

**Files:**
- Modify: `backend/tests/test_expert_handoff.py` (remove one test, add one test)
- Modify: `backend/app/services/expert_handoff.py`

**Interfaces:**
- Consumes: `app.services.notify.notify_pool(tenant_id: str, type: str, title: str, message: str, *, db=None) -> None`
- Modifies: `confirm_expert_handoff_payment` (unchanged signature, new side effect)

- [ ] **Step 1: Remove the interrupted test**

In `backend/tests/test_expert_handoff.py`, delete this entire function (it's the last thing in the file, from an earlier attempt that used `chat_handovers` — superseded by this plan's D6):

```python
def test_confirm_expert_handoff_payment_creates_chat_handover_for_staff_visibility():
    ...
```

Delete everything from that `def` line to the end of the file.

- [ ] **Step 2: Write the failing test**

Append to `backend/tests/test_expert_handoff.py`:

```python
def test_confirm_expert_handoff_payment_notifies_staff_pool():
    session_row = {"id": "sess-1", "status": "awaiting_payment", "lead_id": "lead-1", "tenant_id": "t-1", "collected_data": {"name": "Priya"}}
    lead_row = {"id": "lead-1", "phone": "+919876543210", "name": "Priya"}
    db = MagicMock()

    def make_table(name):
        t = MagicMock()
        if name == "expert_handoff_sessions":
            fetch = MagicMock()
            fetch.data = session_row
            t.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = fetch
            t.update.return_value.eq.return_value.execute.return_value = MagicMock()
        elif name == "leads":
            fetch = MagicMock()
            fetch.data = lead_row
            t.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = fetch
            t.update.return_value.eq.return_value.execute.return_value = MagicMock()
        return t

    cache = {}
    def selector(name):
        if name not in cache:
            cache[name] = make_table(name)
        return cache[name]
    db.table.side_effect = selector

    with patch.object(eh, "notify_pool") as notify:
        eh.confirm_expert_handoff_payment("sess-1", "pay_abc123", db=db)

    notify.assert_called_once()
    args = notify.call_args[0]
    assert args[0] == "t-1"
    assert args[1] == "expert_handoff_paid"
    assert "Priya" in args[3]


def test_confirm_expert_handoff_payment_notify_failure_does_not_break_confirmation():
    session_row = {"id": "sess-1", "status": "awaiting_payment", "lead_id": "lead-1", "tenant_id": "t-1", "collected_data": {"name": "Priya"}}
    lead_row = {"id": "lead-1", "phone": "+919876543210", "name": "Priya"}
    db = MagicMock()

    def make_table(name):
        t = MagicMock()
        if name == "expert_handoff_sessions":
            fetch = MagicMock()
            fetch.data = session_row
            t.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = fetch
            t.update.return_value.eq.return_value.execute.return_value = MagicMock()
        elif name == "leads":
            fetch = MagicMock()
            fetch.data = lead_row
            t.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = fetch
            t.update.return_value.eq.return_value.execute.return_value = MagicMock()
        return t

    cache = {}
    def selector(name):
        if name not in cache:
            cache[name] = make_table(name)
        return cache[name]
    db.table.side_effect = selector

    with patch.object(eh, "notify_pool", side_effect=RuntimeError("push service down")):
        result = eh.confirm_expert_handoff_payment("sess-1", "pay_abc123", db=db)

    assert result == ("+919876543210", "t-1", "lead-1", "Priya")
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && venv/bin/python -m pytest tests/test_expert_handoff.py -k notify_staff_pool -v`
Expected: FAIL with `AttributeError: <module 'app.services.expert_handoff' ...> does not have the attribute 'notify_pool'`

- [ ] **Step 4: Write minimal implementation**

Add the import at the top of `backend/app/services/expert_handoff.py`, alongside the other module-level service imports:

```python
from app.services.notify import notify_pool
```

Modify `confirm_expert_handoff_payment` — find this block near the end of the function:

```python
    lead_row = (
        db.table("leads")
        .select("phone,name")
        .eq("id", lead_id)
        .maybe_single()
        .execute()
    )
    lead = (lead_row.data if lead_row else None) or {}
    phone = lead.get("phone", "")
    customer_name = (session.get("collected_data") or {}).get("name") or lead.get("name") or "Customer"
    return (phone, tenant_id, lead_id, customer_name)
```

Replace it with:

```python
    lead_row = (
        db.table("leads")
        .select("phone,name")
        .eq("id", lead_id)
        .maybe_single()
        .execute()
    )
    lead = (lead_row.data if lead_row else None) or {}
    phone = lead.get("phone", "")
    customer_name = (session.get("collected_data") or {}).get("name") or lead.get("name") or "Customer"

    try:
        notify_pool(
            tenant_id,
            "expert_handoff_paid",
            "New paid consultation",
            f"Lead '{customer_name}' paid for a consultation — check Consultations.",
            db=db,
        )
    except Exception as e:
        logger.warning(f"expert_handoff_paid notify_pool failed for session {session_id}: {e}")

    return (phone, tenant_id, lead_id, customer_name)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && venv/bin/python -m pytest tests/test_expert_handoff.py -v`
Expected: PASS (all tests in the file, including the two new ones — should be 23 total: 21 pre-existing minus the 1 removed plus 2 new)

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_expert_handoff.py backend/app/services/expert_handoff.py
git commit -m "feat: notify staff pool on expert handoff payment, drop chat_handovers approach"
```

---

## Task 2: Backend — authenticated sessions list endpoint

**Files:**
- Modify: `backend/app/routes/expert_handoff.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_expert_handoff_sessions_route.py`

**Interfaces:**
- Produces: `router: APIRouter` (new, alongside the existing `public_router`) with `GET /sessions?bucket=awaiting_payment|paid` returning `{"data": [...]}`, each row: `{id, lead_id, status, collected_data, amount_paise, payment_link, paid_at, created_at, leads: {name, phone}}`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_expert_handoff_sessions_route.py
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_and_role


class ExpertHandoffSessionsListTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-1"}
        app.dependency_overrides[get_tenant_and_role] = lambda: {
            "tenant_id": "t-1", "role": "owner", "permissions": [],
        }

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("app.routes.expert_handoff.get_supabase")
    def test_lists_sessions_for_the_requested_bucket(self, mock_get_db):
        db = MagicMock()
        rows = MagicMock()
        rows.data = [
            {"id": "sess-1", "lead_id": "lead-1", "status": "awaiting_payment",
             "collected_data": {"name": "Priya"}, "amount_paise": 2900,
             "payment_link": "https://rzp.io/x", "paid_at": None,
             "created_at": "2026-08-07T00:00:00Z", "leads": {"name": "Priya", "phone": "+919876543210"}},
        ]
        chain = db.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value
        chain.execute.return_value = rows
        mock_get_db.return_value = db

        res = self.client.get("/api/v1/expert-handoff/sessions?bucket=awaiting_payment")

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(len(body["data"]), 1)
        self.assertEqual(body["data"][0]["leads"]["name"], "Priya")
        db.table.return_value.select.return_value.eq.assert_any_call("tenant_id", "t-1")

    @patch("app.routes.expert_handoff.get_supabase")
    def test_rejects_invalid_bucket(self, mock_get_db):
        res = self.client.get("/api/v1/expert-handoff/sessions?bucket=collecting")
        self.assertEqual(res.status_code, 400)

    @patch("app.routes.expert_handoff.get_supabase")
    def test_empty_bucket_returns_empty_list_not_error(self, mock_get_db):
        db = MagicMock()
        rows = MagicMock()
        rows.data = []
        chain = db.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value
        chain.execute.return_value = rows
        mock_get_db.return_value = db

        res = self.client.get("/api/v1/expert-handoff/sessions?bucket=paid")

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"data": []})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && venv/bin/python -m pytest tests/test_expert_handoff_sessions_route.py -v`
Expected: FAIL — `404` (no `/sessions` route registered yet) on the first two tests

- [ ] **Step 3: Write minimal implementation**

In `backend/app/routes/expert_handoff.py`, add these imports at the top (alongside the existing ones) and a new `router`:

```python
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.db.supabase import get_supabase
from app.dependencies.tenant import require_permission
```

(Merge with the existing `from fastapi import APIRouter, HTTPException, Request` line — replace it with the combined import above, adding `Depends` and `Query`.)

Add below the existing `public_router = APIRouter()` line:

```python
router = APIRouter()
require_conversations_view = require_permission("conversations.view")


@router.get("/sessions")
def list_expert_handoff_sessions(
    bucket: str = Query(...),
    ctx: dict = Depends(require_conversations_view),
):
    if bucket not in ("awaiting_payment", "paid"):
        raise HTTPException(status_code=400, detail="bucket must be 'awaiting_payment' or 'paid'")

    db = get_supabase()
    result = (
        db.table("expert_handoff_sessions")
        .select("id, lead_id, status, collected_data, amount_paise, payment_link, paid_at, created_at, leads(name, phone)")
        .eq("tenant_id", ctx["tenant_id"])
        .eq("status", bucket)
        .order("created_at", desc=True)
        .limit(50)
        .execute()
    )
    return {"data": result.data or []}
```

In `backend/app/main.py`, add the authenticated router registration right after the existing public one:

```python
app.include_router(expert_handoff_public_router, prefix="/api/v1/expert-handoff", tags=["expert-handoff-webhook"])
```

becomes:

```python
app.include_router(expert_handoff_public_router, prefix="/api/v1/expert-handoff", tags=["expert-handoff-webhook"])
app.include_router(expert_handoff.router, prefix="/api/v1/expert-handoff", tags=["expert-handoff"], dependencies=_auth)
```

This requires importing the module (not just the symbol) — add near the top-level route imports:

```python
from app.routes import expert_handoff
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && venv/bin/python -m pytest tests/test_expert_handoff_sessions_route.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Sanity-check main.py still boots**

Run: `cd backend && venv/bin/python -c "from app.main import app"`
Expected: no import errors

- [ ] **Step 6: Run the full backend test suite for regressions**

Run: `cd backend && venv/bin/python -m pytest -q`
Expected: same pass count as before this task plus the new tests; only the 2 pre-existing unrelated date-boundary failures remain (see `.agents/decisions/log.md` 2026-08-07 for confirmation these predate this work)

- [ ] **Step 7: Commit**

```bash
git add backend/app/routes/expert_handoff.py backend/app/main.py backend/tests/test_expert_handoff_sessions_route.py
git commit -m "feat: authenticated endpoint to list expert handoff sessions by bucket"
```

---

## Task 3: Frontend API helper

**Files:**
- Modify: `frontend/lib/api.ts`

**Interfaces:**
- Produces: `ExpertHandoffSession` type; `api.expertHandoff.listSessions(bucket: "awaiting_payment" | "paid"): Promise<ExpertHandoffSession[]>`

- [ ] **Step 1: Add the type and API method**

In `frontend/lib/api.ts`, add this interface near the other feature-specific interfaces (e.g. right before `export const api = {`):

```typescript
export interface ExpertHandoffSession {
  id: string;
  lead_id: string;
  status: "awaiting_payment" | "paid";
  collected_data: Record<string, string>;
  amount_paise: number | null;
  payment_link: string | null;
  paid_at: string | null;
  created_at: string;
  leads: { name: string | null; phone: string | null } | null;
}
```

Add a new top-level key to the `api` object, right before its closing `};` (after the existing `chatHandovers: { ... },` block):

```typescript
  expertHandoff: {
    listSessions: async (bucket: "awaiting_payment" | "paid") => {
      const res = await apiFetch<{ data: ExpertHandoffSession[] }>(
        `/api/v1/expert-handoff/sessions?bucket=${bucket}`
      );
      return res.data || [];
    },
  },
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npm run typecheck`
Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "feat: frontend API helper for listing expert handoff sessions"
```

---

## Task 4: Consultation details card

**Files:**
- Create: `frontend/app/dashboard/consultations/ConsultationDetails.tsx`

**Interfaces:**
- Consumes: `ExpertHandoffSession` (Task 3)
- Produces: `export function ConsultationDetails({ session }: { session: ExpertHandoffSession }): JSX.Element`

- [ ] **Step 1: Write the component**

```tsx
// frontend/app/dashboard/consultations/ConsultationDetails.tsx
"use client";
import { CheckCircle2, Clock } from "lucide-react";
import { ExpertHandoffSession } from "@/lib/api";

function formatFieldKey(key: string): string {
  return key
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

export function ConsultationDetails({ session }: { session: ExpertHandoffSession }) {
  const fee = session.amount_paise != null ? `₹${(session.amount_paise / 100).toFixed(0)}` : "—";
  const entries = Object.entries(session.collected_data || {});

  return (
    <div className="card rounded-2xl p-5 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="font-display font-bold text-ink text-sm">Consultation Details</h3>
        {session.status === "paid" ? (
          <span className="badge badge-green inline-flex items-center gap-1">
            <CheckCircle2 size={10} /> Paid {fee}
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 text-amber-700 border border-amber-200 px-2.5 py-1 font-label text-[10px] font-bold">
            <Clock size={10} /> Awaiting payment · {fee}
          </span>
        )}
      </div>
      <div className="grid grid-cols-2 gap-3">
        {entries.map(([key, value]) => (
          <div key={key}>
            <div className="font-label text-[10px] font-bold uppercase tracking-wide text-ink-muted">
              {formatFieldKey(key)}
            </div>
            <div className="font-body text-sm text-ink mt-0.5">{value || "—"}</div>
          </div>
        ))}
        {entries.length === 0 && (
          <p className="font-body text-xs text-ink-muted italic col-span-2">No details collected yet.</p>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npm run typecheck`
Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add frontend/app/dashboard/consultations/ConsultationDetails.tsx
git commit -m "feat: consultation details summary card"
```

---

## Task 5: Consultations page

**Files:**
- Create: `frontend/app/dashboard/consultations/page.tsx`

**Interfaces:**
- Consumes: `api.expertHandoff.listSessions` (Task 3), `api.leads.get` (existing), `ConsultationDetails` (Task 4), `ChatThread` (existing, `frontend/components/chat-thread.tsx`)

- [ ] **Step 1: Write the page**

```tsx
// frontend/app/dashboard/consultations/page.tsx
"use client";
import { useCallback, useEffect, useState } from "react";
import { CheckCircle2, Clock, Phone } from "lucide-react";
import { api, ExpertHandoffSession, Lead } from "@/lib/api";
import { ChatThread } from "@/components/chat-thread";
import { ConsultationDetails } from "./ConsultationDetails";
import { usePolling } from "@/hooks/usePolling";

type Bucket = "awaiting_payment" | "paid";

export default function ConsultationsPage() {
  const [bucket, setBucket] = useState<Bucket>("awaiting_payment");
  const [sessions, setSessions] = useState<ExpertHandoffSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedSession, setSelectedSession] = useState<ExpertHandoffSession | null>(null);
  const [selectedLead, setSelectedLead] = useState<Lead | null>(null);
  const [leadLoading, setLeadLoading] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await api.expertHandoff.listSessions(bucket);
      setSessions(data);
    } catch {
      /* non-critical, list stays as-is */
    } finally {
      setLoading(false);
    }
  }, [bucket]);

  useEffect(() => {
    setLoading(true);
    setSelectedSession(null);
    setSelectedLead(null);
    load();
  }, [bucket, load]);

  usePolling(load, 30000);

  async function selectSession(session: ExpertHandoffSession) {
    setSelectedSession(session);
    setLeadLoading(true);
    try {
      const lead = await api.leads.get(session.lead_id);
      setSelectedLead(lead);
    } catch {
      setSelectedLead(null);
    } finally {
      setLeadLoading(false);
    }
  }

  return (
    <div className="flex h-full">
      <div className="w-[340px] flex-shrink-0 border-r border-border flex flex-col">
        <div className="p-4 border-b border-border">
          <h1 className="font-display text-lg font-bold text-ink mb-3">Consultations</h1>
          <div className="flex gap-2 p-1 bg-surface-subtle border border-border rounded-xl">
            <button
              type="button"
              onClick={() => setBucket("awaiting_payment")}
              className={`flex-1 px-3 py-1.5 rounded-lg font-label text-xs font-bold transition-all ${
                bucket === "awaiting_payment" ? "bg-white text-ink shadow-sm" : "text-ink-muted"
              }`}
            >
              Awaiting Payment
            </button>
            <button
              type="button"
              onClick={() => setBucket("paid")}
              className={`flex-1 px-3 py-1.5 rounded-lg font-label text-xs font-bold transition-all ${
                bucket === "paid" ? "bg-white text-ink shadow-sm" : "text-ink-muted"
              }`}
            >
              Paid
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="p-4 space-y-3">
              {[...Array(4)].map((_, i) => (
                <div key={i} className="h-16 rounded-xl bg-border-subtle animate-pulse" />
              ))}
            </div>
          ) : sessions.length === 0 ? (
            <p className="p-6 text-center font-body text-sm text-ink-muted">
              {bucket === "awaiting_payment" ? "No leads waiting on payment." : "No paid consultations yet."}
            </p>
          ) : (
            sessions.map((session) => (
              <button
                key={session.id}
                type="button"
                onClick={() => selectSession(session)}
                className={`w-full text-left p-4 border-b border-border-subtle hover:bg-surface-subtle transition-colors ${
                  selectedSession?.id === session.id ? "bg-primary-light/40" : ""
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-label text-sm font-semibold text-ink">
                    {session.leads?.name || "Unknown lead"}
                  </span>
                  {session.status === "paid" ? (
                    <CheckCircle2 size={14} className="text-emerald-600" />
                  ) : (
                    <Clock size={14} className="text-amber-600" />
                  )}
                </div>
                <div className="flex items-center gap-1 mt-1 text-xs text-ink-muted font-body">
                  <Phone size={11} />
                  {session.leads?.phone || "—"}
                </div>
              </button>
            ))
          )}
        </div>
      </div>

      <div className="flex-1 flex flex-col overflow-hidden">
        {!selectedSession ? (
          <div className="flex-1 flex items-center justify-center">
            <p className="font-body text-sm text-ink-muted">Select a lead to view details and reply.</p>
          </div>
        ) : (
          <div className="flex-1 flex flex-col overflow-hidden">
            <div className="p-4 border-b border-border">
              <ConsultationDetails session={selectedSession} />
            </div>
            <div className="flex-1 overflow-hidden">
              {leadLoading ? (
                <div className="p-6 text-center font-body text-sm text-ink-muted">Loading conversation…</div>
              ) : selectedLead ? (
                <ChatThread lead={selectedLead} onLeadUpdate={setSelectedLead} />
              ) : (
                <div className="p-6 text-center font-body text-sm text-ink-muted">Could not load this lead.</div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npm run typecheck`
Expected: no errors

- [ ] **Step 3: Lint**

Run: `cd frontend && npm run lint`
Expected: no errors or warnings in this file (this repo's lint failure on unused vars fails the build — double check every import is used)

- [ ] **Step 4: Commit**

```bash
git add frontend/app/dashboard/consultations/page.tsx
git commit -m "feat: Consultations page — list, details, and in-place reply"
```

---

## Task 6: Sidebar navigation entry

**Files:**
- Modify: `frontend/components/sidebar.tsx`

- [ ] **Step 1: Add the import**

Find the Conversations icon import (`MessageSquare` from `lucide-react`) near the top of `sidebar.tsx` and add `Headset` (or check what icon is already imported and unused that fits "consultations" — if none, add `Headset` to the existing `lucide-react` import line):

```typescript
import { MessageSquare, Headset, /* ...existing icons... */ } from "lucide-react";
```

- [ ] **Step 2: Add the nav entry**

In `sidebar.tsx`, right after the existing "TOP LEVEL: Conversations" block (the one ending in `</Link>}` around where `inboxCount` is rendered), add:

```tsx
        {/* TOP LEVEL: Consultations */}
        {isSubscribed && messagingOn && canAny(["conversations.view", "conversations.reply"]) && <Link
          href="/dashboard/consultations"
          className={cn(
            "flex items-center gap-3 px-3 py-2 rounded-xl text-sm font-semibold transition-all duration-150 group",
            pathname.startsWith("/dashboard/consultations")
              ? "bg-[#f5f3ff] text-[#5b21b6]"
              : "text-[#1c1917] hover:bg-[#f0ece4] hover:text-[#1c1917]"
          )}
        >
          <Headset size={16} className={pathname.startsWith("/dashboard/consultations") ? "text-[#5b21b6]" : "text-[#1c1917] group-hover:text-[#1c1917]"} />
          <span className="flex-grow">Consultations</span>
        </Link>}
```

- [ ] **Step 3: Typecheck and lint**

Run: `cd frontend && npm run typecheck && npm run lint`
Expected: no errors

- [ ] **Step 4: Manual verification in the browser**

Run: `cd frontend && npm run dev`, log in, confirm "Consultations" appears in the sidebar between Conversations and Leads, navigate to it, confirm the empty state renders for both tabs (no sessions exist yet in a fresh check), confirm no console errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/sidebar.tsx
git commit -m "feat: add Consultations to dashboard sidebar navigation"
```
