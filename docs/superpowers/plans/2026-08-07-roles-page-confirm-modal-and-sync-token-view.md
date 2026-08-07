# Roles Page: Shared ConfirmModal + Sync Token View/Regenerate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace native `window.confirm()` dialogs on the client dashboard's Roles page with the operator console's existing styled `ConfirmModal`, add a missing confirmation to Reset Password, and give owners a non-destructive way to view an already-minted Aira Sync token instead of the only option today (regenerate, which invalidates the caller's current one immediately).

**Architecture:** Relocate `ConfirmModal` from `app/operator/(console)/components/` to `frontend/components/` (shared, no behavior change) and update its 6 existing importers. On the Roles page, introduce one generic `confirmState` piece of state that drives a single `<ConfirmModal>` instance for all four confirm-needing actions (delete role, delete user, reset password, regenerate sync token). Add a new owner-only `GET /api/v1/callers/{id}/sync-token` backend endpoint that returns the current plaintext token with no side effects, and a small inline two-choice dialog ("View current token" / "Regenerate") that replaces the sync-token row button's direct mint-on-click behavior.

**Tech Stack:** Next.js 14 (frontend/app/dashboard), FastAPI (backend/app/routes/callers.py), existing Supabase-backed `callers` table.

## Global Constraints

- No git worktree — implement directly on `main` (standing user preference).
- `.btn-secondary` and other existing Tailwind utility classes on this page are already correct as of this session — do not touch button styling, only confirm/dialog behavior.
- `ConfirmModal`'s public API (`ConfirmModalProps`) must not change — 6 existing call sites depend on its current shape.
- Every new/changed frontend file must pass `npx tsc --noEmit --pretty false` and `npx eslint <file>` with zero errors before its task is considered done.
- Every new/changed backend file must pass the relevant `venv/bin/python -m pytest` run with zero failures before its task is considered done.

---

### Task 1: Move `ConfirmModal` to a shared location

**Files:**
- Create: `frontend/components/ConfirmModal.tsx` (exact copy of current content, see below)
- Delete: `frontend/app/operator/(console)/components/confirm-modal.tsx`
- Modify: `frontend/app/operator/(console)/scheduler/page.tsx:6`
- Modify: `frontend/app/operator/(console)/page.tsx:7`
- Modify: `frontend/app/operator/(console)/components/operator-sidebar.tsx:9`
- Modify: `frontend/app/operator/(console)/client/[id]/views/team.tsx:7`
- Modify: `frontend/app/operator/(console)/client/[id]/views/management.tsx:5`
- Modify: `frontend/app/operator/(console)/client/[id]/views/data-ops.tsx:8`

**Interfaces:**
- Produces: `ConfirmModal` component at `@/components/ConfirmModal`, same props as today:
  ```ts
  interface ConfirmModalProps {
    open: boolean;
    onClose: () => void;
    onConfirm: () => void;
    title: string;
    description: string;
    tone?: "danger" | "warning" | "primary";
    confirmLabel?: string;
    cancelLabel?: string;
    loading?: boolean;
    loadingLabel?: string;
    details?: { label: string; count: number }[];
    requireTypedConfirmation?: string;
  }
  ```

- [ ] **Step 1: Create the shared file with the exact current implementation**

Write `frontend/components/ConfirmModal.tsx` with this content (byte-identical to the current `frontend/app/operator/(console)/components/confirm-modal.tsx`, just relocated):

