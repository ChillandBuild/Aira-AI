"use client";
import { useEffect, useState } from "react";
import { Activity, CheckCircle2, XCircle, AlertTriangle } from "lucide-react";
import { API_URL, getAuthHeaders } from "@/lib/api";
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

interface ChannelHealth {
  channel: string;
  healthy: boolean;
  token_status: "valid" | "expired" | "not_set";
}

interface DeliveryStats {
  sent: number;
  delivered: number;
  failed: number;
  success_rate: number;
}

interface RecentError {
  error: string;
  count: number;
  last_seen: string;
}

interface Incident {
  id: string;
  type: string;
  severity: string;
  message: string;
  created_at: string;
}

interface HealthData {
  channels: ChannelHealth[];
  delivery_stats_7d: DeliveryStats;
  recent_errors: RecentError[];
  open_incidents: Incident[];
}

function tokenBadge(status: string) {
  switch (status) {
    case "valid":
      return <span className="inline-flex items-center gap-1 text-xs text-success"><CheckCircle2 size={12} /> Valid</span>;
    case "expired":
      return <span className="inline-flex items-center gap-1 text-xs text-danger"><XCircle size={12} /> Expired</span>;
    default:
      return <span className="inline-flex items-center gap-1 text-xs text-ink-muted"><XCircle size={12} /> Not Set</span>;
  }
}

export function HealthView({ tenantId }: { tenantId: string }) {
  const [health, setHealth] = useState<HealthData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<HealthData>(`/api/v1/operator/clients/${tenantId}/health`)
      .then(setHealth)
      .catch(e => setError(e instanceof Error ? e.message : "Failed to load health"))
      .finally(() => setLoading(false));
  }, [tenantId]);

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} />)}
        </div>
        <SkeletonCard />
        <SkeletonTable rows={3} />
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

  if (!health) return null;

  const ds = health.delivery_stats_7d;
  const successPct = ds.success_rate;

  return (
    <div className="space-y-6">
      {/* Channel Health */}
      <div>
        <h3 className="text-sm font-semibold text-ink mb-3 flex items-center gap-2">
          <Activity size={16} className="text-ink-muted" />
          Channel Health
        </h3>
        <div className="grid grid-cols-4 gap-4">
          {health.channels.map(ch => (
            <div key={ch.channel} className="bg-white rounded-card border border-border p-4 shadow-sm">
              <div className="flex items-center gap-2 mb-2">
                <span className={`w-2 h-2 rounded-full ${ch.healthy ? "bg-success animate-pulse" : "bg-danger"}`} />
                <span className="text-sm font-medium text-ink capitalize">{ch.channel}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className={`text-xs font-medium ${ch.healthy ? "text-success" : "text-danger"}`}>
                  {ch.healthy ? "Healthy" : "Unhealthy"}
                </span>
                {tokenBadge(ch.token_status)}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Delivery Stats (7d) */}
      <div className="bg-white rounded-card border border-border p-5 shadow-sm">
        <h3 className="text-sm font-semibold text-ink mb-4">Delivery Stats (7 days)</h3>
        <div className="grid grid-cols-4 gap-4 mb-4">
          <div>
            <p className="text-xs text-ink-muted uppercase tracking-wider">Sent</p>
            <p className="text-lg font-bold text-ink">{ds.sent.toLocaleString()}</p>
          </div>
          <div>
            <p className="text-xs text-ink-muted uppercase tracking-wider">Delivered</p>
            <p className="text-lg font-bold text-success">{ds.delivered.toLocaleString()}</p>
          </div>
          <div>
            <p className="text-xs text-ink-muted uppercase tracking-wider">Failed</p>
            <p className="text-lg font-bold text-danger">{ds.failed.toLocaleString()}</p>
          </div>
          <div>
            <p className="text-xs text-ink-muted uppercase tracking-wider">Success Rate</p>
            <p className="text-lg font-bold text-ink">{successPct.toFixed(1)}%</p>
          </div>
        </div>
        {/* Visual bar */}
        <div className="w-full h-3 bg-surface-mid rounded-full overflow-hidden">
          <div
            className="h-full bg-success rounded-full transition-all duration-500"
            style={{ width: `${Math.min(successPct, 100)}%` }}
          />
        </div>
        <div className="flex justify-between text-xs text-ink-muted mt-1">
          <span>0%</span>
          <span>100%</span>
        </div>
      </div>

      {/* Recent Errors */}
      {health.recent_errors.length > 0 && (
        <div className="bg-white rounded-card border border-border overflow-hidden shadow-sm">
          <div className="px-5 py-3 bg-surface-mid border-b border-border-subtle">
            <h3 className="text-sm font-semibold text-ink flex items-center gap-2">
              <AlertTriangle size={14} className="text-warning" />
              Recent Delivery Errors
            </h3>
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-surface-mid text-left">
                <th className="px-5 py-2.5 text-xs font-semibold text-ink-muted uppercase tracking-wider">Error</th>
                <th className="px-5 py-2.5 text-xs font-semibold text-ink-muted uppercase tracking-wider">Count</th>
                <th className="px-5 py-2.5 text-xs font-semibold text-ink-muted uppercase tracking-wider">Last Seen</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border-subtle">
              {health.recent_errors.map((err, i) => (
                <tr key={i} className="hover:bg-surface-mid/50 transition-colors">
                  <td className="px-5 py-3 text-ink">{err.error}</td>
                  <td className="px-5 py-3 text-ink font-medium">{err.count}</td>
                  <td className="px-5 py-3 text-ink-muted">{new Date(err.last_seen).toLocaleString("en-IN")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Open Incidents */}
      {health.open_incidents.length > 0 && (
        <div className="bg-white rounded-card border border-border overflow-hidden shadow-sm">
          <div className="px-5 py-3 bg-surface-mid border-b border-border-subtle">
            <h3 className="text-sm font-semibold text-ink flex items-center gap-2">
              <XCircle size={14} className="text-danger" />
              Open Incidents
            </h3>
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-surface-mid text-left">
                <th className="px-5 py-2.5 text-xs font-semibold text-ink-muted uppercase tracking-wider">Type</th>
                <th className="px-5 py-2.5 text-xs font-semibold text-ink-muted uppercase tracking-wider">Severity</th>
                <th className="px-5 py-2.5 text-xs font-semibold text-ink-muted uppercase tracking-wider">Message</th>
                <th className="px-5 py-2.5 text-xs font-semibold text-ink-muted uppercase tracking-wider">Created</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border-subtle">
              {health.open_incidents.map(inc => (
                <tr key={inc.id} className="hover:bg-surface-mid/50 transition-colors">
                  <td className="px-5 py-3 text-ink font-mono text-xs">{inc.type}</td>
                  <td className="px-5 py-3">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                      inc.severity === "critical" ? "bg-danger/10 text-danger" :
                      inc.severity === "warning" ? "bg-warning/10 text-warning" :
                      "bg-surface-mid text-ink-muted"
                    }`}>
                      {inc.severity}
                    </span>
                  </td>
                  <td className="px-5 py-3 text-ink">{inc.message}</td>
                  <td className="px-5 py-3 text-ink-muted text-xs">{new Date(inc.created_at).toLocaleString("en-IN")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Empty state */}
      {health.recent_errors.length === 0 && health.open_incidents.length === 0 && (
        <div className="bg-white rounded-card border border-border p-8 shadow-sm text-center">
          <CheckCircle2 size={32} className="text-success mx-auto mb-2" />
          <p className="text-sm text-ink-secondary">No errors or incidents. All systems healthy.</p>
        </div>
      )}
    </div>
  );
}
