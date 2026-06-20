"use client";
import { useEffect, useState, useCallback } from "react";
import { Key, PowerOff, Power, Trash2, Mail, User, Clock } from "lucide-react";
import { API_URL, getAuthHeaders } from "@/lib/api";
import { ConfirmDialog } from "../components/confirm-dialog";
import { SkeletonTable } from "../components/skeleton";
import type { OverviewData } from "../types";

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

interface TeamMember {
  id: string;
  name: string;
  role: string;
  is_active: boolean;
  score: number | null;
  shift_start_hour: number | null;
  shift_end_hour: number | null;
}

export function ManagementView({
  tenantId,
  overview,
  onReload,
  setError,
}: {
  tenantId: string;
  overview: OverviewData | null;
  onReload: () => void;
  setError: (e: string | null) => void;
}) {
  const [team, setTeam] = useState<TeamMember[]>([]);
  const [teamLoading, setTeamLoading] = useState(true);
  const [tempPassword, setTempPassword] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [wipeDialogOpen, setWipeDialogOpen] = useState(false);
  const [wipeLoading, setWipeLoading] = useState(false);

  const loadTeam = useCallback(async () => {
    setTeamLoading(true);
    try {
      const data = await apiFetch<{ members: TeamMember[] }>(`/api/v1/operator/clients/${tenantId}/team`);
      setTeam(data.members);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load team");
    } finally {
      setTeamLoading(false);
    }
  }, [tenantId, setError]);

  useEffect(() => { loadTeam(); }, [loadTeam]);

  async function handleResetPassword() {
    setActionLoading("reset");
    try {
      const res = await apiFetch<{ temp_password: string }>(`/api/v1/operator/clients/${tenantId}/reset-password`, {
        method: "POST",
      });
      setTempPassword(res.temp_password);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to reset password");
    } finally {
      setActionLoading(null);
    }
  }

  async function handleToggleStatus() {
    if (!overview) return;
    const newStatus = overview.tenant.status === "active" ? "suspended" : "active";
    setActionLoading("status");
    try {
      await apiFetch(`/api/v1/operator/clients/${tenantId}/status`, {
        method: "PATCH",
        body: JSON.stringify({ status: newStatus }),
      });
      onReload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update status");
    } finally {
      setActionLoading(null);
    }
  }

  async function handleWipeLeads() {
    setWipeLoading(true);
    try {
      await apiFetch(`/api/v1/operator/clients/${tenantId}/wipe-leads`, {
        method: "POST",
      });
      setWipeDialogOpen(false);
      onReload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to wipe leads");
    } finally {
      setWipeLoading(false);
    }
  }

  const isActive = overview?.tenant.status === "active";

  return (
    <div className="space-y-6">
      {/* Action Cards */}
      <div>
        <h3 className="text-sm font-semibold text-ink mb-3">Actions</h3>
        <div className="grid grid-cols-3 gap-4">
          {/* Reset Password */}
          <div className="bg-white rounded-card border border-border p-4 shadow-sm hover:shadow-card transition-all">
            <button
              onClick={handleResetPassword}
              disabled={actionLoading === "reset"}
              className="flex items-center gap-3 w-full text-left disabled:opacity-50"
            >
              <div className="w-10 h-10 rounded-xl bg-primary-light flex items-center justify-center">
                <Key size={18} className="text-primary" />
              </div>
              <div>
                <p className="text-sm font-medium text-ink">Reset Owner Password</p>
                <p className="text-xs text-ink-muted">Generate a temporary password</p>
              </div>
            </button>
          </div>

          {/* Suspend / Activate */}
          <div className="bg-white rounded-card border border-border p-4 shadow-sm hover:shadow-card transition-all">
            <button
              onClick={handleToggleStatus}
              disabled={actionLoading === "status"}
              className="flex items-center gap-3 w-full text-left disabled:opacity-50"
            >
              <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${
                isActive ? "bg-warning/10" : "bg-success/10"
              }`}>
                {isActive
                  ? <PowerOff size={18} className="text-warning" />
                  : <Power size={18} className="text-success" />
                }
              </div>
              <div>
                <p className="text-sm font-medium text-ink">
                  {isActive ? "Suspend Client" : "Activate Client"}
                </p>
                <p className="text-xs text-ink-muted">
                  {isActive ? "Temporarily disable all services" : "Re-enable all services"}
                </p>
              </div>
            </button>
          </div>

          {/* Wipe Leads */}
          <div className="bg-white rounded-card border border-border p-4 shadow-sm hover:shadow-card transition-all">
            <button
              onClick={() => setWipeDialogOpen(true)}
              className="flex items-center gap-3 w-full text-left"
            >
              <div className="w-10 h-10 rounded-xl bg-danger/5 flex items-center justify-center">
                <Trash2 size={18} className="text-danger" />
              </div>
              <div>
                <p className="text-sm font-medium text-ink">Wipe All Leads</p>
                <p className="text-xs text-ink-muted">Permanently delete all lead data</p>
              </div>
            </button>
          </div>
        </div>
      </div>

      {/* Temp Password */}
      {tempPassword && (
        <div className="bg-success/5 border border-success/20 rounded-xl p-4">
          <p className="text-sm text-ink mb-1">Temporary password generated:</p>
          <code className="text-sm font-mono font-bold text-success bg-success/10 px-3 py-1.5 rounded-lg inline-block">
            {tempPassword}
          </code>
          <p className="text-xs text-ink-muted mt-2">Share this securely with the client. It must be changed on first login.</p>
        </div>
      )}

      {/* Owner Info */}
      {overview && (
        <div className="bg-white rounded-card border border-border p-5 shadow-sm">
          <h3 className="text-sm font-semibold text-ink mb-3">Owner Information</h3>
          <div className="space-y-2">
            {overview.owner?.email && (
              <div className="flex items-center gap-2 text-sm">
                <Mail size={14} className="text-ink-muted" />
                <span className="text-ink-secondary">Email:</span>
                <span className="text-ink">{overview.owner.email}</span>
              </div>
            )}
            {overview.owner?.user_id && (
              <div className="flex items-center gap-2 text-sm">
                <User size={14} className="text-ink-muted" />
                <span className="text-ink-secondary">User ID:</span>
                <span className="text-ink font-mono text-xs">{overview.owner.user_id}</span>
              </div>
            )}
            <div className="flex items-center gap-2 text-sm">
              <Clock size={14} className="text-ink-muted" />
              <span className="text-ink-secondary">Since:</span>
              <span className="text-ink">{new Date(overview.tenant.created_at).toLocaleDateString("en-IN")}</span>
            </div>
          </div>
        </div>
      )}

      {/* Team Table */}
      <div className="bg-white rounded-card border border-border overflow-hidden shadow-sm">
        <div className="px-5 py-3 bg-surface-mid border-b border-border-subtle">
          <h3 className="text-sm font-semibold text-ink">Team Members</h3>
        </div>
        {teamLoading ? (
          <SkeletonTable rows={4} />
        ) : team.length === 0 ? (
          <div className="p-8 text-center text-sm text-ink-muted">No team members found.</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-surface-mid text-left">
                <th className="px-5 py-2.5 text-xs font-semibold text-ink-muted uppercase tracking-wider">Name</th>
                <th className="px-5 py-2.5 text-xs font-semibold text-ink-muted uppercase tracking-wider">Role</th>
                <th className="px-5 py-2.5 text-xs font-semibold text-ink-muted uppercase tracking-wider">Status</th>
                <th className="px-5 py-2.5 text-xs font-semibold text-ink-muted uppercase tracking-wider">Score</th>
                <th className="px-5 py-2.5 text-xs font-semibold text-ink-muted uppercase tracking-wider">Shift</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border-subtle">
              {team.map(m => (
                <tr key={m.id} className="hover:bg-surface-mid/50 transition-colors">
                  <td className="px-5 py-3 text-ink font-medium">{m.name}</td>
                  <td className="px-5 py-3">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                      m.role === "owner" ? "bg-purple-50 text-purple-700" : "bg-surface-mid text-ink-muted"
                    }`}>
                      {m.role}
                    </span>
                  </td>
                  <td className="px-5 py-3">
                    <span className="flex items-center gap-1.5">
                      <span className={`w-1.5 h-1.5 rounded-full ${m.is_active ? "bg-success" : "bg-ink-muted/30"}`} />
                      <span className="text-xs text-ink-secondary">{m.is_active ? "Active" : "Inactive"}</span>
                    </span>
                  </td>
                  <td className="px-5 py-3 text-ink">{m.score !== null ? m.score : "—"}</td>
                  <td className="px-5 py-3 text-ink-secondary text-xs">
                    {m.shift_start_hour !== null && m.shift_end_hour !== null
                      ? `${m.shift_start_hour}:00 - ${m.shift_end_hour}:00`
                      : "Default"
                    }
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Wipe Confirm Dialog */}
      <ConfirmDialog
        open={wipeDialogOpen}
        onClose={() => setWipeDialogOpen(false)}
        onConfirm={handleWipeLeads}
        title="Wipe All Leads"
        description="This will permanently delete ALL leads, messages, and associated data for this client. This action cannot be undone."
        details={overview ? [
          { label: "total leads", count: overview.stats.total_leads },
        ] : []}
        confirmText={overview?.tenant.name || "CONFIRM"}
        loading={wipeLoading}
      />
    </div>
  );
}
