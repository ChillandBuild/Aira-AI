"use client";

import { useEffect, useMemo, useState } from "react";
import {
  CheckCircle2,
  Copy,
  KeyRound,
  Loader2,
  Pencil,
  Plus,
  ShieldCheck,
  Trash2,
  UserPlus,
} from "lucide-react";
import { api, ClientRole, PermissionDef, RbacUser } from "@/lib/api";
import { useAuthRole } from "../contexts/AuthRoleContext";
import { cn } from "@/lib/utils";

type Tab = "users" | "roles";

const emptyRole = { name: "", permissions: [] as string[] };
const emptyUser = {
  full_name: "",
  email: "",
  role_id: "",
  temporary_password: "",
  phone: "",
  telecmi_agent_id: "",
  telecmi_agent_password: "",
};

function makePassword() {
  const chars = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789";
  const body = Array.from({ length: 13 }, () => chars[Math.floor(Math.random() * chars.length)]).join("");
  return `${body}9!`;
}

export default function RolesPage() {
  const { role, permissions: myPermissions, loading: roleLoading } = useAuthRole();
  const canManage = role === "owner" || myPermissions.includes("roles.manage");
  const [tab, setTab] = useState<Tab>("users");
  const [roles, setRoles] = useState<ClientRole[]>([]);
  const [users, setUsers] = useState<RbacUser[]>([]);
  const [permissions, setPermissions] = useState<PermissionDef[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [roleDraft, setRoleDraft] = useState(emptyRole);
  const [editingRoleId, setEditingRoleId] = useState<string | null>(null);
  const [userDraft, setUserDraft] = useState(emptyUser);
  const [editingUserId, setEditingUserId] = useState<string | null>(null);
  const [temporaryPassword, setTemporaryPassword] = useState<{ label: string; value: string } | null>(null);

  const permissionGroups = useMemo(() => {
    return permissions.reduce<Record<string, PermissionDef[]>>((acc, permission) => {
      acc[permission.group] = [...(acc[permission.group] ?? []), permission];
      return acc;
    }, {});
  }, [permissions]);

  const roleById = useMemo(() => new Map(roles.map((r) => [r.id, r])), [roles]);
  const selectedRole = roleById.get(userDraft.role_id);
  const selectedRoleIsTelecaller = selectedRole?.slug === "telecaller" || selectedRole?.permissions.includes("telecalling.dialer");

  async function load() {
    setError(null);
    setLoading(true);
    try {
      const [roleRes, userRes] = await Promise.all([api.rbac.roles(), api.rbac.users()]);
      setRoles(roleRes.data);
      setPermissions(roleRes.permissions);
      setUsers(userRes.data);
      setUserDraft((d) => ({ ...d, role_id: d.role_id || roleRes.data.find((r) => r.slug === "telecaller")?.id || roleRes.data[0]?.id || "" }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load roles");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!roleLoading && canManage) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [roleLoading, canManage]);

  function startRole(role: ClientRole) {
    setEditingRoleId(role.id);
    setRoleDraft({
      name: role.name,
      permissions: role.permissions,
    });
    setTab("roles");
  }

  function resetRole() {
    setEditingRoleId(null);
    setRoleDraft(emptyRole);
  }

  function startUser(user: RbacUser) {
    setEditingUserId(user.user_id);
    setUserDraft({
      ...emptyUser,
      full_name: user.full_name,
      email: user.email,
      role_id: user.role_id || roles.find((r) => r.slug === "telecaller")?.id || "",
      phone: user.caller_profile?.phone ?? "",
      telecmi_agent_id: user.caller_profile?.telecmi_agent_id ?? "",
    });
    setTab("users");
  }

  function resetUser() {
    setEditingUserId(null);
    setUserDraft({
      ...emptyUser,
      role_id: roles.find((r) => r.slug === "telecaller")?.id || roles[0]?.id || "",
      temporary_password: makePassword(),
    });
  }

  useEffect(() => {
    if (!userDraft.temporary_password && !editingUserId) {
      setUserDraft((d) => ({ ...d, temporary_password: makePassword() }));
    }
  }, [editingUserId, userDraft.temporary_password]);

  async function saveRole(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      if (editingRoleId) {
        await api.rbac.updateRole(editingRoleId, roleDraft);
      } else {
        await api.rbac.createRole(roleDraft);
      }
      resetRole();
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save role");
    } finally {
      setSaving(false);
    }
  }

  async function saveUser(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      if (editingUserId) {
        await api.rbac.updateUser(editingUserId, userDraft);
      } else {
        const created = await api.rbac.createUser(userDraft);
        setTemporaryPassword({ label: userDraft.full_name || userDraft.email, value: created.temporary_password });
      }
      resetUser();
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save user");
    } finally {
      setSaving(false);
    }
  }

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

  if (roleLoading || loading) {
    return <div className="flex min-h-[400px] items-center justify-center"><Loader2 size={24} className="animate-spin text-primary" /></div>;
  }

  if (!canManage) {
    return <div className="py-20 text-center"><p className="font-body text-sm text-ink-muted">Only admins with role management access can open this page.</p></div>;
  }

  return (
    <div className="min-w-0 space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="mb-3 inline-flex items-center gap-2 rounded-full bg-primary-light px-3 py-1 font-label text-[10px] font-black uppercase tracking-wider text-primary">
            <ShieldCheck size={13} />
            Client-specific RBAC
          </div>
          <h1 className="font-display text-2xl font-black text-ink sm:text-3xl">Roles</h1>
          <p className="mt-2 max-w-2xl font-body text-sm leading-6 text-ink-muted">
            Create users, assign exactly one role, and choose which dashboard areas each role can access.
          </p>
        </div>
        <div className="flex w-full gap-1 rounded-2xl bg-[#e8e3db]/60 p-1 sm:w-fit">
          {(["users", "roles"] as Tab[]).map((item) => (
            <button
              key={item}
              type="button"
              onClick={() => setTab(item)}
              className={cn(
                "flex-1 rounded-xl px-4 py-2.5 font-label text-xs font-bold capitalize transition-all sm:flex-none",
                tab === item ? "bg-white text-primary shadow-sm" : "text-[#78716c] hover:text-[#292524]",
              )}
            >
              {item}
            </button>
          ))}
        </div>
      </div>

      {error && <div className="rounded-2xl border border-red-100 bg-red-50 px-4 py-3 font-body text-sm text-red-700">{error}</div>}

      {temporaryPassword && (
        <div className="flex flex-col gap-3 rounded-3xl border border-emerald-200 bg-emerald-50 p-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="font-label text-[10px] font-black uppercase tracking-wider text-emerald-700">Temporary password for {temporaryPassword.label}</p>
            <p className="mt-1 font-mono text-sm font-bold text-ink">{temporaryPassword.value}</p>
          </div>
          <button
            type="button"
            className="btn-secondary justify-center"
            onClick={() => navigator.clipboard?.writeText(temporaryPassword.value)}
          >
            <Copy size={14} /> Copy
          </button>
        </div>
      )}

      {tab === "users" ? (
        <div className="grid gap-5 xl:grid-cols-[0.9fr_1.1fr]">
          <form onSubmit={saveUser} className="card rounded-3xl space-y-4">
            <div className="flex items-center justify-between gap-3">
              <h2 className="font-display text-base font-bold text-ink">{editingUserId ? "Edit User" : "Create User"}</h2>
              {editingUserId && <button type="button" onClick={resetUser} className="btn-secondary text-xs">New</button>}
            </div>
            <div className="grid gap-3">
              <input className="input" placeholder="Full name" value={userDraft.full_name} onChange={(e) => setUserDraft((d) => ({ ...d, full_name: e.target.value }))} required />
              <input className="input" placeholder="Email" type="email" value={userDraft.email} onChange={(e) => setUserDraft((d) => ({ ...d, email: e.target.value }))} disabled={!!editingUserId} required />
              <select className="input" value={userDraft.role_id} onChange={(e) => setUserDraft((d) => ({ ...d, role_id: e.target.value }))} required>
                {roles.map((role) => <option key={role.id} value={role.id}>{role.name}</option>)}
              </select>
              {!editingUserId && (
                <div className="flex gap-2">
                  <input className="input flex-1 font-mono" placeholder="Temporary password" value={userDraft.temporary_password} onChange={(e) => setUserDraft((d) => ({ ...d, temporary_password: e.target.value }))} required />
                  <button type="button" className="btn-secondary" onClick={() => setUserDraft((d) => ({ ...d, temporary_password: makePassword() }))}>
                    <KeyRound size={14} />
                  </button>
                </div>
              )}
              {selectedRoleIsTelecaller && (
                <div className="grid gap-3 rounded-2xl border border-border-subtle bg-surface-subtle p-3">
                  <input className="input" placeholder="Phone for SIM calling" value={userDraft.phone} onChange={(e) => setUserDraft((d) => ({ ...d, phone: e.target.value }))} />
                  <input className="input" placeholder="TeleCMI agent ID" value={userDraft.telecmi_agent_id} onChange={(e) => setUserDraft((d) => ({ ...d, telecmi_agent_id: e.target.value }))} />
                  <input className="input" placeholder={editingUserId ? "New TeleCMI password (optional)" : "TeleCMI agent password"} type="password" value={userDraft.telecmi_agent_password} onChange={(e) => setUserDraft((d) => ({ ...d, telecmi_agent_password: e.target.value }))} />
                </div>
              )}
            </div>
            <button type="submit" disabled={saving} className="btn-primary w-full justify-center">
              {saving ? <Loader2 size={14} className="animate-spin" /> : editingUserId ? <CheckCircle2 size={14} /> : <UserPlus size={14} />}
              {editingUserId ? "Save User" : "Create User"}
            </button>
          </form>

          <div className="card rounded-3xl overflow-hidden">
            <h2 className="mb-4 font-display text-base font-bold text-ink">Users</h2>
            <div className="divide-y divide-border-subtle">
              {users.map((user) => (
                <div key={user.user_id} className="flex flex-col gap-3 py-3 sm:flex-row sm:items-center sm:justify-between">
                  <div className="min-w-0">
                    <p className="truncate font-body text-sm font-bold text-ink">{user.full_name || user.email}</p>
                    <p className="truncate font-body text-xs text-ink-muted">{user.email}</p>
                    <div className="mt-1 flex flex-wrap gap-2">
                      <span className="rounded-full bg-primary-light px-2 py-0.5 font-label text-[10px] font-bold text-primary">{user.role_name}</span>
                      {user.force_password_reset && <span className="rounded-full bg-amber-100 px-2 py-0.5 font-label text-[10px] font-bold text-amber-700">Reset required</span>}
                    </div>
                  </div>
                  {user.role !== "owner" && (
                    <div className="flex gap-2">
                      <button type="button" className="btn-secondary px-3" onClick={() => startUser(user)}><Pencil size={14} /></button>
                      <button type="button" className="btn-secondary px-3" onClick={() => resetPassword(user)}><KeyRound size={14} /></button>
                      <button type="button" className="btn-secondary px-3 text-red-600" onClick={() => api.rbac.deleteUser(user.user_id).then(load).catch((e) => setError(e.message))}><Trash2 size={14} /></button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      ) : (
        <div className="grid gap-5 xl:grid-cols-[0.9fr_1.1fr]">
          <form onSubmit={saveRole} className="card rounded-3xl space-y-4">
            <div className="flex items-center justify-between gap-3">
              <h2 className="font-display text-base font-bold text-ink">{editingRoleId ? "Edit Role" : "Create Role"}</h2>
              {editingRoleId && <button type="button" onClick={resetRole} className="btn-secondary text-xs">New</button>}
            </div>
            <input className="input" placeholder="Role name" value={roleDraft.name} onChange={(e) => setRoleDraft((d) => ({ ...d, name: e.target.value }))} required />
            <div className="space-y-4">
              {Object.entries(permissionGroups).map(([group, items]) => (
                <div key={group}>
                  <p className="mb-2 font-label text-[10px] font-black uppercase tracking-wider text-ink-muted">{group}</p>
                  <div className="grid gap-2 sm:grid-cols-2">
                    {items.map((permission) => (
                      <label key={permission.key} className="flex cursor-pointer items-center gap-2 rounded-xl border border-border-subtle bg-white px-3 py-2 font-body text-xs font-semibold text-ink">
                        <input
                          type="checkbox"
                          checked={roleDraft.permissions.includes(permission.key)}
                          onChange={(e) => {
                            setRoleDraft((d) => ({
                              ...d,
                              permissions: e.target.checked
                                ? [...d.permissions, permission.key]
                                : d.permissions.filter((p) => p !== permission.key),
                            }));
                          }}
                        />
                        {permission.label}
                      </label>
                    ))}
                  </div>
                </div>
              ))}
            </div>
            <button type="submit" disabled={saving} className="btn-primary w-full justify-center">
              {saving ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
              {editingRoleId ? "Save Role" : "Create Role"}
            </button>
          </form>

          <div className="grid gap-4">
            {roles.map((role) => (
              <div key={role.id} className="card rounded-3xl">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h2 className="font-display text-base font-bold text-ink">{role.name}</h2>
                    {role.slug === "telecaller" && <p className="mt-2 font-label text-[10px] font-black uppercase tracking-wider text-primary">Default telecaller template</p>}
                  </div>
                  <div className="flex gap-2">
                    <button type="button" className="btn-secondary px-3" onClick={() => startRole(role)}><Pencil size={14} /></button>
                    {role.slug !== "telecaller" && <button type="button" className="btn-secondary px-3 text-red-600" onClick={() => api.rbac.deleteRole(role.id).then(load).catch((e) => setError(e.message))}><Trash2 size={14} /></button>}
                  </div>
                </div>
                <div className="mt-4 flex flex-wrap gap-2">
                  {role.permissions.length === 0 ? (
                    <span className="font-body text-xs text-ink-muted">No permissions selected</span>
                  ) : role.permissions.map((permission) => (
                    <span key={permission} className="rounded-full bg-primary-light px-3 py-1 font-label text-[11px] font-bold text-primary">{permission}</span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