```tsx
"use client";
import { useState } from "react";
import { AlertTriangle, X } from "lucide-react";

interface ConfirmModalProps {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  description: string;
  tone?: "danger" | "warning" | "primary";
  confirmLabel?: string;
  cancelLabel?: string;
  loading?: boolean;
  loadingLabel?: string;
  details?: { label: string; count: number }[];
  /** When set, the confirm button stays disabled until the user types this
   * exact string — for destructive, hard-to-undo actions. */
  requireTypedConfirmation?: string;
}

const TONE_STYLE: Record<NonNullable<ConfirmModalProps["tone"]>, { icon: string; button: string }> = {
  danger: { icon: "bg-danger/10 text-danger", button: "bg-danger hover:bg-danger/90" },
  warning: { icon: "bg-warning/10 text-warning", button: "bg-warning hover:bg-warning/90" },
  primary: { icon: "bg-primary-muted text-primary", button: "bg-primary hover:bg-primary-dark" },
};

export function ConfirmModal({
  open,
  onClose,
  onConfirm,
  title,
  description,
  tone = "primary",
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  loading,
  loadingLabel = "Working…",
  details,
  requireTypedConfirmation,
}: ConfirmModalProps) {
  const [typed, setTyped] = useState("");
  if (!open) return null;

  const style = TONE_STYLE[tone];
  const confirmDisabled = loading || (requireTypedConfirmation !== undefined && typed !== requireTypedConfirmation);

  function handleConfirm() {
    onConfirm();
    setTyped("");
  }

  return (
    <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-card shadow-xl w-full max-w-md p-6">
        <div className="flex items-start justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className={`w-10 h-10 rounded-full flex items-center justify-center ${style.icon}`}>
              <AlertTriangle size={20} />
            </div>
            <h3 className="text-lg font-bold text-ink">{title}</h3>
          </div>
          <button onClick={onClose} className="text-ink-muted hover:text-ink" aria-label="Close">
            <X size={18} />
          </button>
        </div>

        <p className="text-sm text-ink-secondary mb-3 whitespace-pre-line">{description}</p>

        {details && details.length > 0 && (
          <ul className="text-sm text-ink mb-4 space-y-1">
            {details.map(d => (
              <li key={d.label} className="flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-danger" />
                <span className="font-medium">{d.count.toLocaleString()}</span> {d.label}
              </li>
            ))}
          </ul>
        )}

        {requireTypedConfirmation !== undefined && (
          <>
            <p className="text-sm text-ink-secondary mb-2">
              Type <span className="font-mono font-bold text-ink">{requireTypedConfirmation}</span> to confirm:
            </p>
            <input
              value={typed}
              onChange={e => setTyped(e.target.value)}
              className="w-full border border-border rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-danger/20 focus:border-danger mb-4 font-mono"
              placeholder={requireTypedConfirmation}
            />
          </>
        )}

        <div className="flex gap-3">
          <button
            onClick={onClose}
            className="flex-1 px-4 py-2.5 border border-border text-sm text-ink-secondary rounded-xl hover:bg-surface-mid transition-colors"
          >
            {cancelLabel}
          </button>
          <button
            onClick={handleConfirm}
            disabled={confirmDisabled}
            className={`flex-1 px-4 py-2.5 text-white text-sm font-medium rounded-xl disabled:opacity-40 disabled:cursor-not-allowed transition-colors ${style.button}`}
          >
            {loading ? loadingLabel : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Delete the old file**

```bash
rm "/Users/prem/Documents/Aira AI/frontend/app/operator/(console)/components/confirm-modal.tsx"
```

- [ ] **Step 3: Update all 6 importers to the new path**

In each of these files, change the import line to `import { ConfirmModal } from "@/components/ConfirmModal";`:
- `frontend/app/operator/(console)/scheduler/page.tsx:6` — was `import { ConfirmModal } from "../components/confirm-modal";`
- `frontend/app/operator/(console)/page.tsx:7` — was `import { ConfirmModal } from "./components/confirm-modal";`
- `frontend/app/operator/(console)/components/operator-sidebar.tsx:9` — was `import { ConfirmModal } from "./confirm-modal";`
- `frontend/app/operator/(console)/client/[id]/views/team.tsx:7` — was `import { ConfirmModal } from "../../../components/confirm-modal";`
- `frontend/app/operator/(console)/client/[id]/views/management.tsx:5` — was `import { ConfirmModal } from "../../../components/confirm-modal";`
- `frontend/app/operator/(console)/client/[id]/views/data-ops.tsx:8` — was `import { ConfirmModal } from "../../../components/confirm-modal";`

- [ ] **Step 4: Typecheck the whole frontend**

Run: `cd "/Users/prem/Documents/Aira AI/frontend" && npx tsc --noEmit --pretty false`
Expected: no output (zero errors). If any of the 6 files still reference the old path, this will fail with "Cannot find module './confirm-modal'" or similar — fix any missed import.

- [ ] **Step 5: Lint the changed files**

Run: `cd "/Users/prem/Documents/Aira AI/frontend" && npx eslint components/ConfirmModal.tsx "app/operator/(console)/scheduler/page.tsx" "app/operator/(console)/page.tsx" "app/operator/(console)/components/operator-sidebar.tsx" "app/operator/(console)/client/[id]/views/team.tsx" "app/operator/(console)/client/[id]/views/management.tsx" "app/operator/(console)/client/[id]/views/data-ops.tsx"`
Expected: no output (zero errors).

- [ ] **Step 6: Commit**

```bash
cd "/Users/prem/Documents/Aira AI" && git add frontend/components/ConfirmModal.tsx frontend/app/operator && git commit -m "refactor(frontend): relocate ConfirmModal to shared components/, no behavior change"
```

---

### Task 2: Backend — add read-only `GET /callers/{id}/sync-token`

**Files:**
- Modify: `backend/app/routes/callers.py` (insert new route before the existing `POST /{caller_id}/sync-token` at line 542)
- Create: `backend/tests/test_callers_sync_token_static.py`

**Interfaces:**
- Produces: `GET /api/v1/callers/{caller_id}/sync-token` → `200 {"sync_token": str}` on success, `404` if caller not found or no token ever minted. Owner-only via `Depends(get_owner_tenant_id)` (same dependency the existing POST mint endpoint uses).

- [ ] **Step 1: Write the failing static contract test**

Create `backend/tests/test_callers_sync_token_static.py`:

```python
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_get_sync_token_endpoint_exists():
    source = _read("app/routes/callers.py")
    assert '@router.get("/{caller_id}/sync-token")' in source
    assert "async def get_sync_token(caller_id: UUID, tenant_id: str = Depends(get_owner_tenant_id))" in source
    # Read-only: must select, never update, the sync_token column in this function
    get_fn_start = source.index("async def get_sync_token")
    post_fn_start = source.index("async def generate_sync_token")
    get_fn_body = source[get_fn_start:post_fn_start]
    assert '.select("sync_token")' in get_fn_body
    assert '.update({"sync_token"' not in get_fn_body


