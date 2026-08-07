"use client";
import { useState } from "react";
import { Key, PowerOff, Power } from "lucide-react";
import { API_URL, getAuthHeaders } from "@/lib/api";
import { ConfirmModal } from "@/components/ConfirmModal";
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
  const [tempPassword, setTempPassword] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [showResetConfirm, setShowResetConfirm] = useState(false);
  const [showStatusConfirm, setShowStatusConfirm] = useState(false);

  async function handleResetPassword() {
    setActionLoading("reset");
    try {
      const res = await apiFetch<{ temp_password: string }>(`/api/v1/operator/clients/${tenantId}/reset-password`, {
        method: "POST",
      });
      setTempPassword(res.temp_password);
      setShowResetConfirm(false);
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
      setShowStatusConfirm(false);
      onReload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update status");
    } finally {
      setActionLoading(null);
    }
  }

  const isActive = overview?.tenant.status === "active";
  const clientName = overview?.tenant.name || "this client";

  return (
    <div className="space-y-6">
      {/* Action Cards */}
      <div>
        <h3 className="text-sm font-semibold text-ink mb-3">Actions</h3>
        <div className="grid grid-cols-2 gap-4">
          {/* Reset Password */}
          <div className="bg-white rounded-card border border-border p-4 shadow-sm hover:shadow-card transition-all">
            <button
              onClick={() => setShowResetConfirm(true)}
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
              onClick={() => setShowStatusConfirm(true)}
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

      <p className="text-xs text-ink-muted">
        Team roster and owner details are on the <span className="font-medium text-ink-secondary">Team</span> tab.
        To wipe a client&apos;s lead data, use the <span className="font-medium text-ink-secondary">Data Ops</span> tab.
      </p>

      {/* Reset Password Confirmation */}
      <ConfirmModal
        open={showResetConfirm}
        onClose={() => setShowResetConfirm(false)}
        onConfirm={handleResetPassword}
        title="Reset owner password?"
        description={`This will generate a new temporary password for ${clientName}'s account owner. Their current password will stop working immediately.`}
        confirmLabel="Reset"
        tone="primary"
        loading={actionLoading === "reset"}
      />

      {/* Suspend/Activate Confirmation */}
      <ConfirmModal
        open={showStatusConfirm}
        onClose={() => setShowStatusConfirm(false)}
        onConfirm={handleToggleStatus}
        title={isActive ? `Suspend ${clientName}?` : `Activate ${clientName}?`}
        description={
          isActive
            ? `Suspended clients lose access to all services immediately. Are you sure you want to suspend ${clientName}?`
            : `${clientName} will regain access to all services immediately. Are you sure you want to activate this client?`
        }
        confirmLabel={isActive ? "Suspend" : "Activate"}
        tone={isActive ? "danger" : "primary"}
        loading={actionLoading === "status"}
      />
    </div>
  );
}
