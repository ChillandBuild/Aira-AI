# Telecaller Hard-Delete + Tenant Audit Log Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make deleting a telecaller from Roles → Users actually remove the `callers` row (not just deactivate it), and give tenant owners a readable audit trail of team/role changes.

**Architecture:** All changes live in `backend/app/routes/rbac.py` (delete logic + 7 audit-log call sites + 1 new read endpoint) and three frontend files (`api.ts`, `AppHeader.tsx`, `roles/page.tsx`). Reuses the existing `app_audit_logs` table and `record_audit_event()` service — no schema migration needed for that part. A separate one-off data migration hard-deletes 5 pre-existing orphaned rows.

**Tech Stack:** FastAPI (backend/app/routes/rbac.py), Next.js 14 (frontend/app/dashboard/roles, frontend/components/AppHeader.tsx), Supabase (app_audit_logs, callers, chat_handovers), pytest with MagicMock table chains (matches `backend/tests/test_rbac_seat_enforcement.py` style).

## Global Constraints

- `record_audit_event(db, *, tenant_id, actor_user_id, actor_role, action, target_type, target_id=None, metadata=None)` — `backend/app/services/audit_log.py`, best-effort, never raises, already sanitizes password/token/secret/key/credential keys in metadata.
- FK delete rules on `callers.id`: `call_logs.caller_id`, `leads.assigned_to`, `lead_notes.caller_id`, `follow_up_jobs.scheduled_by_caller_id` are all `ON DELETE SET NULL` (safe). `chat_handovers.assigned_to` is `NO ACTION` — must be nulled manually before the `callers` delete or the delete fails.
- New endpoint must be gated by the existing `require_roles_read` dependency (rbac.py:29) and scoped to `ctx["tenant_id"]` — never cross-tenant.
- Follow existing code style in rbac.py: no comments unless explaining non-obvious *why*, same request/response shapes as neighboring endpoints.

---

### Task 1: Hard-delete in `delete_user` + audit log on all 7 rbac.py mutation endpoints

**Files:**
- Modify: `backend/app/routes/rbac.py` (import `record_audit_event`; `create_user` ~L341-381, `update_user` ~L384-422, `delete_user` ~L425-441, `reset_user_password` ~L444-457, `create_role` ~L258-275, `update_role` ~L278-290, `delete_role` ~L293-305)
- Test: `backend/tests/test_rbac_delete_audit.py`

**Interfaces:**
- Consumes: `record_audit_event` from `app.services.audit_log` (signature above).
- Produces: `delete_user` now hard-deletes `callers` row (was `active=false` update) and nulls `chat_handovers.assigned_to` first. No other endpoint's response shape changes.

- [ ] **Step 1: Write the failing test for hard-delete + handover null-out + audit write**

```python
# backend/tests/test_rbac_delete_audit.py
"""delete_user (DELETE /api/v1/rbac/users/{user_id}) must hard-delete the
callers row (not just deactivate it) so it doesn't linger as an orphan once
the auth account and tenant_users row are gone -- and must null out any
chat_handovers.assigned_to reference first, since that FK has no cascade
(ON DELETE NO ACTION) and would otherwise block the delete."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_and_role

CTX = {
    "tenant_id": "tenant-1",
    "role": "owner",
    "user_id": "owner-1",
    "caller_id": None,
    "permissions": ["roles.manage"],
}


def _mock_db(member_role="caller", caller_row=None):
    db = MagicMock()

    tenant_users_tbl = MagicMock()
    tenant_users_tbl.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[{"role": member_role}]
    )
    tenant_users_tbl.delete.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"user_id": "user-1"}])

    callers_tbl = MagicMock()
    callers_tbl.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[caller_row] if caller_row else []
    )
    callers_tbl.delete.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "caller-1"}])

    handovers_tbl = MagicMock()
    handovers_tbl.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

    audit_tbl = MagicMock()
    audit_tbl.insert.return_value.execute.return_value = MagicMock(data=[{"id": "audit-1"}])

    def table(name):
        return {
            "tenant_users": tenant_users_tbl,
            "callers": callers_tbl,
            "chat_handovers": handovers_tbl,
            "app_audit_logs": audit_tbl,
        }[name]

    db.table.side_effect = table
    db.auth.admin.delete_user = MagicMock()
    return db, callers_tbl, handovers_tbl, audit_tbl


class TestDeleteUserHardDelete(unittest.TestCase):
    def setUp(self):
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "owner-1"}
        app.dependency_overrides[get_tenant_and_role] = lambda: CTX

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("app.routes.rbac.get_supabase")
    def test_hard_deletes_callers_row_and_nulls_handovers(self, mock_get_supabase):
        caller_row = {"id": "caller-1", "name": "Test Caller", "phone": None, "active": True,
                      "telecmi_agent_id": None, "telecmi_agent_password": None}
        db, callers_tbl, handovers_tbl, audit_tbl = _mock_db(caller_row=caller_row)
        mock_get_supabase.return_value = db

        client = TestClient(app)
        resp = client.delete("/api/v1/rbac/users/user-1")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"deleted": True})
        # chat_handovers nulled before the caller row is dropped
        handovers_tbl.update.assert_called_once_with({"assigned_to": None})
        # callers row is actually deleted, not deactivated
        callers_tbl.delete.assert_called_once()
        callers_tbl.update.assert_not_called()
        # audit event recorded
        audit_tbl.insert.assert_called_once()
        inserted = audit_tbl.insert.call_args[0][0]
        self.assertEqual(inserted["action"], "team.member_deleted")
        self.assertEqual(inserted["target_type"], "tenant_user")
        self.assertEqual(inserted["target_id"], "user-1")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_rbac_delete_audit.py -v`