def test_generate_sync_token_endpoint_still_exists():
    # Regression guard: the existing mint endpoint must be untouched by this change
    source = _read("app/routes/callers.py")
    assert '@router.post("/{caller_id}/sync-token")' in source
    assert "async def generate_sync_token(caller_id: UUID, tenant_id: str = Depends(get_owner_tenant_id))" in source
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd "/Users/prem/Documents/Aira AI/backend" && venv/bin/python -m pytest tests/test_callers_sync_token_static.py -v`
Expected: `test_get_sync_token_endpoint_exists` FAILS (endpoint doesn't exist yet), `test_generate_sync_token_endpoint_still_exists` PASSES (it already exists).

- [ ] **Step 3: Add the new endpoint**

In `backend/app/routes/callers.py`, immediately before the existing `@router.post("/{caller_id}/sync-token")` block (currently starting at line 542), insert:

```python
@router.get("/{caller_id}/sync-token")
async def get_sync_token(caller_id: UUID, tenant_id: str = Depends(get_owner_tenant_id)):
    db = get_supabase()
    result = (
        db.table("callers")
        .select("sync_token")
        .eq("id", str(caller_id))
        .eq("tenant_id", tenant_id)
        .maybe_single()
        .execute()
    )
    row = result.data if result else None
    if not row:
        raise HTTPException(status_code=404, detail="Caller not found")
    token = row.get("sync_token")
    if not token:
        raise HTTPException(status_code=404, detail="No sync token has been generated for this caller yet")
    return {"sync_token": token}


