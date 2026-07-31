"use client";
import { useEffect, useState, useCallback } from "react";
import { ShieldCheck, Users, KeyRound } from "lucide-react";
import { API_URL, getAuthHeaders } from "@/lib/api";
import { StatCard } from "../components/stat-card";
import { SkeletonCard, SkeletonTable } from "../components/skeleton";

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

interface RoleRow {
  id: string;
  name: string;
  slug: string | null;
  is_system_template: boolean;
  is_telecaller: boolean;
  permission_count: number;
}

interface RoleUserRow {
  user_id: string;
  full_name: string | null;
  role: "owner" | "caller";
  role_name: string;
  created_at: string | null;
}

interface RolesData {
  roles: RoleRow[];
  users: RoleUserRow[];
}

export function RolesView({ tenantId }: { tenantId: string }) {
  const [data, setData] = useState<RolesData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    apiFetch<RolesData>(`/api/v1/operator/clients/${tenantId}/roles`)
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, [tenantId]);

  useEffect(() => { load(); }, [load]);

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-4"><SkeletonCard /><SkeletonCard /></div>
        <SkeletonTable rows={4} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 bg-red-50 border border-danger/20 rounded-xl text-sm text-danger">
        {error}
      </div>
    );
  }

  if (!data) return null;

  return (
    <div className="space-y-6">
      <p className="text-xs text-ink-muted">
        Read-only view. Role and user management happens on the client&apos;s own Roles page.
      </p>

      <div className="grid grid-cols-2 gap-4">
        <StatCard icon={<ShieldCheck size={18} />} label="Roles Defined" value={data.roles.length} />
        <StatCard icon={<Users size={18} />} label="Users" value={data.users.length} />
      </div>

      <div className="bg-white rounded-card border border-border overflow-hidden shadow-sm">
        <div className="px-4 py-3 border-b border-border-subtle">
          <p className="text-sm font-medium text-ink">Roles</p>
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-surface-mid text-ink-secondary uppercase text-xs">
              <th className="text-left px-4 py-3 font-medium">Name</th>
              <th className="text-left px-4 py-3 font-medium">Type</th>
              <th className="text-left px-4 py-3 font-medium">Permissions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border-subtle">
            {data.roles.map((r) => (
              <tr key={r.id} className="hover:bg-surface-mid/50 transition-colors">
                <td className="px-4 py-3 font-medium text-ink">{r.name}</td>
                <td className="px-4 py-3">
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                    r.is_system_template ? "bg-primary-muted text-primary" : "bg-surface-mid text-ink-secondary"
                  }`}>
                    {r.is_system_template ? "System" : "Custom"}
                  </span>
                </td>
                <td className="px-4 py-3 text-ink-secondary flex items-center gap-1.5">
                  <KeyRound size={12} /> {r.permission_count}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {data.users.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-ink-muted">
          <Users size={40} className="mb-3 opacity-40" />
          <p className="text-sm">No users</p>
        </div>
      ) : (
        <div className="bg-white rounded-card border border-border overflow-hidden shadow-sm">
          <div className="px-4 py-3 border-b border-border-subtle">
            <p className="text-sm font-medium text-ink">Users</p>
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-surface-mid text-ink-secondary uppercase text-xs">
                <th className="text-left px-4 py-3 font-medium">Name</th>
                <th className="text-left px-4 py-3 font-medium">Assigned Role</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border-subtle">
              {data.users.map((u) => (
                <tr key={u.user_id} className="hover:bg-surface-mid/50 transition-colors">
                  <td className="px-4 py-3 font-medium text-ink">{u.full_name || "—"}</td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                      u.role === "owner" ? "bg-primary-muted text-primary" : "bg-surface-mid text-ink-secondary"
                    }`}>
                      {u.role_name}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
