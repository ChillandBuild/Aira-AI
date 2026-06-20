"use client";
import { useEffect, useState } from "react";
import {
  Radio, MessageSquare, PhoneCall, Users,
  BookOpen, FileCheck, BarChart2,
} from "lucide-react";
import { API_URL, getAuthHeaders } from "@/lib/api";
import { ConfirmDialog } from "../components/confirm-dialog";
import { SkeletonCard } from "../components/skeleton";

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

const DATA_TYPES = [
  { key: "broadcasts", label: "Broadcast History", icon: Radio, color: "text-primary", bg: "bg-primary-light" },
  { key: "messages", label: "Messages", icon: MessageSquare, color: "text-info", bg: "bg-info/5" },
  { key: "call_logs", label: "Call Logs", icon: PhoneCall, color: "text-warning", bg: "bg-warning/10" },
  { key: "leads", label: "Leads", icon: Users, color: "text-success", bg: "bg-success/10" },
  { key: "knowledge", label: "Knowledge Base", icon: BookOpen, color: "text-purple-600", bg: "bg-purple-50" },
  { key: "templates", label: "Templates", icon: FileCheck, color: "text-pink-600", bg: "bg-pink-50" },
  { key: "analytics", label: "Analytics Data", icon: BarChart2, color: "text-ink-secondary", bg: "bg-surface-mid" },
] as const;

type DataTypeKey = typeof DATA_TYPES[number]["key"];

export function DataOpsView({ tenantId, clientName }: { tenantId: string; clientName: string }) {
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(true);
  const [confirmType, setConfirmType] = useState<DataTypeKey | null>(null);
  const [clearing, setClearing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function fetchCounts() {
      setLoading(true);
      const result: Record<string, number> = {};
      await Promise.allSettled(
        DATA_TYPES.map(async (dt) => {
          try {
            const data = await apiFetch<{ count: number }>(
              `/api/v1/operator/clients/${tenantId}/clear/${dt.key}/count`
            );
            result[dt.key] = data.count;
          } catch {
            result[dt.key] = 0;
          }
        })
      );
      if (!cancelled) {
        setCounts(result);
        setLoading(false);
      }
    }
    fetchCounts();
    return () => { cancelled = true; };
  }, [tenantId]);

  async function handleClear() {
    if (!confirmType) return;
    setClearing(true);
    try {
      await apiFetch(`/api/v1/operator/clients/${tenantId}/clear/${confirmType}`, {
        method: "POST",
      });
      setCounts(prev => ({ ...prev, [confirmType]: 0 }));
      setConfirmType(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to clear data");
    } finally {
      setClearing(false);
    }
  }

  const activeType = confirmType ? DATA_TYPES.find(d => d.key === confirmType) : null;

  return (
    <div className="space-y-4">
      {error && (
        <div className="p-3 bg-red-50 border border-danger/20 rounded-xl text-sm text-danger flex items-center justify-between">
          {error}
          <button onClick={() => setError(null)} className="text-xs underline ml-2">dismiss</button>
        </div>
      )}

      <h3 className="text-sm font-semibold text-ink">Data Operations</h3>
      <p className="text-xs text-ink-muted">Clear specific data types for this client. Each operation requires confirmation.</p>

      {loading ? (
        <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {Array.from({ length: 7 }).map((_, i) => <SkeletonCard key={i} />)}
        </div>
      ) : (
        <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {DATA_TYPES.map(dt => {
            const count = counts[dt.key] ?? 0;
            const Icon = dt.icon;
            return (
              <div key={dt.key} className="bg-white rounded-card border border-border p-5 shadow-sm">
                <div className="flex items-center gap-3 mb-3">
                  <div className={`w-10 h-10 rounded-xl ${dt.bg} flex items-center justify-center`}>
                    <Icon size={18} className={dt.color} />
                  </div>
                  <div>
                    <p className="text-sm font-medium text-ink">{dt.label}</p>
                    <p className="text-xs text-ink-muted">{count.toLocaleString()} records</p>
                  </div>
                </div>
                <button
                  onClick={() => setConfirmType(dt.key)}
                  disabled={count === 0}
                  className="w-full px-3 py-2 border border-danger/20 text-danger text-sm rounded-xl hover:bg-red-50 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                >
                  Clear Data
                </button>
              </div>
            );
          })}
        </div>
      )}

      {/* Confirm Dialog */}
      <ConfirmDialog
        open={!!confirmType}
        onClose={() => setConfirmType(null)}
        onConfirm={handleClear}
        title={`Clear ${activeType?.label || ""}`}
        description={`This will permanently delete all ${activeType?.label.toLowerCase() || ""} data for "${clientName}". This action cannot be undone.`}
        details={confirmType ? [{ label: activeType?.label || "", count: counts[confirmType] ?? 0 }] : []}
        confirmText={clientName}
        loading={clearing}
      />
    </div>
  );
}