```

Leave the existing `generate_sync_token` function immediately after it completely unchanged.

- [ ] **Step 4: Run the test again to verify it passes**

Run: `cd "/Users/prem/Documents/Aira AI/backend" && venv/bin/python -m pytest tests/test_callers_sync_token_static.py -v`
Expected: both tests PASS.

- [ ] **Step 5: Run the full backend suite to check for regressions**

Run: `cd "/Users/prem/Documents/Aira AI/backend" && venv/bin/python -m pytest -q`
Expected: same pass count as before this task plus 2 (the two new tests), no new failures. (2 pre-existing unrelated UTC/IST day-boundary failures in `test_analytics_overview.py`/`test_growth_ad_performance.py` are expected and not caused by this change.)

- [ ] **Step 6: Commit**

```bash
cd "/Users/prem/Documents/Aira AI" && git add backend/app/routes/callers.py backend/tests/test_callers_sync_token_static.py && git commit -m "feat(callers): add read-only GET /callers/{id}/sync-token, owner-only"
```

---

### Task 3: Frontend API client — add `getSyncToken`

**Files:**
- Modify: `frontend/lib/api.ts:1181-1184` (the `callers` object, right after `generateSyncToken`)

**Interfaces:**
- Consumes: nothing new (uses existing `apiFetch<T>` helper already used by `generateSyncToken` two lines above)
- Produces: `api.callers.getSyncToken(id: string): Promise<{ sync_token: string }>`

- [ ] **Step 1: Add the method**

In `frontend/lib/api.ts`, immediately after the existing `generateSyncToken` entry (currently lines 1183-1184):

```ts
    generateSyncToken: (id: string) =>
      apiFetch<{ sync_token: string }>(`/api/v1/callers/${id}/sync-token`, { method: "POST" }),
    getSyncToken: (id: string) =>
      apiFetch<{ sync_token: string }>(`/api/v1/callers/${id}/sync-token`, { method: "GET" }),
    remove: (id: string) =>
```

(Note: `remove` already exists two lines below `generateSyncToken` in the current file — this step only adds the new `getSyncToken` line between them, nothing else moves.)

- [ ] **Step 2: Typecheck**

Run: `cd "/Users/prem/Documents/Aira AI/frontend" && npx tsc --noEmit --pretty false`
Expected: no output.

- [ ] **Step 3: Commit**

```bash
cd "/Users/prem/Documents/Aira AI" && git add frontend/lib/api.ts && git commit -m "feat(api): add api.callers.getSyncToken client method"
```

---

### Task 4: Roles page — shared `confirmState` driving one `ConfirmModal`, applied to delete role / delete user / reset password

**Files:**
- Modify: `frontend/app/dashboard/roles/page.tsx`

**Interfaces:**
- Consumes: `ConfirmModal` from `@/components/ConfirmModal` (Task 1)
- Produces: a `confirmState` setter other code in Task 5 will also use:
  ```ts
  type ConfirmState = {
    title: string;
    description: string;
    tone: "danger" | "warning" | "primary";
    confirmLabel?: string;
    onConfirm: () => void;
  };
  const [confirmState, setConfirmState] = useState<ConfirmState | null>(null);
  ```

- [ ] **Step 1: Import ConfirmModal and add confirmState**

In `frontend/app/dashboard/roles/page.tsx`, add to the import block (after the existing `import { api, API_URL, ClientRole, PermissionDef, RbacUser } from "@/lib/api";` line):

```tsx
import { ConfirmModal } from "@/components/ConfirmModal";
```

Add a `ConfirmState` type near the top of the file, right after the existing `type CallingProvider = "telecmi" | "sim_basic";` line:

```tsx
type ConfirmState = {
  title: string;
  description: string;
  tone: "danger" | "warning" | "primary";
  confirmLabel?: string;
  onConfirm: () => void;
};
```

Add the state itself inside `RolesPage()`, right after the existing `const [mintingSyncToken, setMintingSyncToken] = useState<string | null>(null);` line:

```tsx
  const [confirmState, setConfirmState] = useState<ConfirmState | null>(null);
```

- [ ] **Step 2: Rewrite `deleteRole` to go through confirmState instead of `window.confirm`**

Replace the current `deleteRole` function:

```tsx
  async function deleteRole(roleItem: ClientRole) {
    if (!canWrite) return;
    const confirmed = window.confirm(`Delete role "${roleItem.name}"? This only works when no users are assigned to it.`);
    if (!confirmed) return;
    setDeleting(`role:${roleItem.id}`);
    setError(null);
    try {
      await api.rbac.deleteRole(roleItem.id);
      if (editingRoleId === roleItem.id) resetRole();
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete role");
    } finally {
      setDeleting(null);
    }
  }
