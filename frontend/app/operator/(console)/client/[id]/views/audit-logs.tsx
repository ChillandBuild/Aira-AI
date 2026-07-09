"use client";
import { useCallback, useEffect, useState } from "react";
import { Download, Search } from "lucide-react";
import { API_URL, getAuthHeaders } from "@/lib/api";
import { SkeletonTable } from "../components/skeleton";

interface AuditEntry {
  id: string;
  actor_user_id: string | null;
  actor_role: string | null;
  action: string;
  target_type: string;
  target_id: string | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
}

function formatMeta(meta: Record<string, unknown> | null): string {
  if (!meta || Object.keys(meta).length === 0) return "";
  return Object.entries(meta)
    .filter(([, v]) => v !== null && v !== undefined && v !== "********")
    .map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : String(v)}`)
    .join(" · ");
}

function toDateStr(d: Date): string {
  return d.toISOString().slice(0, 10);
}

export function AuditLogsView({ tenantId, clientName }: { tenantId: string; clientName: string }) {
  const [logs, setLogs] = useState<AuditEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const today = toDateStr(new Date());
  const thirtyDaysAgo = toDateStr(new Date(Date.now() - 30 * 86400000));
  const [dateFrom, setDateFrom] = useState(thirtyDaysAgo);
  const [dateTo, setDateTo] = useState(today);

  const limit = 30;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const auth = await getAuthHeaders();
      const params = new URLSearchParams({ page: String(page), limit: String(limit) });
      if (dateFrom) params.set("date_from", dateFrom);
      if (dateTo) params.set("date_to", dateTo);
      const res = await fetch(`${API_URL}/api/v1/operator/clients/${tenantId}/audit-logs?${params}`, {
        headers: { ...auth },
        cache: "no-store",
      });
      if (!res.ok) throw new Error(`Request failed (${res.status})`);
      const data = await res.json();
      setLogs(data.data);
      setTotal(data.total);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, [tenantId, page, dateFrom, dateTo]);

  useEffect(() => { load(); }, [load]);

  async function handleDownloadCsv() {
    try {
      const auth = await getAuthHeaders();
      const params = new URLSearchParams();
      if (dateFrom) params.set("date_from", dateFrom);
      if (dateTo) params.set("date_to", dateTo);
      const res = await fetch(`${API_URL}/api/v1/operator/clients/${tenantId}/audit-logs/csv?${params}`, {
        headers: { ...auth },
      });
      if (!res.ok) throw new Error("Download failed");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `audit-log-${clientName.replace(/\s+/g, "_")}-${dateFrom}-to-${dateTo}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Download failed");
    }
  }

  const totalPages = Math.ceil(total / limit) || 1;

  return (
    <div className="space-y-4">
      {error && (
        <div className="p-3 bg-red-50 border border-danger/20 rounded-xl text-sm text-danger flex items-center justify-between">
          {error}
          <button onClick={() => setError(null)} className="text-xs underline ml-2">dismiss</button>
        </div>
      )}

      {/* Date range + Download */}
      <div className="rounded-2xl border border-border bg-white/95 p-3 shadow-sm">
        <div className="flex flex-wrap items-center gap-2.5 lg:flex-nowrap">
          <div className="flex shrink-0 items-center gap-2">
            <label className="text-[11px] font-bold uppercase tracking-wider text-ink-muted">From</label>
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => { setDateFrom(e.target.value); setPage(1); }}
              className="h-9 rounded-xl border border-border bg-white px-3 text-xs font-semibold text-ink shadow-[inset_0_1px_0_rgba(255,255,255,0.8)] transition-colors hover:border-violet-200 focus:outline-none focus:ring-2 focus:ring-violet-200"
            />
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <label className="text-[11px] font-bold uppercase tracking-wider text-ink-muted">To</label>
            <input
              type="date"
              value={dateTo}
              onChange={(e) => { setDateTo(e.target.value); setPage(1); }}
              className="h-9 rounded-xl border border-border bg-white px-3 text-xs font-semibold text-ink shadow-[inset_0_1px_0_rgba(255,255,255,0.8)] transition-colors hover:border-violet-200 focus:outline-none focus:ring-2 focus:ring-violet-200"
            />
          </div>
          <button
            onClick={handleDownloadCsv}
            className="ml-auto flex h-9 shrink-0 items-center gap-1.5 rounded-xl bg-primary px-3 text-xs font-bold text-white shadow-sm transition-colors hover:bg-primary-dark focus:outline-none focus:ring-2 focus:ring-violet-200"
          >
            <Download size={13} /> Export CSV
          </button>
        </div>
      </div>

      {/* Table */}
      {loading ? (
        <SkeletonTable rows={6} />
      ) : logs.length === 0 ? (
        <div className="bg-white rounded-card border border-border p-12 text-center shadow-sm">
          <Search size={32} className="text-ink-muted mx-auto mb-2" />
          <p className="text-sm text-ink-muted">No audit log entries for this date range.</p>
        </div>
      ) : (
        <div className="bg-white rounded-card border border-border overflow-hidden shadow-sm">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-surface-mid text-left">
                <th className="px-5 py-2.5 text-xs font-semibold text-ink-muted uppercase tracking-wider">Time</th>
                <th className="px-5 py-2.5 text-xs font-semibold text-ink-muted uppercase tracking-wider">Action</th>
                <th className="px-5 py-2.5 text-xs font-semibold text-ink-muted uppercase tracking-wider">Target</th>
                <th className="px-5 py-2.5 text-xs font-semibold text-ink-muted uppercase tracking-wider">Details</th>
                <th className="px-5 py-2.5 text-xs font-semibold text-ink-muted uppercase tracking-wider">Actor</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border-subtle">
              {logs.map((log) => (
                <tr key={log.id} className="hover:bg-surface-mid/50 transition-colors">
                  <td className="px-5 py-3 text-ink-muted text-xs whitespace-nowrap">
                    {new Date(log.created_at).toLocaleString("en-IN", { dateStyle: "short", timeStyle: "short" })}
                  </td>
                  <td className="px-5 py-3">
                    <span className="px-2 py-0.5 rounded-full text-[11px] font-medium bg-primary-light text-primary">
                      {log.action}
                    </span>
                  </td>
                  <td className="px-5 py-3 text-ink-muted text-xs font-mono">
                    {log.target_type}{log.target_id ? `:${log.target_id.slice(0, 8)}` : ""}
                  </td>
                  <td className="px-5 py-3 text-ink-muted text-xs max-w-[300px] truncate" title={formatMeta(log.metadata)}>
                    {formatMeta(log.metadata) || "—"}
                  </td>
                  <td className="px-5 py-3">
                    <span className={`px-2 py-0.5 rounded-full text-[11px] font-medium ${
                      log.actor_role === "system_admin" ? "bg-purple-50 text-purple-700"
                        : log.actor_role === "owner" ? "bg-primary-light text-primary"
                        : "bg-surface-mid text-ink-muted"
                    }`}>
                      {log.actor_role || "system"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-xs text-ink-muted">{total} entries · page {page} of {totalPages}</p>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={page === 1}
              className="px-3 py-1.5 border border-border rounded-lg text-sm hover:bg-surface-mid disabled:opacity-30 transition-colors"
            >
              Previous
            </button>
            <button
              onClick={() => setPage(p => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
              className="px-3 py-1.5 border border-border rounded-lg text-sm hover:bg-surface-mid disabled:opacity-30 transition-colors"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
