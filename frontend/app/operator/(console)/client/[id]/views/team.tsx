"use client";
import { useEffect, useState, useCallback } from "react";
import { Users, Crown, UserCheck, Mail, User, Clock, Trash2 } from "lucide-react";
import { API_URL, getAuthHeaders } from "@/lib/api";
import { StatCard } from "../components/stat-card";
import { SkeletonCard, SkeletonTable } from "../components/skeleton";
import { ConfirmModal } from "../../../components/confirm-modal";

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

interface CallerRow {
  id: string;
  name: string;
  role: string;
  active: boolean;
  overall_score: number | null;
  shift_start_hour: number | null;
  shift_end_hour: number | null;
}

interface TeamData {
  owner: { user_id: string | null; email: string | null; created_at: string | null };
  callers: CallerRow[];
}

function formatShift(start: number | null, end: number | null): string {
  if (start == null || end == null) return "—";
  const fmt = (h: number) => `${h.toString().padStart(2, "0")}:00`;
  return `${fmt(start)} – ${fmt(end)}`;
}

export function TeamView({ tenantId }: { tenantId: string }) {
  const [data, setData] = useState<TeamData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<CallerRow | null>(null);
  const [deleting, setDeleting] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    apiFetch<TeamData>(`/api/v1/operator/clients/${tenantId}/team`)
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, [tenantId]);

  useEffect(() => { load(); }, [load]);

  async function handleDeleteMember() {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await apiFetch(`/api/v1/operator/clients/${tenantId}/team/${deleteTarget.id}`, { method: "DELETE" });
      setData(prev => prev ? { ...prev, callers: prev.callers.filter(c => c.id !== deleteTarget.id) } : prev);
      setDeleteTarget(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete member");
    } finally {
      setDeleting(false);
    }
  }

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
      {/* Owner Card */}
      <div className="bg-white rounded-card border border-border p-5 shadow-sm">
        <div className="flex items-center gap-3 mb-3">
          <div className="w-10 h-10 rounded-full bg-primary-muted flex items-center justify-center">
            <Crown size={18} className="text-primary" />
          </div>
          <p className="text-sm font-medium text-ink">Account Owner</p>
        </div>
        <div className="space-y-2">
          {data.owner.email && (
            <div className="flex items-center gap-2 text-sm">
              <Mail size={14} className="text-ink-muted" />
              <span className="text-ink-secondary">Email:</span>
              <span className="text-ink">{data.owner.email}</span>
            </div>
          )}
          {data.owner.user_id && (
            <div className="flex items-center gap-2 text-sm">
              <User size={14} className="text-ink-muted" />
              <span className="text-ink-secondary">User ID:</span>
              <span className="text-ink font-mono text-xs">{data.owner.user_id}</span>
            </div>
          )}
          {data.owner.created_at && (
            <div className="flex items-center gap-2 text-sm">
              <Clock size={14} className="text-ink-muted" />
              <span className="text-ink-secondary">Since:</span>
              <span className="text-ink">{new Date(data.owner.created_at).toLocaleDateString("en-IN")}</span>
            </div>
          )}
          {!data.owner.email && !data.owner.user_id && (
            <p className="text-xs text-ink-muted">Not set</p>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <StatCard icon={<Users size={18} />} label="Total Members" value={data.callers.length} />
        <StatCard icon={<UserCheck size={18} />} label="Active Callers" value={data.callers.filter(c => c.active).length} />
      </div>

      {data.callers.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-ink-muted">
          <Users size={40} className="mb-3 opacity-40" />
          <p className="text-sm">No team members</p>
        </div>
      ) : (
        <div className="bg-white rounded-card border border-border overflow-hidden shadow-sm">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-surface-mid text-ink-secondary uppercase text-xs">
                <th className="text-left px-4 py-3 font-medium">Name</th>
                <th className="text-left px-4 py-3 font-medium">Role</th>
                <th className="text-left px-4 py-3 font-medium">Status</th>
                <th className="text-left px-4 py-3 font-medium">Score</th>
                <th className="text-left px-4 py-3 font-medium">Shift Hours</th>
                <th className="text-left px-4 py-3 font-medium w-12"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border-subtle">
              {data.callers.map((c) => (
                <tr key={c.id} className="hover:bg-surface-mid/50 transition-colors">
                  <td className="px-4 py-3 font-medium text-ink">{c.name}</td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                      c.role === "owner" ? "bg-primary-muted text-primary" : "bg-surface-mid text-ink-secondary"
                    }`}>
                      {c.role}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1.5">
                      <span className={`w-2 h-2 rounded-full ${c.active ? "bg-success" : "bg-ink-muted/40"}`} />
                      <span className="text-xs text-ink-secondary">{c.active ? "Active" : "Inactive"}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-ink">{c.overall_score != null ? c.overall_score.toFixed(1) : "—"}</td>
                  <td className="px-4 py-3 text-ink-secondary text-xs">{formatShift(c.shift_start_hour, c.shift_end_hour)}</td>
                  <td className="px-4 py-3">
                    {c.role !== "owner" && (
                      <button
                        onClick={() => setDeleteTarget(c)}
                        className="p-1.5 rounded-lg hover:bg-red-50 text-ink-muted hover:text-danger transition-colors"
                        title={`Delete ${c.name}`}
                      >
                        <Trash2 size={14} />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <ConfirmModal
        open={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleDeleteMember}
        title="Delete team member?"
        description={`Delete "${deleteTarget?.name ?? ""}" from this client's team? This permanently removes the caller record.`}
        tone="danger"
        confirmLabel="Delete"
        loadingLabel="Deleting…"
        loading={deleting}
      />
    </div>
  );
}
