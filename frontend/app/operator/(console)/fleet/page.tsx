"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { RefreshCw, Users, AlertTriangle, Download, ArrowUp, ArrowDown, ArrowUpDown } from "lucide-react";
import { operatorFetch } from "@/lib/operator";

interface FleetClient {
  id: string;
  name: string;
  enabled_features: string[];
  status: string;
  created_at: string;
  mrr: number;
  health: "healthy" | "warning" | "critical";
  messages_30d: number;
  ai_usage: number;
  last_activity: string | null;
  near_cap?: boolean;
  no_activity_14d?: boolean;
  token_expired?: boolean;
  channel_unhealthy?: boolean;
}

type SortKey = "mrr" | "ai_usage" | "messages_30d" | "last_activity";
type SortDir = "asc" | "desc";

const SORT_COLUMNS: { key: SortKey; label: string }[] = [
  { key: "mrr", label: "MRR" },
  { key: "messages_30d", label: "Msgs 30d" },
  { key: "ai_usage", label: "AI Usage %" },
  { key: "last_activity", label: "Last Activity" },
];

function attentionReasons(c: FleetClient): string[] {
  const reasons: string[] = [];
  if (c.token_expired) reasons.push("Token expired");
  if (c.channel_unhealthy) reasons.push("Channel down");
  if (c.near_cap) reasons.push("Near cap");
  if (c.no_activity_14d) reasons.push("Idle 14d");
  return reasons;
}