```

with:

```tsx
  function deleteRole(roleItem: ClientRole) {
    if (!canWrite) return;
    setConfirmState({
      title: "Delete role",
      description: `Delete role "${roleItem.name}"? This only works when no users are assigned to it.`,
      tone: "danger",
      confirmLabel: "Delete",
      onConfirm: () => runDeleteRole(roleItem),
    });
  }

  async function runDeleteRole(roleItem: ClientRole) {
    setDeleting(`role:${roleItem.id}`);
    setError(null);
    try {
      await api.rbac.deleteRole(roleItem.id);
      if (editingRoleId === roleItem.id) resetRole();
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete role");
    } finally {
      setDeleting(null);
      setConfirmState(null);
    }
  }
```

- [ ] **Step 3: Rewrite `deleteUser` the same way**

Replace the current `deleteUser` function:

```tsx
  async function deleteUser(user: RbacUser) {
    if (!canWrite) return;
    const confirmed = window.confirm(`Delete user "${user.full_name || user.email}"? This removes their tenant access and disables their caller profile.`);
    if (!confirmed) return;
    setDeleting(`user:${user.user_id}`);
    setError(null);
    try {
      await api.rbac.deleteUser(user.user_id);
      if (editingUserId === user.user_id) resetUser();
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete user");
    } finally {
      setDeleting(null);
    }
  }
```

with:

```tsx
  function deleteUser(user: RbacUser) {
    if (!canWrite) return;
    setConfirmState({
      title: "Delete user",
      description: `Delete user "${user.full_name || user.email}"? This removes their tenant access and disables their caller profile.`,
      tone: "danger",
      confirmLabel: "Delete",
      onConfirm: () => runDeleteUser(user),
    });
  }

  async function runDeleteUser(user: RbacUser) {
    setDeleting(`user:${user.user_id}`);
    setError(null);
    try {
      await api.rbac.deleteUser(user.user_id);
      if (editingUserId === user.user_id) resetUser();
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete user");
    } finally {
      setDeleting(null);
      setConfirmState(null);
    }
  }
```

- [ ] **Step 4: Add a confirm to `resetPassword` (currently fires with zero confirmation)**

Replace the current `resetPassword` function:

```tsx
  async function resetPassword(user: RbacUser) {
    setSaving(true);
    setError(null);
    try {
      const res = await api.rbac.resetPassword(user.user_id);
      setTemporaryPassword({ label: user.full_name || user.email, value: res.temporary_password });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to reset password");
    } finally {
      setSaving(false);
    }
  }
```

with:

```tsx
  function resetPassword(user: RbacUser) {
    setConfirmState({
      title: "Reset password",
      description: `Issue a new temporary password for "${user.full_name || user.email}"? They'll be required to set a new password on next login.`,
      tone: "warning",
      confirmLabel: "Reset password",
      onConfirm: () => runResetPassword(user),
    });
  }

  async function runResetPassword(user: RbacUser) {
    setSaving(true);
    setError(null);
    try {
      const res = await api.rbac.resetPassword(user.user_id);
      setTemporaryPassword({ label: user.full_name || user.email, value: res.temporary_password });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to reset password");
    } finally {
      setSaving(false);
      setConfirmState(null);
    }
  }
```

- [ ] **Step 5: Render the single `ConfirmModal` instance**

At the very end of the component's JSX, immediately before the final closing `</div>` of the top-level return (i.e. right after the `{tab === "roles" ? (...) : (...)}` block, currently ending at line 887 with `)}`), add:

```tsx
      <ConfirmModal
        open={confirmState !== null}
        onClose={() => setConfirmState(null)}
        onConfirm={() => confirmState?.onConfirm()}
        title={confirmState?.title ?? ""}
        description={confirmState?.description ?? ""}
        tone={confirmState?.tone ?? "primary"}
        confirmLabel={confirmState?.confirmLabel}
        loading={saving || deleting !== null}
      />