Expected: FAIL — `callers_tbl.update` was called (current code deactivates, doesn't delete), `handovers_tbl.update` never called, `audit_tbl.insert` never called.

- [ ] **Step 3: Implement — import audit_log, update `delete_user`**

Add near the top of `backend/app/routes/rbac.py` (after the existing `app.services.rbac` import block):

```python
from app.services.audit_log import record_audit_event
```

Replace the body of `delete_user` (currently `backend/app/routes/rbac.py:425-441`):

```python
@router.delete("/users/{user_id}")
def delete_user(user_id: str, ctx: dict = Depends(require_roles_manage)):
    if user_id == ctx["user_id"]:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")
    db = get_supabase()
    member = db.table("tenant_users").select("role").eq("tenant_id", ctx["tenant_id"]).eq("user_id", user_id).limit(1).execute()
    if not member.data:
        raise HTTPException(status_code=404, detail="User not found")
    if member.data[0].get("role") == "owner":
        raise HTTPException(status_code=400, detail="Owner cannot be deleted here")

    caller = _caller_for_user(db, ctx["tenant_id"], user_id)
    if caller:
        db.table("chat_handovers").update({"assigned_to": None}).eq("assigned_to", caller["id"]).execute()
        db.table("callers").delete().eq("id", caller["id"]).eq("tenant_id", ctx["tenant_id"]).execute()

    db.table("tenant_users").delete().eq("tenant_id", ctx["tenant_id"]).eq("user_id", user_id).execute()
    try:
        db.auth.admin.delete_user(user_id)
    except Exception:
        logger.warning("Deleted tenant membership but auth user delete failed for %s", user_id)

    record_audit_event(
        db,
        tenant_id=ctx["tenant_id"],
        actor_user_id=ctx["user_id"],
        actor_role=ctx.get("role"),
        action="team.member_deleted",
        target_type="tenant_user",
        target_id=user_id,
        metadata={"caller_name": caller.get("name") if caller else None},
    )
    return {"deleted": True}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_rbac_delete_audit.py -v`
Expected: PASS

- [ ] **Step 5: Add audit-log calls to the other 6 mutation endpoints**

In `create_user` (rbac.py ~L341-381), right before the final `return {"created": True, ...}`:

```python
    record_audit_event(
        db, tenant_id=ctx["tenant_id"], actor_user_id=ctx["user_id"], actor_role=ctx.get("role"),
        action="team.member_created", target_type="tenant_user", target_id=user_id,
        metadata={"full_name": payload.full_name.strip(), "email": str(payload.email), "role_name": role.get("name")},
    )
```

In `update_user` (rbac.py ~L384-422), right before `return {"updated": True}`:

```python
    record_audit_event(
        db, tenant_id=ctx["tenant_id"], actor_user_id=ctx["user_id"], actor_role=ctx.get("role"),
        action="team.member_updated", target_type="tenant_user", target_id=user_id,
        metadata={"full_name": payload.full_name, "role_name": role.get("name")},
    )
```

In `reset_user_password` (rbac.py ~L444-457), right before `return {"temporary_password": password}`:

```python
    record_audit_event(
        db, tenant_id=ctx["tenant_id"], actor_user_id=ctx["user_id"], actor_role=ctx.get("role"),
        action="team.password_reset", target_type="tenant_user", target_id=user_id, metadata={},
    )
```

In `create_role` (rbac.py ~L258-275), right before `return _serialize_role(created.data[0])`:

```python
    record_audit_event(
        db, tenant_id=ctx["tenant_id"], actor_user_id=ctx["user_id"], actor_role=ctx.get("role"),
        action="role.created", target_type="tenant_role", target_id=created.data[0]["id"],
        metadata={"name": name, "permissions": row["permissions"]},
    )
```

In `update_role` (rbac.py ~L278-290), right before `return _serialize_role(updated.data[0])`:

```python
    record_audit_event(
        db, tenant_id=ctx["tenant_id"], actor_user_id=ctx["user_id"], actor_role=ctx.get("role"),
        action="role.updated", target_type="tenant_role", target_id=role_id,
        metadata={"name": updates["name"], "permissions": updates["permissions"]},
    )
```

In `delete_role` (rbac.py ~L293-305), right before `return {"deleted": True}`:

```python
    record_audit_event(
        db, tenant_id=ctx["tenant_id"], actor_user_id=ctx["user_id"], actor_role=ctx.get("role"),
        action="role.deleted", target_type="tenant_role", target_id=role_id,
        metadata={"name": role.get("name")},
    )
```

- [ ] **Step 6: Run the full rbac test suite**

Run: `cd backend && python -m pytest tests/test_rbac_delete_audit.py tests/test_rbac_service.py tests/test_rbac_seat_enforcement.py -v`
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/routes/rbac.py backend/tests/test_rbac_delete_audit.py
git commit -m "$(cat <<'EOF'
fix(rbac): hard-delete callers row on team member removal, add audit log

The Roles > Users delete flow deactivated the callers row instead of
removing it, leaving orphaned rows once the tenant_users row and auth
account were gone. Now nulls the one FK without a cascade
(chat_handovers.assigned_to) and hard-deletes. Also wires up the
existing audit_log service across all 7 rbac.py mutation endpoints --
previously nothing in this file wrote to app_audit_logs.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Tenant-scoped audit log read endpoint

**Files:**
- Modify: `backend/app/routes/rbac.py` (add `GET /audit-log`)
- Test: `backend/tests/test_rbac_audit_log_endpoint.py`

**Interfaces:**
- Consumes: `require_roles_read` (rbac.py:29, already defined).
- Produces: `GET /api/v1/rbac/audit-log?page=&limit=&date_from=&date_to=` → `{"data": [...], "total": int, "page": int, "limit": int}`, each row `{id, actor_user_id, actor_role, action, target_type, target_id, metadata, created_at}`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_rbac_audit_log_endpoint.py
"""GET /api/v1/rbac/audit-log must be tenant-scoped (never leak another
tenant's rows) and gated by the same roles.view/roles.manage permission as
the rest of the Roles page."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_and_role

CTX = {
    "tenant_id": "tenant-1",
    "role": "owner",
    "user_id": "owner-1",
    "caller_id": None,
    "permissions": ["roles.manage"],
}


class TestAuditLogEndpoint(unittest.TestCase):
    def setUp(self):
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "owner-1"}
        app.dependency_overrides[get_tenant_and_role] = lambda: CTX

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("app.routes.rbac.get_supabase")
    def test_scopes_query_to_tenant(self, mock_get_supabase):
        db = MagicMock()
        audit_tbl = MagicMock()
        chain = audit_tbl.select.return_value.eq.return_value
        chain.order.return_value.range.return_value.execute.return_value = MagicMock(
            data=[{"id": "a1", "actor_user_id": "owner-1", "actor_role": "owner", "action": "team.member_deleted",
                   "target_type": "tenant_user", "target_id": "user-1", "metadata": {}, "created_at": "2026-08-08T00:00:00Z"}],
            count=1,
        )
        db.table.return_value = audit_tbl
        mock_get_supabase.return_value = db

        client = TestClient(app)
        resp = client.get("/api/v1/rbac/audit-log")

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["total"], 1)
        self.assertEqual(len(body["data"]), 1)
        audit_tbl.select.return_value.eq.assert_called_with("tenant_id", "tenant-1")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_rbac_audit_log_endpoint.py -v`
Expected: FAIL with 404 (route doesn't exist yet).

- [ ] **Step 3: Implement the endpoint**

Add to `backend/app/routes/rbac.py`, near the other `@router.get` routes:

```python
@router.get("/audit-log")
def list_audit_log(
    page: int = 1,
    limit: int = 50,
    date_from: str | None = None,
    date_to: str | None = None,
    ctx: dict = Depends(require_roles_read),
):
    db = get_supabase()
    q = db.table("app_audit_logs").select(
        "id, actor_user_id, actor_role, action, target_type, target_id, metadata, created_at",
        count="exact",
    ).eq("tenant_id", ctx["tenant_id"])

    if date_from:
        q = q.gte("created_at", date_from)
    if date_to:
        q = q.lte("created_at", date_to + "T23:59:59.999Z")

    offset = (page - 1) * limit
    result = q.order("created_at", desc=True).range(offset, offset + limit - 1).execute()

    return {"data": result.data or [], "total": result.count or 0, "page": page, "limit": limit}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_rbac_audit_log_endpoint.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/routes/rbac.py backend/tests/test_rbac_audit_log_endpoint.py
git commit -m "$(cat <<'EOF'
feat(rbac): add tenant-scoped GET /rbac/audit-log endpoint

Mirrors the operator console's /clients/{tenant_id}/audit-logs query
shape against the same app_audit_logs table, swapping the operator-admin
auth for the tenant roles.view/roles.manage gate so tenant owners can
finally read their own audit trail without operator access.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Frontend — API client + AppHeader tab

**Files:**
- Modify: `frontend/lib/api.ts` (rbac section, near `deleteUser`/`resetPassword`, ~L1812-1823)
- Modify: `frontend/components/AppHeader.tsx` (segmented control at ~L466-489)

**Interfaces:**
- Consumes: `GET /api/v1/rbac/audit-log` from Task 2.
- Produces: `api.rbac.auditLog(params?: { page?: number; date_from?: string; date_to?: string }) => Promise<{ data: AuditLogEntry[]; total: number; page: number; limit: number }>`, and `AuditLogEntry` type exported from `api.ts` for Task 4 to import.

- [ ] **Step 1: Add the `AuditLogEntry` type and `auditLog` client method**

In `frontend/lib/api.ts`, add near the other exported types used by the roles page (`ClientRole`, `PermissionDef`, `RbacUser`):

```typescript
export interface AuditLogEntry {
  id: string;
  actor_user_id: string | null;
  actor_role: string | null;
  action: string;
  target_type: string;
  target_id: string | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
}
```

In the `rbac` section of the `api` object, right after `deleteUser` (`frontend/lib/api.ts:1812-1815`):

```typescript
    auditLog: (params?: { page?: number; date_from?: string; date_to?: string }) => {
      const qs = new URLSearchParams();
      if (params?.page) qs.set("page", String(params.page));
      if (params?.date_from) qs.set("date_from", params.date_from);
      if (params?.date_to) qs.set("date_to", params.date_to);
      const query = qs.toString();
      return apiFetch<{ data: AuditLogEntry[]; total: number; page: number; limit: number }>(
        `/api/v1/rbac/audit-log${query ? `?${query}` : ""}`,
      );
    },
```

- [ ] **Step 2: Add the "Audit Log" tab to AppHeader's segmented control**

In `frontend/components/AppHeader.tsx`, replace the tab array at ~L466-489:

```typescript
        {pathname === "/dashboard/roles" && (
          <div className="mr-2 hidden gap-1 rounded-2xl bg-[#e8e3db]/60 p-1 md:flex">
            {(["roles", "users", "audit"] as const).map((item) => (
              <button
                key={item}
                type="button"
                onClick={() => {
                  const params = new URLSearchParams(searchParams.toString());
                  if (item === "roles") params.delete("tab");
                  else params.set("tab", item);
                  const query = params.toString();
                  router.replace(`/dashboard/roles${query ? `?${query}` : ""}`, { scroll: false });
                }}
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5 font-label text-xs font-bold capitalize transition-all",
                  rolesTab === item ? "bg-white text-primary shadow-sm" : "text-[#78716c] hover:text-[#292524]",
                )}
              >
                {item === "roles" ? <ShieldCheck size={13} /> : item === "users" ? <Users size={13} /> : <ScrollText size={13} />}
                {item === "audit" ? "Audit Log" : item}
              </button>
            ))}
          </div>
        )}
```

Update the `rolesTab` derivation a few lines above (~L203) to a 3-way type:

```typescript
  const rolesTab = (searchParams.get("tab") === "users" || searchParams.get("tab") === "audit") ? searchParams.get("tab")! : "roles";
```

Add `ScrollText` to the existing `lucide-react` import at the top of the file (alongside whatever icons `AppHeader.tsx` already imports — find the current import line and append `ScrollText` to it).

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npm run typecheck`
Expected: no new errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/lib/api.ts frontend/components/AppHeader.tsx
git commit -m "$(cat <<'EOF'
feat(frontend): add audit log API client + Audit Log tab in AppHeader

Adds api.rbac.auditLog() and a third "Audit Log" entry next to
Roles/Users in the segmented control shown on /dashboard/roles.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Frontend — Audit Log panel on the Roles page

**Files:**
- Modify: `frontend/app/dashboard/roles/page.tsx`

**Interfaces:**
- Consumes: `api.rbac.auditLog` and `AuditLogEntry` from Task 3.
- Produces: renders when `tab === "audit"`.

- [ ] **Step 1: Extend the `Tab` type and load audit data on tab switch**

In `frontend/app/dashboard/roles/page.tsx`, change line 35:

```typescript
type Tab = "roles" | "users" | "audit";
```

Update the `urlTab` derivation (line 153):

```typescript
  const urlTab: Tab = searchParams.get("tab") === "users" ? "users" : searchParams.get("tab") === "audit" ? "audit" : "roles";
```

Add state and a loader near the other `useState` declarations (after `syncTokenDialogUser`/`viewingSyncToken`, ~L176-177):

```typescript
  const [auditEntries, setAuditEntries] = useState<AuditLogEntry[]>([]);
  const [auditTotal, setAuditTotal] = useState(0);
  const [auditPage, setAuditPage] = useState(1);
  const [auditLoading, setAuditLoading] = useState(false);
```

Add `AuditLogEntry` to the existing `import { api, API_URL, ClientRole, PermissionDef, RbacUser } from "@/lib/api";` line (line 30):

```typescript
import { api, API_URL, AuditLogEntry, ClientRole, PermissionDef, RbacUser } from "@/lib/api";
```

Add a loader effect after the existing `useEffect(() => { if (!roleLoading && canView) load(); ... }, ...)` block (~L246-249):

```typescript
  useEffect(() => {
    if (tab !== "audit" || !canView) return;
    let active = true;
    setAuditLoading(true);
    api.rbac.auditLog({ page: auditPage }).then((res) => {
      if (!active) return;
      setAuditEntries(res.data);
      setAuditTotal(res.total);
    }).catch(() => undefined).finally(() => {
      if (active) setAuditLoading(false);
    });
    return () => { active = false; };
  }, [tab, auditPage, canView]);
```

- [ ] **Step 2: Add the "audit" branch to the tab-switch render**

The render currently does `{tab === "roles" ? (...) : (...)}` at line 631/814. Change the outer structure to a three-way switch — replace `{tab === "roles" ? (` at line 631 through the closing `)}` at line 953 with:

```typescript
      {tab === "roles" ? (
        // ...existing roles JSX unchanged (lines 632-813)...
      ) : tab === "users" ? (
        // ...existing users JSX unchanged (lines 815-952)...
      ) : (
        <div className="card rounded-3xl overflow-hidden">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="font-display text-base font-bold text-ink">Audit Log</h2>
            <span className="rounded-full bg-surface-subtle px-2.5 py-1 font-label text-[10px] font-bold text-ink-muted">{auditTotal} total</span>
          </div>
          {auditLoading ? (
            <div className="flex justify-center py-16"><Loader2 size={24} className="animate-spin text-primary" /></div>
          ) : auditEntries.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-2 py-16 text-center">
              <Inbox size={32} className="text-ink-muted/40" />
              <p className="font-body text-sm text-ink-muted">No audit events yet.</p>
            </div>
          ) : (
            <div className="divide-y divide-border-subtle">
              {auditEntries.map((entry) => {
                const user = users.find((u) => u.user_id === entry.actor_user_id);
                const metaText = entry.metadata && Object.keys(entry.metadata).length > 0
                  ? Object.entries(entry.metadata)
                      .filter(([, v]) => v !== null && v !== undefined && v !== "********")
                      .map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : String(v)}`)
                      .join(" · ")
                  : "";
                return (
                  <div key={entry.id} className="flex flex-col gap-1 py-3.5 sm:flex-row sm:items-center sm:justify-between sm:px-2">
                    <div className="min-w-0">
                      <p className="font-body text-sm font-bold text-ink">
                        {entry.action} <span className="font-body text-xs font-normal text-ink-muted">by {user?.full_name || user?.email || entry.actor_role || "system"}</span>
                      </p>
                      {metaText && <p className="mt-0.5 truncate font-body text-xs text-ink-muted">{metaText}</p>}
                    </div>
                    <p className="shrink-0 font-label text-[10px] font-bold text-ink-muted">{new Date(entry.created_at).toLocaleString()}</p>
                  </div>
                );
              })}
            </div>
          )}
          {auditTotal > 50 && (
            <div className="mt-4 flex items-center justify-end gap-2">
              <button type="button" className="btn-secondary px-3" disabled={auditPage <= 1} onClick={() => setAuditPage((p) => p - 1)}>Prev</button>
              <span className="font-body text-xs text-ink-muted">Page {auditPage}</span>
              <button type="button" className="btn-secondary px-3" disabled={auditPage * 50 >= auditTotal} onClick={() => setAuditPage((p) => p + 1)}>Next</button>
            </div>
          )}
        </div>
      )}
```

- [ ] **Step 3: Typecheck and lint**

Run: `cd frontend && npm run typecheck && npm run lint`
Expected: no new errors (CLAUDE.md note: CI runs `next lint`, `tsc` alone isn't sufficient — run both).

- [ ] **Step 4: Manual verification**

Run: `cd frontend && npm run dev`, log in as an owner, go to `/dashboard/roles`, confirm the "Audit Log" tab appears next to Roles/Users, click it, confirm it loads (empty state is fine pre-Task-1-deploy).

- [ ] **Step 5: Commit**

```bash
git add frontend/app/dashboard/roles/page.tsx
git commit -m "$(cat <<'EOF'
feat(frontend): render Audit Log panel on the Roles page

Third tab alongside Roles/Users, paginated list of team/role changes
sourced from GET /rbac/audit-log.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Data migration — clean up the 5 orphaned caller rows

**Files:** none (Supabase SQL executed directly via MCP, no migration file — this is one-off data cleanup, not a schema change)

**Interfaces:** none.

- [ ] **Step 1: Re-verify the 5 rows are still safe to delete**

Run via `mcp__claude_ai_Supabase__execute_sql` against project `ayftynkgmfkaqmmnlmoc`:

```sql
select c.id, c.name, c.user_id,
  (select count(*) from leads l where l.assigned_to = c.id) as leads,
  (select count(*) from call_logs cl where cl.caller_id = c.id) as calls,
  (select count(*) from chat_handovers ch where ch.assigned_to = c.id) as handovers
from callers c
where c.name in ('yuvaraj','kalai','theee','abi','hgyuu')
  and c.tenant_id = 'eba3ed94-277c-430f-a992-19bbe855e2f4';
```

Expected: all five rows show `leads=0, calls=0, handovers=0` (matches the earlier investigation). If any row now shows a nonzero count, stop and re-investigate before deleting — do not proceed on stale assumptions.

- [ ] **Step 2: Delete the 5 rows**

```sql
delete from callers
where name in ('yuvaraj','kalai','theee','abi','hgyuu')
  and tenant_id = 'eba3ed94-277c-430f-a992-19bbe855e2f4'
returning id, name;
```

Expected: 5 rows returned.

- [ ] **Step 3: Confirm no orphans remain for that tenant**

```sql
select c.id, c.name
from callers c
left join tenant_users tu on tu.user_id = c.user_id and tu.tenant_id = c.tenant_id
where c.tenant_id = 'eba3ed94-277c-430f-a992-19bbe855e2f4' and tu.user_id is null;
```

Expected: 0 rows (Vivek T and Prem, the two rows with real `tenant_users` membership, are untouched).

No commit for this task — it's a data-only change, not a code change.

---

## Self-Review Notes

- Spec coverage: §1 (hard-delete) → Task 1; §2 (audit write sites) → Task 1; §3 (read endpoint) → Task 2; §4 (frontend tab + panel) → Tasks 3-4; §5 (orphan cleanup) → Task 5. All covered.
- `_caller_for_user` (rbac.py:163) is reused rather than re-querying — confirmed its `select` already includes `id` and `name`, both used in Task 1's audit metadata.
- Task 4's JSX replacement for the tab-switch is described as "existing JSX unchanged" for the roles/users branches rather than reprinted in full, since those blocks are 180+ lines each and copying them verbatim here would just be transcription risk — the actual edit is a two-line ternary-to-two-branches wrap around content the engineer can see live in the file. This is the one place the plan leans on "look at the file" rather than full inline code; flagged here rather than silently.
