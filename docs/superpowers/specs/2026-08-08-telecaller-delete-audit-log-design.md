# Telecaller hard-delete + tenant audit log

Date: 2026-08-08

## Problem

Deleting a telecaller from Roles → Users (`DELETE /api/v1/rbac/users/{user_id}`) soft-deactivates
their `callers` row instead of removing it, leaving orphaned rows behind once the auth account is
gone (found via 5 stale test rows: yuvaraj, kalai, theee, abi, hgyuu — all `active:false`, zero
leads, zero calls, auth account already deleted). There's also no audit trail for who deleted a
team member, when, or why — `record_audit_event`/`app_audit_logs` already exist and are used
elsewhere (`app_settings.py`, `operator.py`) but nothing in `rbac.py` writes to it, and there's no
tenant-facing way to read it (only the operator console can).

## Decisions (confirmed with user)

1. **Delete behavior**: hard-delete when safe, not unconditional. `callers.id` is referenced by
   `call_logs.caller_id`, `leads.assigned_to`, `lead_notes.caller_id`,
   `follow_up_jobs.scheduled_by_caller_id` — all `ON DELETE SET NULL`, safe to hard-delete through.
   `chat_handovers.assigned_to` is `NO ACTION` (no cascade) — null it out first, then delete.
   History rows survive; attribution to the deleted caller's name is lost (expected trade-off).
2. **Audit scope**: team membership changes (user create/update/delete/reset-password) *and*
   role/permission changes (role create/update/delete). Not broader tenant-wide settings audit.
3. **Orphan cleanup**: hard-delete the 5 existing stale rows as part of this work.

## Changes

### Backend — `backend/app/routes/rbac.py`

- `delete_user`: before deleting, `UPDATE chat_handovers SET assigned_to = NULL WHERE assigned_to = :user_caller_id`,
  then hard `DELETE FROM callers WHERE id = :caller_id` (replacing the `active=false` update). Keep
  existing `tenant_users` delete + `auth.admin.delete_user`. Add `record_audit_event` call.
- Add `record_audit_event` calls to: `create_user`, `update_user`, `reset_user_password`,
  `create_role`, `update_role`, `delete_role` (7 total including `delete_user`).
- New endpoint `GET /api/v1/rbac/audit-log`, gated by existing `require_roles_read`, tenant-scoped
  (`ctx["tenant_id"]`), paginated (`page`/`limit`), optional `date_from`/`date_to`. Mirrors
  `operator.py`'s `/clients/{tenant_id}/audit-logs` query shape (same `app_audit_logs` columns),
  swapping the operator-admin auth for the tenant `roles.view`/`roles.manage` gate.

### Frontend

- `frontend/lib/api.ts`: add `api.rbac.auditLog(params)` calling the new endpoint.
- `frontend/components/AppHeader.tsx`: extend the `["roles", "users"]` segmented control
  (AppHeader.tsx:466-489) to `["roles", "users", "audit"]`, routing to `?tab=audit`.
- `frontend/app/dashboard/roles/page.tsx`: extend `Tab` to include `"audit"`, add an audit log
  panel (table: time, actor, action, target, details) modeled on
  `frontend/app/operator/(console)/audit-log/page.tsx`, minus the tenant-name column and operator
  auth — paginated, simple date-range filter optional (match existing page's `ChevronLeft`/`ChevronRight` pager).

### Data migration (Supabase, one-off)

Hard-delete the 5 orphaned `callers` rows (`yuvaraj`, `kalai`, `theee`, `abi`, `hgyuu` under tenant
`eba3ed94-277c-430f-a992-19bbe855e2f4`) — confirmed zero `leads.assigned_to`, zero `call_logs`, no
`chat_handovers` reference, and no `tenant_users` row (already orphaned pre-fix).

## Explicitly out of scope

Three other dead/parallel delete paths exist and are untouched: `DELETE /api/v1/team/{user_id}`
(team.py, unused by any frontend page), `DELETE /api/v1/callers/{caller_id}` (callers.py:535,
unused), and the operator console's own `DELETE /operator/clients/{tenant_id}/team/{caller_id}`.
Unifying them is a separate future cleanup.

## Testing

- Backend: a pytest covering `delete_user` — create a caller with an open `chat_handovers` row
  referencing it, delete, assert the caller row is gone and the handover's `assigned_to` is null.
  Assert an `app_audit_logs` row is written for each of the 7 call sites.
- Frontend: manual check — delete a test telecaller from Roles → Users, confirm it disappears,
  confirm the new Audit tab shows the deletion event.