```

This goes right after the closing of the `{tab === "roles" ? (` ternary and before the final `</div>` that closes the component's root `<div className="min-w-0 space-y-6">`.

- [ ] **Step 6: Typecheck and lint**

Run: `cd "/Users/prem/Documents/Aira AI/frontend" && npx tsc --noEmit --pretty false`
Expected: no output.

Run: `cd "/Users/prem/Documents/Aira AI/frontend" && npx eslint app/dashboard/roles/page.tsx`
Expected: no output.

- [ ] **Step 7: Commit**

```bash
cd "/Users/prem/Documents/Aira AI" && git add frontend/app/dashboard/roles/page.tsx && git commit -m "feat(roles): replace native window.confirm with styled ConfirmModal, add missing reset-password confirm"
```

---

### Task 5: Roles page — sync-token "View current / Regenerate" dialog

**Files:**
- Modify: `frontend/app/dashboard/roles/page.tsx`

**Interfaces:**
- Consumes: `api.callers.getSyncToken` (Task 3), `confirmState`/`setConfirmState` (Task 4), existing `syncToken`/`setSyncToken`/`showSyncToken`/`setShowSyncToken` state (unchanged), existing `generateSyncToken` mint logic.
- Produces: nothing consumed by later tasks — this is the last task.

- [ ] **Step 1: Add dialog-open and view-loading state**

Right after the existing `const [confirmState, setConfirmState] = useState<ConfirmState | null>(null);` line added in Task 4, add:

```tsx
  const [syncTokenDialogUser, setSyncTokenDialogUser] = useState<RbacUser | null>(null);
  const [viewingSyncToken, setViewingSyncToken] = useState<string | null>(null);
```

- [ ] **Step 2: Rewrite `generateSyncToken` to be called from the dialog's Regenerate action, and add a `viewSyncToken` function**

Replace the current `generateSyncToken` function:

```tsx
  async function generateSyncToken(user: RbacUser) {
    const callerId = user.caller_profile?.id;
    if (!callerId) return;
    const confirmed = window.confirm(
      `Generate a new Aira Sync token for "${user.full_name || user.email}"? This immediately invalidates their current token — their Aira Sync app will stop syncing until you paste in the new one.`,
    );
    if (!confirmed) return;
    setMintingSyncToken(callerId);
    setError(null);
    try {
      const res = await api.callers.generateSyncToken(callerId);
      setShowSyncToken(true);
      setSyncToken({ label: user.full_name || user.email, value: res.sync_token });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to generate sync token");
    } finally {
      setMintingSyncToken(null);
    }
  }
```

with:

```tsx
  function regenerateSyncToken(user: RbacUser) {
    const callerId = user.caller_profile?.id;
    if (!callerId) return;
    setSyncTokenDialogUser(null);
    setConfirmState({
      title: "Regenerate Aira Sync token",
      description: `Generate a new Aira Sync token for "${user.full_name || user.email}"? This immediately invalidates their current token — their Aira Sync app will stop syncing until you paste in the new one.`,
      tone: "danger",
      confirmLabel: "Regenerate",
      onConfirm: () => runRegenerateSyncToken(user, callerId),
    });
  }

  async function runRegenerateSyncToken(user: RbacUser, callerId: string) {
    setMintingSyncToken(callerId);
    setError(null);
    try {
      const res = await api.callers.generateSyncToken(callerId);
      setShowSyncToken(true);
      setSyncToken({ label: user.full_name || user.email, value: res.sync_token });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to generate sync token");
    } finally {
      setMintingSyncToken(null);
      setConfirmState(null);
    }
  }

  async function viewSyncToken(user: RbacUser) {
    const callerId = user.caller_profile?.id;
    if (!callerId) return;
    setViewingSyncToken(callerId);
    setError(null);
    try {
      const res = await api.callers.getSyncToken(callerId);
      setSyncTokenDialogUser(null);
      setShowSyncToken(true);
      setSyncToken({ label: user.full_name || user.email, value: res.sync_token });
    } catch (e) {
      setError(e instanceof Error ? e.message : "No sync token has been generated for this caller yet");
    } finally {
      setViewingSyncToken(null);
    }
  }
```

- [ ] **Step 3: Change the row's phone icon button to open the dialog instead of minting directly**

Replace the current button (inside the `{role === "owner" && callingProvider === "sim_basic" && user.caller_profile && (...)}` block in the users list):

```tsx
                        {role === "owner" && callingProvider === "sim_basic" && user.caller_profile && (
                          <button
                            type="button"
                            className="btn-secondary px-3"
                            onClick={() => generateSyncToken(user)}
                            disabled={mintingSyncToken === user.caller_profile.id}
                            title="Generate Aira Sync token"
                          >
                            {mintingSyncToken === user.caller_profile.id ? <Loader2 size={14} className="animate-spin" /> : <Smartphone size={14} />}
                          </button>
                        )}
```

with:

```tsx
                        {role === "owner" && callingProvider === "sim_basic" && user.caller_profile && (
                          <button
                            type="button"
                            className="btn-secondary px-3"
                            onClick={() => setSyncTokenDialogUser(user)}
                            title="Aira Sync token"
                          >
                            <Smartphone size={14} />
                          </button>
                        )}
```

- [ ] **Step 4: Add the two-choice dialog JSX**

Immediately after the `<ConfirmModal ... />` block added in Task 4 Step 5 (and still before the root `</div>`), add:

```tsx
      {syncTokenDialogUser && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-card bg-white p-6 shadow-xl">
            <div className="mb-4 flex items-start justify-between">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary-muted text-primary">
                  <Smartphone size={18} />
                </div>
                <h3 className="text-lg font-bold text-ink">
                  Aira Sync — {syncTokenDialogUser.full_name || syncTokenDialogUser.email}
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setSyncTokenDialogUser(null)}
                className="text-ink-muted hover:text-ink"
                aria-label="Close"
              >
                <X size={18} />
              </button>
            </div>
            <p className="mb-4 text-sm text-ink-secondary">
              View this caller&apos;s current token, or regenerate it if it was lost — regenerating invalidates the current one immediately.
            </p>
            <div className="flex flex-col gap-2">
              <button
                type="button"
                className="btn-secondary w-full justify-center"
                onClick={() => viewSyncToken(syncTokenDialogUser)}
                disabled={viewingSyncToken === syncTokenDialogUser.caller_profile?.id}
              >
                {viewingSyncToken === syncTokenDialogUser.caller_profile?.id ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  <Eye size={14} />
                )}
                View current token
              </button>
              <button
                type="button"
                className="w-full justify-center rounded-xl border border-danger/30 bg-danger/5 px-4 py-2.5 text-sm font-bold text-danger transition-colors hover:bg-danger/10"
                onClick={() => regenerateSyncToken(syncTokenDialogUser)}
              >
                Regenerate token
              </button>
            </div>
          </div>
        </div>
      )}
