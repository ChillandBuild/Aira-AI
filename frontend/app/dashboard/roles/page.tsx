"use client";

import { useEffect, useMemo, useState } from "react";
import {
  CheckCircle2,
  Copy,
  KeyRound,
  Loader2,
  Pencil,
  Plus,
  RotateCcw,
  Search,
  ShieldCheck,
  UserPlus,
  Users,
} from "lucide-react";
import { api, ClientRole, PermissionDef, RbacUser } from "@/lib/api";
import { useAuthRole } from "../contexts/AuthRoleContext";
import { cn } from "@/lib/utils";

type Tab = "roles" | "users";
type CallingProvider = "telecmi" | "sim_basic";

type AccessModule = {
  id: string;
  title: string;
  description: string;
  group: string;
  readKeys: string[];
  writeKeys: string[];
};

const ACCESS_MODULES: AccessModule[] = [
  { id: "dashboard", title: "Dashboard", description: "View executive metrics and workspace status.", group: "Overview", readKeys: ["dashboard.view"], writeKeys: [] },
  { id: "conversations", title: "Conversations", description: "Open inbox threads and reply to customers.", group: "Messaging", readKeys: ["conversations.view"], writeKeys: ["conversations.reply"] },
  { id: "segments", title: "Segments", description: "View and update lead segments.", group: "Leads", readKeys: ["leads.view"], writeKeys: ["leads.manage"] },
  { id: "inbound", title: "Inbound Leads", description: "Review inbound enquiries and handoffs.", group: "Leads", readKeys: ["inbound_leads.view"], writeKeys: [] },
  { id: "outbound", title: "Outbound Leads", description: "Prepare outbound lead workflows.", group: "Messaging", readKeys: ["outbound_leads.manage"], writeKeys: ["outbound_leads.manage"] },
  { id: "templates", title: "Templates", description: "Create and sync WhatsApp templates.", group: "Messaging", readKeys: ["templates.manage"], writeKeys: ["templates.manage"] },
  { id: "numbers", title: "Numbers Pool", description: "Manage sender numbers and health.", group: "Messaging", readKeys: ["numbers.manage"], writeKeys: ["numbers.manage"] },
  { id: "knowledge", title: "Knowledge Base", description: "Maintain AI answer sources.", group: "AI", readKeys: ["knowledge.manage"], writeKeys: ["knowledge.manage"] },
  { id: "catalog", title: "Catalog", description: "Maintain product and service items.", group: "AI", readKeys: ["catalog.manage"], writeKeys: ["catalog.manage"] },
  { id: "analytics", title: "Analytics", description: "View campaign, funnel, and performance reports.", group: "Reports", readKeys: ["analytics.view"], writeKeys: [] },
  { id: "subscription", title: "Subscription", description: "Review and update subscription controls.", group: "Admin", readKeys: ["subscription.manage"], writeKeys: ["subscription.manage"] },
  { id: "team", title: "Team", description: "View performance and manage caller operations.", group: "Team", readKeys: ["team.view"], writeKeys: ["team.manage"] },
  { id: "roles", title: "Roles", description: "Create roles and assign user access.", group: "Admin", readKeys: ["roles.manage"], writeKeys: ["roles.manage"] },
  { id: "settings", title: "Settings", description: "Configure workspace settings.", group: "Admin", readKeys: ["settings.manage"], writeKeys: ["settings.manage"] },
  { id: "dialer", title: "Telecalling Dialer", description: "Use the calling cockpit and agent workflow.", group: "Telecalling", readKeys: ["telecalling.dialer"], writeKeys: ["telecalling.dialer"] },
  { id: "upload", title: "Telecalling Upload", description: "Upload call lists and assign batches.", group: "Telecalling", readKeys: ["telecalling.upload"], writeKeys: ["telecalling.upload"] },
  { id: "scheduled", title: "Scheduled Calls", description: "Work callback queues and scheduled follow-ups.", group: "Telecalling", readKeys: ["telecalling.scheduled"], writeKeys: ["telecalling.scheduled"] },
  { id: "notes", title: "Call Notes", description: "Read and write call notes.", group: "Telecalling", readKeys: ["telecalling.notes"], writeKeys: ["telecalling.notes"] },
];

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

function unique(values: string[]) {
  return Array.from(new Set(values));
}

function hasAnyPermission(rolePermissions: string[], keys: string[]) {
  return keys.some((key) => rolePermissions.includes(key));
}