function csvEscape(value: string | number): string {
  const s = String(value);
  if (/[",\n]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
  return s;
}

export default function FleetPage() {
  const [clients, setClients] = useState<FleetClient[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [healthFilter, setHealthFilter] = useState<string>("all");
  const [sortKey, setSortKey] = useState<SortKey | null>(null);
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const load = useCallback(() => {
    setLoading(true);
    return operatorFetch<{ data: FleetClient[] } | FleetClient[]>("/api/v1/operator/fleet")
      .then(res => {
        setClients(Array.isArray(res) ? res : res.data ?? []);
        setError(null);
      })
      .catch(e => setError(e instanceof Error ? e.message : "Request failed"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const totalMrr = clients.reduce((sum, c) => sum + (c.mrr || 0), 0);
  const activeCount = clients.filter(c => c.status === "active").length;
  const trialCount = clients.filter(c => c.status === "trial").length;
  const nearCap = clients.filter(c => c.ai_usage >= 80).length;

  const attentionClients = useMemo(
    () => clients.filter(c => c.health !== "healthy"),
    [clients]
  );

  const statusOptions = useMemo(
    () => Array.from(new Set(clients.map(c => c.status))).sort(),
    [clients]
  );

  const filteredSorted = useMemo(() => {
    let rows = clients;
    if (statusFilter !== "all") rows = rows.filter(c => c.status === statusFilter);
    if (healthFilter !== "all") rows = rows.filter(c => c.health === healthFilter);

    if (sortKey) {
      const dirMul = sortDir === "asc" ? 1 : -1;
      rows = [...rows].sort((a, b) => {
        if (sortKey === "last_activity") {
          const av = a.last_activity ? new Date(a.last_activity).getTime() : 0;
          const bv = b.last_activity ? new Date(b.last_activity).getTime() : 0;
          return (av - bv) * dirMul;
        }
        const av = a[sortKey] || 0;
        const bv = b[sortKey] || 0;
        return (av - bv) * dirMul;
      });
    }
    return rows;
  }, [clients, statusFilter, healthFilter, sortKey, sortDir]);

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir(d => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  };

  const exportCsv = () => {
    const headers = ["Company", "Status", "MRR", "Msgs 30d", "AI Usage %", "Health", "Last Activity"];
    const lines = [headers.join(",")];
    for (const c of filteredSorted) {
      lines.push([
        csvEscape(c.name),
        csvEscape(c.status),
        csvEscape(c.mrr || 0),
        csvEscape(c.messages_30d),
        csvEscape(c.ai_usage),
        csvEscape(c.health),
        csvEscape(c.last_activity ? new Date(c.last_activity).toISOString() : ""),
      ].join(","));
    }
    const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8;" });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `fleet_${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
  };

  if (loading && clients.length === 0) return <div className="p-8 text-center">Loading fleet…</div>;

  return (
    <div className="max-w-7xl mx-auto px-8 py-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-ink">Fleet Cockpit</h1>
          <p className="text-sm text-ink-muted mt-1">All clients summary and attention queue.</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={exportCsv}
            disabled={filteredSorted.length === 0}
            className="flex items-center gap-1.5 px-3 py-2 text-sm text-ink-secondary hover:text-ink border border-border rounded-lg hover:bg-surface-mid transition-colors disabled:opacity-60"
            title="Export CSV"
            aria-label="Export fleet as CSV"
          >
            <Download size={14} /> Export CSV
          </button>
          <button
            onClick={() => load()}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-2 text-sm text-ink-secondary hover:text-ink border border-border rounded-lg hover:bg-surface-mid transition-colors disabled:opacity-60"
            title="Refresh"
            aria-label="Refresh fleet"
          >
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} /> Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-danger/20 rounded-xl text-sm text-danger">
          {error}
        </div>
      )}

      <div className="grid grid-cols-4 gap-4 mb-6">
        <div className="bg-white rounded-card border border-border p-4 shadow-card">
          <p className="text-xs text-ink-muted uppercase tracking-wider font-medium">Total MRR</p>
          <p className="text-2xl font-bold text-primary mt-1">₹{totalMrr.toLocaleString("en-IN")}</p>
        </div>
        <div className="bg-white rounded-card border border-border p-4 shadow-card">
          <p className="text-xs text-ink-muted uppercase tracking-wider font-medium">Active Clients</p>
          <p className="text-2xl font-bold text-success mt-1">{activeCount}</p>
        </div>
        <div className="bg-white rounded-card border border-border p-4 shadow-card">
          <p className="text-xs text-ink-muted uppercase tracking-wider font-medium">Trials</p>
          <p className="text-2xl font-bold text-warning mt-1">{trialCount}</p>
        </div>
        <div className="bg-white rounded-card border border-border p-4 shadow-card">
          <p className="text-xs text-ink-muted uppercase tracking-wider font-medium">Near Cap</p>
          <p className="text-2xl font-bold text-danger mt-1">{nearCap}</p>
        </div>
      </div>

      {/* Attention Queue */}
      <div className="mb-6">
        <h2 className="text-sm font-semibold text-ink mb-3 flex items-center gap-2">
          <AlertTriangle size={16} className="text-warning" />
          Attention Queue
        </h2>
        {attentionClients.length === 0 ? (
          <div className="bg-white rounded-card border border-border shadow-card px-5 py-4 text-sm text-ink-secondary">
            All clients healthy.
          </div>
        ) : (
          <div className="bg-white rounded-card border border-border shadow-card divide-y divide-border-subtle overflow-hidden">
            {attentionClients.map(c => (
              <div key={c.id} className="px-5 py-3 flex items-center justify-between gap-4 flex-wrap">
                <div className="flex items-center gap-3 min-w-0">
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium shrink-0 ${
                    c.health === "critical" ? "bg-red-50 text-danger" : "bg-warning/10 text-warning"
                  }`}>
                    {c.health}
                  </span>
                  <span className="font-medium text-ink truncate">{c.name}</span>
                </div>
                <div className="flex items-center gap-1.5 flex-wrap">
                  {attentionReasons(c).map(reason => (
                    <span
                      key={reason}
                      className="px-2 py-0.5 rounded-full text-xs font-medium bg-surface-mid text-ink-secondary border border-border-subtle"
                    >
                      {reason}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3 mb-4 flex-wrap">
        <div className="flex items-center gap-2">
          <label htmlFor="status-filter" className="text-xs font-medium text-ink-secondary">Status</label>
          <select
            id="status-filter"
            value={statusFilter}
            onChange={e => setStatusFilter(e.target.value)}
            className="border border-border rounded-lg px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
          >
            <option value="all">All</option>
            {statusOptions.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <div className="flex items-center gap-2">
          <label htmlFor="health-filter" className="text-xs font-medium text-ink-secondary">Health</label>
          <select
            id="health-filter"
            value={healthFilter}
            onChange={e => setHealthFilter(e.target.value)}
            className="border border-border rounded-lg px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
          >
            <option value="all">All</option>
            <option value="healthy">Healthy</option>
            <option value="warning">Warning</option>
            <option value="critical">Critical</option>
          </select>
        </div>
        {(statusFilter !== "all" || healthFilter !== "all") && (
          <button
            onClick={() => { setStatusFilter("all"); setHealthFilter("all"); }}
            className="text-xs text-ink-muted hover:text-ink underline"
          >
            Clear filters
          </button>
        )}
      </div>

      {clients.length === 0 ? (
        <div className="bg-white rounded-card border border-border shadow-card flex flex-col items-center justify-center py-16 px-6 text-center">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-surface-mid text-ink-muted mb-4">
            <Users size={22} />
          </div>
          <p className="text-sm font-semibold text-ink">No clients yet</p>
          <p className="text-xs text-ink-muted mt-1 max-w-xs">
            Onboard your first client to see MRR, usage, and health across the fleet here.
          </p>
        </div>
      ) : filteredSorted.length === 0 ? (
        <div className="bg-white rounded-card border border-border shadow-card flex flex-col items-center justify-center py-16 px-6 text-center">
          <p className="text-sm font-semibold text-ink">No clients match the current filters</p>
        </div>
      ) : (
        <div className="bg-white rounded-card border border-border shadow-card overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-surface-mid">
              <tr>
                <th className="px-5 py-3 text-left font-semibold text-ink-secondary whitespace-nowrap">Company</th>
                <th className="px-5 py-3 text-left font-semibold text-ink-secondary whitespace-nowrap">Status</th>
                {SORT_COLUMNS.map(col => (
                  <th key={col.key} className="px-5 py-3 text-left font-semibold text-ink-secondary whitespace-nowrap">
                    <button
                      type="button"
                      onClick={() => toggleSort(col.key)}
                      className="flex items-center gap-1 hover:text-ink transition-colors"
                      aria-label={`Sort by ${col.label}`}
                    >
                      {col.label}
                      {sortKey === col.key ? (
                        sortDir === "asc" ? <ArrowUp size={12} /> : <ArrowDown size={12} />
                      ) : (
                        <ArrowUpDown size={12} className="text-ink-muted/50" />
                      )}
                    </button>
                  </th>
                ))}
                <th className="px-5 py-3 text-left font-semibold text-ink-secondary whitespace-nowrap">Health</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border-subtle">
              {filteredSorted.map(c => (
                <tr key={c.id} className="hover:bg-surface-mid/50 transition-colors">
                  <td className="px-5 py-3 font-medium text-ink">{c.name}</td>
                  <td className="px-5 py-3">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                      c.status === "active" ? "bg-green-50 text-success" : "bg-red-50 text-danger"
                    }`}>
                      {c.status}
                    </span>
                  </td>
                  <td className="px-5 py-3 text-primary font-mono">₹{(c.mrr || 0).toLocaleString("en-IN")}</td>
                  <td className="px-5 py-3 font-mono text-ink">{c.messages_30d.toLocaleString("en-IN")}</td>
                  <td className="px-5 py-3">
                    <div className="flex items-center gap-2">
                      <div className="w-full bg-surface-mid rounded-full h-2 max-w-24 overflow-hidden">
                        <div className={`h-2 rounded-full ${c.ai_usage >= 100 ? "bg-danger" : c.ai_usage >= 80 ? "bg-warning" : "bg-success"}`}
                          style={{ width: `${Math.min(c.ai_usage, 100)}%` }} />
                      </div>
                      <span className={`text-xs font-mono font-medium tabular-nums ${
                        c.ai_usage >= 100 ? "text-danger" : c.ai_usage >= 80 ? "text-warning" : "text-ink-secondary"
                      }`}>
                        {Math.round(c.ai_usage)}%
                      </span>
                    </div>
                  </td>
                  <td className="px-5 py-3 text-ink-muted">
                    {c.last_activity ? new Date(c.last_activity).toLocaleDateString("en-IN") : "—"}
                  </td>
                  <td className="px-5 py-3">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                      c.health === "healthy" ? "bg-green-50 text-success" : c.health === "warning" ? "bg-warning/10 text-warning" : "bg-red-50 text-danger"
                    }`}>
                      {c.health}
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