```

- [ ] **Step 5: Add the `X` icon import**

In the `lucide-react` import block at the top of the file, add `X` alongside the existing icons (alphabetically, after `Users`):

```tsx
  User,
  UserPlus,
  Users,
  X,
} from "lucide-react";
```

- [ ] **Step 6: Typecheck and lint**

Run: `cd "/Users/prem/Documents/Aira AI/frontend" && npx tsc --noEmit --pretty false`
Expected: no output.

Run: `cd "/Users/prem/Documents/Aira AI/frontend" && npx eslint app/dashboard/roles/page.tsx`
Expected: no output.

- [ ] **Step 7: Manual verification checklist (no browser tool available this session — do this yourself)**

- Refresh the Roles page → Users tab on a SIM Basic tenant, logged in as owner.
- Click the phone icon on a telecaller row → dialog opens with "View current token" and "Regenerate token".
- Click "View current token" on a caller with no token yet minted → error banner shows "No sync token has been generated for this caller yet", dialog closes.
- Mint a token once (via Regenerate), copy it somewhere, close the banner.
- Click phone icon again → "View current token" → same token reappears in the banner, unchanged (confirm this by comparing to what you copied — regenerating would produce a different value).
- Click phone icon → "Regenerate token" → styled `ConfirmModal` (not a browser-native dialog) appears, danger-toned, "Regenerate" button.
- Confirm it → new token banner appears, different value from before.
- Click Delete on a role and a user → styled `ConfirmModal` appears (not browser-native), matches the screenshot comparison from this session.
- Click the key icon (Reset Password) → styled `ConfirmModal` appears (this one previously had zero confirmation) → confirm → temp password banner appears as before.

- [ ] **Step 8: Commit**

```bash
cd "/Users/prem/Documents/Aira AI" && git add frontend/app/dashboard/roles/page.tsx && git commit -m "feat(roles): add non-destructive 'view current sync token' path alongside regenerate"
```