function moduleActiveCount(rolePermissions: string[]) {
  return ACCESS_MODULES.filter((module) =>
    hasAnyPermission(rolePermissions, [...module.readKeys, ...module.writeKeys]),
  ).length;
}

function providerLabel(provider: CallingProvider) {
  return provider === "sim_basic" ? "SIM Basic" : "TeleCMI";
}

export default function RolesPage() {
  const { role, permissions: myPermissions, loading: roleLoading } = useAuthRole();
  const canManage = role === "owner" || myPermissions.includes("roles.manage");
  const [tab, setTab] = useState<Tab>("roles");
  const [roles, setRoles] = useState<ClientRole[]>([]);
  const [users, setUsers] = useState<RbacUser[]>([]);
  const [permissions, setPermissions] = useState<PermissionDef[]>([]);
  const [callingProvider, setCallingProvider] = useState<CallingProvider>("telecmi");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [roleSearch, setRoleSearch] = useState("");
  const [roleDraft, setRoleDraft] = useState(emptyRole);
  const [editingRoleId, setEditingRoleId] = useState<string | null>(null);
  const [userDraft, setUserDraft] = useState(emptyUser);
  const [editingUserId, setEditingUserId] = useState<string | null>(null);
  const [temporaryPassword, setTemporaryPassword] = useState<{ label: string; value: string } | null>(null);

  const catalogKeys = useMemo(() => new Set(permissions.map((permission) => permission.key)), [permissions]);
  const availableModules = useMemo(() => {
    if (catalogKeys.size === 0) return ACCESS_MODULES;
    return ACCESS_MODULES.filter((module) =>
      [...module.readKeys, ...module.writeKeys].some((key) => catalogKeys.has(key)),
    );
  }, [catalogKeys]);

  const roleById = useMemo(() => new Map(roles.map((r) => [r.id, r])), [roles]);
  const selectedRole = roleById.get(userDraft.role_id);
  const selectedRoleIsTelecaller = selectedRole?.slug === "telecaller" || selectedRole?.permissions.includes("telecalling.dialer");
  const editingRole = editingRoleId ? roleById.get(editingRoleId) : null;

  const filteredRoles = useMemo(() => {
    const query = roleSearch.trim().toLowerCase();
    if (!query) return roles;
    return roles.filter((item) => item.name.toLowerCase().includes(query) || (item.slug ?? "").toLowerCase().includes(query));
  }, [roleSearch, roles]);

  async function load() {
    setError(null);
    setLoading(true);
    try {
      const [roleRes, userRes, assignmentRes] = await Promise.all([
        api.rbac.roles(),
        api.rbac.users(),
        api.calls.assignmentMode().catch(() => null),
      ]);
      setRoles(roleRes.data);
      setPermissions(roleRes.permissions);
      setUsers(userRes.data);
      setCallingProvider(assignmentRes?.calling_provider ?? "telecmi");
      setUserDraft((d) => ({
        ...d,
        role_id: d.role_id || roleRes.data.find((r) => r.slug === "telecaller")?.id || roleRes.data[0]?.id || "",
      }));
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

  function setModuleAccess(module: AccessModule, access: "read" | "write", checked: boolean) {
    setRoleDraft((draft) => {
      const current = new Set(draft.permissions);
      const readKeys = module.readKeys.filter((key) => catalogKeys.size === 0 || catalogKeys.has(key));
      const writeKeys = module.writeKeys.filter((key) => catalogKeys.size === 0 || catalogKeys.has(key));

      if (access === "read") {
        if (checked) {
          readKeys.forEach((key) => current.add(key));
        } else {
          [...readKeys, ...writeKeys].forEach((key) => current.delete(key));
        }
      } else if (checked) {
        [...readKeys, ...writeKeys].forEach((key) => current.add(key));
      } else {
        writeKeys.forEach((key) => current.delete(key));
      }

      return { ...draft, permissions: unique(Array.from(current)).sort() };
    });
  }

  function clearModule(module: AccessModule) {
    const keys = new Set([...module.readKeys, ...module.writeKeys]);
    setRoleDraft((draft) => ({ ...draft, permissions: draft.permissions.filter((key) => !keys.has(key)) }));
  }

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
      const payload = {
        ...userDraft,
        phone: selectedRoleIsTelecaller ? userDraft.phone.trim() || null : null,
        telecmi_agent_id: selectedRoleIsTelecaller && callingProvider === "telecmi" ? userDraft.telecmi_agent_id.trim() || null : null,
        telecmi_agent_password: null,
      };
      if (editingUserId) {
        await api.rbac.updateUser(editingUserId, payload);
      } else {
        const created = await api.rbac.createUser(payload);
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
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <div className="mb-3 inline-flex items-center gap-2 rounded-full bg-primary-light px-3 py-1 font-label text-[10px] font-black uppercase tracking-wider text-primary">
            <ShieldCheck size={13} />
            Role & Permission Management
          </div>
          <h1 className="font-display text-2xl font-black text-ink sm:text-3xl">Roles</h1>
          <p className="mt-2 max-w-2xl font-body text-sm leading-6 text-ink-muted">
            Define read and write access for every dashboard area, then assign one role to each team member.
          </p>
        </div>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <div className="rounded-2xl border border-border-subtle bg-white px-4 py-2 font-body text-xs font-semibold text-ink-muted shadow-sm">
            Calling provider: <span className="text-ink">{providerLabel(callingProvider)}</span>
          </div>
          <div className="flex w-full gap-1 rounded-2xl bg-[#e8e3db]/60 p-1 sm:w-fit">
            {(["roles", "users"] as Tab[]).map((item) => (
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
          {tab === "roles" && (
            <button type="button" onClick={resetRole} className="btn-primary justify-center">
              <Plus size={14} /> Add New Role
            </button>
          )}
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

      {tab === "roles" ? (
        <div className="grid gap-5 xl:grid-cols-[380px_minmax(0,1fr)]">
          <aside className="card rounded-3xl p-4">
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-muted" size={16} />
              <input
                className="input pl-9"
                placeholder="Search roles..."
                value={roleSearch}
                onChange={(e) => setRoleSearch(e.target.value)}
              />
            </div>
            <div className="mt-4 space-y-2">
              {filteredRoles.map((item) => {
                const active = editingRoleId === item.id;
                const activeModules = moduleActiveCount(item.permissions);
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => startRole(item)}
                    className={cn(
                      "w-full rounded-2xl border p-4 text-left transition-all",
                      active ? "border-primary/30 bg-primary-light shadow-sm" : "border-border-subtle bg-white hover:border-primary/20 hover:bg-surface-subtle",
                    )}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div className="flex min-w-0 items-center gap-3">
                        <span className={cn("grid h-10 w-10 shrink-0 place-items-center rounded-2xl", active ? "bg-white text-primary" : "bg-surface-subtle text-ink-muted")}>
                          <ShieldCheck size={16} />
                        </span>
                        <div className="min-w-0">
                          <p className="truncate font-body text-sm font-bold text-ink">{item.name}</p>
                          <p className="font-body text-xs text-ink-muted">{activeModules} modules active</p>
                        </div>
                      </div>
                      <span className="rounded-full bg-white px-2 py-1 font-label text-[10px] font-bold text-ink-muted">
                        {item.is_system_template ? "System" : "Custom"}
                      </span>
                    </div>
                  </button>
                );
              })}
            </div>
          </aside>

          <form onSubmit={saveRole} className="card rounded-3xl overflow-hidden p-0">
            <div className="border-b border-border-subtle bg-surface-subtle px-5 py-5">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                <div>
                  <h2 className="font-display text-lg font-black text-ink">
                    Role Details: {roleDraft.name || editingRole?.name || "New Role"}
                  </h2>
                  <p className="mt-1 font-body text-sm text-ink-muted">Configure module-level read and write access. Delete access is intentionally omitted.</p>
                </div>
                {editingRoleId && (
                  <button type="button" onClick={resetRole} className="btn-secondary w-fit text-xs">
                    <Plus size={14} /> New Role
                  </button>
                )}
              </div>
              <div className="mt-5">
                <label className="mb-2 block font-label text-[10px] font-black uppercase tracking-wider text-ink-muted">Role title</label>
                <input
                  className="input bg-white"
                  placeholder="Example: Telecaller"
                  value={roleDraft.name}
                  onChange={(e) => setRoleDraft((d) => ({ ...d, name: e.target.value }))}
                  required
                />
              </div>
            </div>

            <div className="overflow-x-auto p-5">
              <table className="w-full min-w-[760px] border-separate border-spacing-0 overflow-hidden rounded-2xl border border-border-subtle bg-white">
                <thead>
                  <tr className="bg-surface-subtle">
                    <th className="w-[48%] px-4 py-3 text-left font-label text-[10px] font-black uppercase tracking-wider text-ink-muted">Module / Resource</th>
                    <th className="px-4 py-3 text-center font-label text-[10px] font-black uppercase tracking-wider text-ink-muted">Read</th>
                    <th className="px-4 py-3 text-center font-label text-[10px] font-black uppercase tracking-wider text-ink-muted">Write</th>
                    <th className="px-4 py-3 text-right font-label text-[10px] font-black uppercase tracking-wider text-ink-muted">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {availableModules.map((module) => {
                    const readChecked = hasAnyPermission(roleDraft.permissions, [...module.readKeys, ...module.writeKeys]);
                    const writeChecked = hasAnyPermission(roleDraft.permissions, module.writeKeys);
                    const writeAvailable = module.writeKeys.length > 0;
                    return (
                      <tr key={module.id} className="border-t border-border-subtle">
                        <td className="border-t border-border-subtle px-4 py-4">
                          <p className="font-body text-sm font-bold text-ink">{module.title}</p>
                          <p className="mt-1 font-body text-xs text-ink-muted">{module.description}</p>
                        </td>
                        <td className="border-t border-border-subtle px-4 py-4 text-center">
                          <input
                            type="checkbox"
                            checked={readChecked}
                            onChange={(e) => setModuleAccess(module, "read", e.target.checked)}
                            className="h-4 w-4 rounded border-border-subtle accent-primary"
                            aria-label={`${module.title} read access`}
                          />
                        </td>
                        <td className="border-t border-border-subtle px-4 py-4 text-center">
                          <input
                            type="checkbox"
                            checked={writeChecked}
                            disabled={!writeAvailable}
                            onChange={(e) => setModuleAccess(module, "write", e.target.checked)}
                            className="h-4 w-4 rounded border-border-subtle accent-primary disabled:opacity-30"
                            aria-label={`${module.title} write access`}
                          />
                        </td>
                        <td className="border-t border-border-subtle px-4 py-4 text-right">
                          <button
                            type="button"
                            onClick={() => clearModule(module)}
                            className="inline-flex items-center gap-1 rounded-xl px-3 py-1.5 font-label text-xs font-bold text-ink-muted hover:bg-surface-subtle hover:text-ink"
                          >
                            <RotateCcw size={12} /> Clear
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <div className="flex flex-col gap-3 border-t border-border-subtle px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
              <p className="font-body text-xs text-ink-muted">{moduleActiveCount(roleDraft.permissions)} modules selected for this role.</p>
              <button type="submit" disabled={saving} className="btn-primary justify-center">
                {saving ? <Loader2 size={14} className="animate-spin" /> : <CheckCircle2 size={14} />}
                {editingRoleId ? "Save Role" : "Create Role"}
              </button>
            </div>
          </form>
        </div>
      ) : (
        <div className="grid gap-5 xl:grid-cols-[0.9fr_1.1fr]">
          <form onSubmit={saveUser} className="card rounded-3xl space-y-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h2 className="font-display text-base font-bold text-ink">{editingUserId ? "Edit User" : "Create User"}</h2>
                <p className="mt-1 font-body text-xs text-ink-muted">Assign one role. Telecaller fields adapt to {providerLabel(callingProvider)}.</p>
              </div>
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
                <div className="grid gap-3 rounded-2xl border border-primary/15 bg-primary-light/50 p-3">
                  <div className="flex items-center gap-2 font-label text-[10px] font-black uppercase tracking-wider text-primary">
                    <Users size={13} /> Telecaller setup - {providerLabel(callingProvider)}
                  </div>
                  <input className="input bg-white" placeholder="Phone number" value={userDraft.phone} onChange={(e) => setUserDraft((d) => ({ ...d, phone: e.target.value }))} />
                  {callingProvider === "telecmi" && (
                    <input className="input bg-white" placeholder="TeleCMI agent ID" value={userDraft.telecmi_agent_id} onChange={(e) => setUserDraft((d) => ({ ...d, telecmi_agent_id: e.target.value }))} />
                  )}
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
                      {user.caller_profile && <span className="rounded-full bg-emerald-50 px-2 py-0.5 font-label text-[10px] font-bold text-emerald-700">Team visible</span>}
                    </div>
                  </div>
                  {user.role !== "owner" && (
                    <div className="flex gap-2">
                      <button type="button" className="btn-secondary px-3" onClick={() => startUser(user)}><Pencil size={14} /></button>
                      <button type="button" className="btn-secondary px-3" onClick={() => resetPassword(user)}><KeyRound size={14} /></button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
