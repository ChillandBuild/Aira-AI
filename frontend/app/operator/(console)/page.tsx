"use client";
import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Plus, RefreshCw, PowerOff, Power, List, LayoutGrid, Copy, Check, Eye, EyeOff, Activity, Clock, Cpu, HardDrive, X } from "lucide-react";
import { API_URL } from "@/lib/api";
import { operatorFetch } from "@/lib/operator";
import { OnboardingWizard } from "./components/onboarding-wizard";
import { ActionConfirm } from "./components/action-confirm";

type Client = {
  id: string;
  name: string;
  enabled_features: string[];
  status: string;
  created_at: string;
  owner_user_id: string | null;
};

const FEATURE_LABELS: Record<string, string> = {
  whatsapp: "WA",
  telecalling: "TC",
  instagram: "IG",
  facebook: "FB",
  telegram: "TG",
};

type SystemHealth = {
  status: "healthy" | "unhealthy";
  uptime_seconds: number;
  uptime_human: string;
  started_at: string;
  server_time: string;
  details: {
    database: string;
    scheduler_jobs: Record<string, { status: string; last_heartbeat: string | null }>;
  };
};

type OperatorHealth = {
  status: string;
  uptime_seconds: number;
  uptime_human: string;
  memory_mb: number;
  cpu_percent: number;
  python_version: string;
  server_time: string;
  started_at: string;
};

function SystemHealthCard({ health, operatorHealth, loading }: { health: SystemHealth | null; operatorHealth: OperatorHealth | null; loading: boolean }) {
  if (loading) {
    return (
      <div className="mb-6 p-4 bg-white rounded-card border border-border animate-pulse">
        <div className="h-5 bg-surface-mid rounded w-32 mb-3" />
        <div className="flex gap-6">
          <div className="h-4 bg-surface-mid rounded w-24" />
          <div className="h-4 bg-surface-mid rounded w-24" />
          <div className="h-4 bg-surface-mid rounded w-24" />
        </div>
      </div>
    );
  }

  const isHealthy = health?.status === "healthy";
  const dbOk = health?.details?.database === "ok";
  const uptime = operatorHealth?.uptime_human || health?.uptime_human || "—";
  const memoryMb = operatorHealth?.memory_mb;
  const cpuPercent = operatorHealth?.cpu_percent;

  return (
    <div className={`mb-6 rounded-card border shadow-card overflow-hidden ${
      isHealthy ? "bg-white border-border" : "bg-red-50 border-danger/30"
    }`}>
      <div className="px-5 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className={`w-2.5 h-2.5 rounded-full ${isHealthy ? "bg-emerald-500 animate-pulse" : "bg-red-500"}`} />
          <span className="text-sm font-semibold text-ink">
            Render Backend
          </span>
          <span className={`px-2 py-0.5 rounded-full text-[11px] font-medium ${
            isHealthy ? "bg-emerald-50 text-emerald-700" : "bg-red-100 text-red-700"
          }`}>
            {isHealthy ? "LIVE" : "UNHEALTHY"}
          </span>
        </div>
        <div className="flex items-center gap-5 text-xs text-ink-muted">
          <div className="flex items-center gap-1.5" title="Uptime since last deploy">
            <Clock size={12} className="opacity-60" />
            <span className="font-mono">{uptime}</span>
          </div>
          {memoryMb != null && (
            <div className="flex items-center gap-1.5" title="Memory usage">
              <HardDrive size={12} className="opacity-60" />
              <span className="font-mono">{memoryMb} MB</span>
            </div>
          )}
          {cpuPercent != null && (
            <div className="flex items-center gap-1.5" title="CPU usage">
              <Cpu size={12} className="opacity-60" />
              <span className="font-mono">{cpuPercent.toFixed(1)}%</span>
            </div>
          )}
          <div className="flex items-center gap-1.5" title="Database">
            <Activity size={12} className="opacity-60" />
            <span className={`font-medium ${dbOk ? "text-emerald-600" : "text-red-600"}`}>
              DB {dbOk ? "OK" : "ERR"}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function OperatorPage() {
  const router = useRouter();
  const [clients, setClients] = useState<Client[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tempPw, setTempPw] = useState<{ name: string; pw: string } | null>(null);
  const [pwRevealed, setPwRevealed] = useState(false);
  const [pwCopied, setPwCopied] = useState(false);
  const [resetTarget, setResetTarget] = useState<Client | null>(null);
  const [resetLoading, setResetLoading] = useState(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [bulkAction, setBulkAction] = useState<"active" | "suspended" | null>(null);
  const [bulkRunning, setBulkRunning] = useState(false);
  const [bulkProgress, setBulkProgress] = useState<{ done: number; total: number } | null>(null);
  const [bulkSummary, setBulkSummary] = useState<{ succeeded: number; failed: number; failedNames: string[] } | null>(null);

  const [systemHealth, setSystemHealth] = useState<SystemHealth | null>(null);
  const [operatorHealth, setOperatorHealth] = useState<OperatorHealth | null>(null);
  const [healthLoading, setHealthLoading] = useState(true);

  const [view, setView] = useState<"grid" | "table">(() => {
    if (typeof window !== "undefined") {
      return (localStorage.getItem("operator-clients-view") as "grid" | "table") || "grid";
    }
    return "grid";
  });

  useEffect(() => {
    localStorage.setItem("operator-clients-view", view);
  }, [view]);

  const loadHealth = useCallback(async () => {
    try {
      const [healthRes, opRes] = await Promise.allSettled([
        fetch(`${API_URL}/health`).then(r => r.json()),
        operatorFetch<OperatorHealth>("/api/v1/operator/system-health"),
      ]);
      if (healthRes.status === "fulfilled") setSystemHealth(healthRes.value);
      if (opRes.status === "fulfilled") setOperatorHealth(opRes.value);
    } catch {
      // silent — card shows stale or loading state
    } finally {
      setHealthLoading(false);
    }
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await operatorFetch<{ data: Client[] }>("/api/v1/operator/clients");
      setClients(res.data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); loadHealth(); }, [load, loadHealth]);

  // Auto-refresh health every 60s — also refreshes the client list on the same cadence.
  useEffect(() => {
    const id = setInterval(() => { loadHealth(); load(); }, 60_000);
    return () => clearInterval(id);
  }, [loadHealth, load]);

  async function handleToggleStatus(client: Client) {
    const newStatus = client.status === "active" ? "suspended" : "active";
    try {
      await operatorFetch(`/api/v1/operator/clients/${client.id}/status`, {
        method: "PATCH",
        body: JSON.stringify({ status: newStatus }),
      });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update status");
    }
  }

  function toggleSelected(clientId: string) {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(clientId)) next.delete(clientId);
      else next.add(clientId);
      return next;
    });
  }

  function toggleSelectAll() {
    setSelectedIds(prev => {
      if (clients.length > 0 && prev.size === clients.length) return new Set();
      return new Set(clients.map(c => c.id));
    });
  }

  function clearSelection() {
    setSelectedIds(new Set());
  }

  function requestBulkAction(status: "active" | "suspended") {
    setBulkSummary(null);
    setBulkAction(status);
  }

  async function confirmBulkAction() {
    if (!bulkAction) return;
    const targets = clients.filter(c => selectedIds.has(c.id));
    if (targets.length === 0) {
      setBulkAction(null);
      return;
    }
    setBulkRunning(true);
    setBulkProgress({ done: 0, total: targets.length });
    let succeeded = 0;
    const failedNames: string[] = [];

    for (const client of targets) {
      try {
        await operatorFetch(`/api/v1/operator/clients/${client.id}/status`, {
          method: "PATCH",
          body: JSON.stringify({ status: bulkAction }),
        });
        succeeded++;
      } catch {
        failedNames.push(client.name);
      }
      setBulkProgress(prev => (prev ? { done: prev.done + 1, total: prev.total } : prev));
    }

    setBulkRunning(false);
    setBulkProgress(null);
    setBulkAction(null);
    setBulkSummary({ succeeded, failed: failedNames.length, failedNames });
    if (failedNames.length > 0) {
      setError(`Bulk update: ${succeeded} succeeded, ${failedNames.length} failed (${failedNames.join(", ")}).`);
    } else {
      setError(null);
    }
    clearSelection();
    await load();
  }

  function handleResetPassword(client: Client) {
    setResetTarget(client);
  }

  async function confirmResetPassword() {
    if (!resetTarget) return;
    setResetLoading(true);
    try {
      const res = await operatorFetch<{ temp_password: string }>(
        `/api/v1/operator/clients/${resetTarget.id}/reset-password`,
        { method: "POST" }
      );
      setPwRevealed(false);
      setPwCopied(false);
      setTempPw({ name: resetTarget.name, pw: res.temp_password });
      setResetTarget(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to reset password");
    } finally {
      setResetLoading(false);
    }
  }

  function copyPw(pw: string) {
    navigator.clipboard.writeText(pw);
    setPwCopied(true);
    setTimeout(() => setPwCopied(false), 2000);
  }

  function copyId(id: string) {
    navigator.clipboard.writeText(id);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  }

  function ActionButtons({ client }: { client: Client }) {
    return (
      <div className="flex items-center gap-2">
        <button
          onClick={(e) => { e.stopPropagation(); handleResetPassword(client); }}
          className="p-1.5 rounded-lg hover:bg-surface-mid text-ink-muted hover:text-ink transition-colors"
          title="Reset password"
        >
          <RefreshCw size={13} />
        </button>
        <button
          onClick={(e) => { e.stopPropagation(); handleToggleStatus(client); }}
          className={`p-1.5 rounded-lg hover:bg-surface-mid transition-colors ${
            client.status === "active" ? "text-ink-muted hover:text-danger" : "text-ink-muted hover:text-success"
          }`}
          title={client.status === "active" ? "Suspend" : "Activate"}
        >
          {client.status === "active" ? <PowerOff size={13} /> : <Power size={13} />}
        </button>
      </div>
    );
  }

  function goToClient(clientId: string) {
    router.push(`/operator/client/${clientId}`);
  }

  function handleRowKeyDown(e: React.KeyboardEvent, clientId: string) {
    if (e.target !== e.currentTarget) return;
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      goToClient(clientId);
    }
  }

  return (
    <div className="max-w-6xl mx-auto px-8 py-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-ink">Clients</h1>
          <p className="text-sm text-ink-muted mt-1">Provision and manage tenant accounts.</p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => load()}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-2 text-sm text-ink-secondary hover:text-ink border border-border rounded-lg hover:bg-surface-mid transition-colors disabled:opacity-60"
            title="Refresh"
            aria-label="Refresh clients"
          >
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} /> Refresh
          </button>

          {/* View toggle */}
          <div className="flex bg-surface-mid rounded-lg p-0.5">
            <button
              onClick={() => setView("table")}
              className={`p-2 rounded-md transition-all ${
                view === "table" ? "bg-primary text-white shadow-sm" : "text-ink-secondary hover:text-ink"
              }`}
              title="Table view"
            >
              <List size={16} />
            </button>
            <button
              onClick={() => setView("grid")}
              className={`p-2 rounded-md transition-all ${
                view === "grid" ? "bg-primary text-white shadow-sm" : "text-ink-secondary hover:text-ink"
              }`}
              title="Grid view"
            >
              <LayoutGrid size={16} />
            </button>
          </div>

          <button
            onClick={() => setShowCreate(true)}
            className="flex items-center gap-2 px-4 py-2 bg-primary text-white text-sm font-medium rounded-lg hover:bg-primary-dark transition-colors"
          >
            <Plus size={14} /> New Client
          </button>
        </div>
      </div>

      {/* System Health */}
      <SystemHealthCard health={systemHealth} operatorHealth={operatorHealth} loading={healthLoading} />

      {/* Error alert */}
      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-danger/20 rounded-lg text-sm text-danger">
          {error}
        </div>
      )}

      {/* Temp password banner */}
      {tempPw && (
        <div className="mb-4 p-4 bg-green-50 border border-success/20 rounded-lg">
          <p className="text-sm font-medium text-success">Password reset for {tempPw.name}</p>
          <div className="flex items-center gap-2 mt-1">
            <p className="text-sm text-success">Temp password:</p>
            <code className="font-mono bg-green-100 px-2 py-0.5 rounded text-success tracking-wider">
              {pwRevealed ? tempPw.pw : "•".repeat(tempPw.pw.length)}
            </code>
            <button
              onClick={() => setPwRevealed(v => !v)}
              className="p-1 rounded hover:bg-green-100 text-success transition-colors"
              title={pwRevealed ? "Hide password" : "Reveal password"}
              aria-label={pwRevealed ? "Hide password" : "Reveal password"}
            >
              {pwRevealed ? <EyeOff size={13} /> : <Eye size={13} />}
            </button>
            <button
              onClick={() => copyPw(tempPw.pw)}
              className="p-1 rounded hover:bg-green-100 text-success transition-colors"
              title="Copy password"
              aria-label="Copy password"
            >
              {pwCopied ? <Check size={13} /> : <Copy size={13} />}
            </button>
          </div>
          <button onClick={() => setTempPw(null)} className="text-xs text-success mt-2 underline">Dismiss</button>
        </div>
      )}

      {/* Reset password confirmation */}
      <ActionConfirm
        open={resetTarget !== null}
        onClose={() => setResetTarget(null)}
        onConfirm={confirmResetPassword}
        title="Reset password?"
        description={`This will generate a new temporary password for ${resetTarget?.name ?? "this client"}. Their current password will stop working immediately.`}
        confirmText="Reset"
        tone="primary"
        loading={resetLoading}
      />

      {/* Create modal */}
      {showCreate && (
        <OnboardingWizard open={showCreate} onClose={() => setShowCreate(false)} onComplete={load} />
      )}

      {/* Content */}
      {loading && clients.length === 0 ? (
        <div className="p-8 text-center text-sm text-ink-muted">Loading…</div>
      ) : clients.length === 0 ? (
        <div className="p-12 text-center">
          <p className="text-ink font-semibold">No clients yet</p>
          <p className="text-sm text-ink-muted mt-1">Create your first client to get started.</p>
        </div>
      ) : view === "grid" ? (
        /* Grid view */
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {clients.map(client => (
            <div
              key={client.id}
              role="button"
              tabIndex={0}
              aria-label={`Open client ${client.name}`}
              className="bg-white rounded-card border border-border shadow-card hover:shadow-card-hover transition-all duration-200 cursor-pointer p-5 focus:outline-none focus:ring-2 focus:ring-primary/40"
              onClick={() => goToClient(client.id)}
              onKeyDown={(e) => handleRowKeyDown(e, client.id)}
            >
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-start gap-2.5">
                  <input
                    type="checkbox"
                    checked={selectedIds.has(client.id)}
                    onClick={(e) => e.stopPropagation()}
                    onChange={(e) => { e.stopPropagation(); toggleSelected(client.id); }}
                    aria-label={`Select ${client.name}`}
                    className="mt-1 w-4 h-4 rounded border-border text-primary focus:ring-2 focus:ring-primary/40 cursor-pointer"
                  />
                  <div>
                    <h3 className="text-base font-semibold text-ink">{client.name}</h3>
                    <div className="flex items-center gap-1 mt-0.5">
                      <p className="text-xs text-ink-muted font-mono">{client.id.slice(0, 8)}&hellip;</p>
                      <button
                        onClick={(e) => { e.stopPropagation(); copyId(client.id); }}
                        className="p-0.5 rounded hover:bg-surface-mid text-ink-muted hover:text-ink transition-colors"
                        title="Copy tenant ID"
                      >
                        {copiedId === client.id ? <Check size={10} /> : <Copy size={10} />}
                      </button>
                    </div>
                  </div>
                </div>
                <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium ${
                  client.status === "active" ? "bg-green-50 text-success" : "bg-red-50 text-danger"
                }`}>
                  <span className={`w-1.5 h-1.5 rounded-full ${client.status === "active" ? "bg-success" : "bg-danger"}`} />
                  {client.status}
                </span>
              </div>
              <div className="flex flex-wrap gap-1 mb-3">
                {(client.enabled_features || []).filter(f => !f.includes(".")).map(f => (
                  <span key={f} className="px-2 py-0.5 rounded-full text-[11px] font-medium bg-primary-muted text-primary">
                    {FEATURE_LABELS[f] || f}
                  </span>
                ))}
              </div>
              <p className="text-xs text-ink-muted mb-3">Created {new Date(client.created_at).toLocaleDateString("en-IN")}</p>
              <div className="border-t border-border-subtle pt-3">
                <ActionButtons client={client} />
              </div>
            </div>
          ))}
        </div>
      ) : (
        /* Table view */
        <div className="bg-white rounded-card border border-border overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-border">
                <th className="px-5 py-3 text-left bg-surface-mid w-10">
                  <input
                    type="checkbox"
                    checked={clients.length > 0 && selectedIds.size === clients.length}
                    ref={(el) => {
                      if (el) el.indeterminate = selectedIds.size > 0 && selectedIds.size < clients.length;
                    }}
                    onChange={toggleSelectAll}
                    aria-label="Select all clients"
                    className="w-4 h-4 rounded border-border text-primary focus:ring-2 focus:ring-primary/40 cursor-pointer"
                  />
                </th>
                {["Company", "Service", "Status", "Created", "Actions"].map(h => (
                  <th key={h} className="px-5 py-3 text-left text-xs font-semibold text-ink-secondary uppercase tracking-wider bg-surface-mid">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-border-subtle">
              {clients.map(client => (
                <tr
                  key={client.id}
                  role="button"
                  tabIndex={0}
                  aria-label={`Open client ${client.name}`}
                  className="hover:bg-surface-mid/50 transition-colors cursor-pointer focus:outline-none focus:ring-2 focus:ring-inset focus:ring-primary/40"
                  onClick={() => goToClient(client.id)}
                  onKeyDown={(e) => handleRowKeyDown(e, client.id)}
                >
                  <td className="px-5 py-4" onClick={(e) => e.stopPropagation()}>
                    <input
                      type="checkbox"
                      checked={selectedIds.has(client.id)}
                      onChange={() => toggleSelected(client.id)}
                      aria-label={`Select ${client.name}`}
                      className="w-4 h-4 rounded border-border text-primary focus:ring-2 focus:ring-primary/40 cursor-pointer"
                    />
                  </td>
                  <td className="px-5 py-4">
                    <p className="text-sm font-semibold text-ink">{client.name}</p>
                    <div className="flex items-center gap-1 mt-0.5">
                      <p className="text-xs text-ink-muted font-mono">{client.id.slice(0, 8)}&hellip;</p>
                      <button
                        onClick={(e) => { e.stopPropagation(); copyId(client.id); }}
                        className="p-0.5 rounded hover:bg-surface-mid text-ink-muted hover:text-ink transition-colors"
                        title="Copy tenant ID"
                      >
                        {copiedId === client.id ? <Check size={10} /> : <Copy size={10} />}
                      </button>
                    </div>
                  </td>
                  <td className="px-5 py-4">
                    <div className="flex flex-wrap gap-1">
                      {(client.enabled_features || []).filter(f => !f.includes(".")).map(f => (
                        <span key={f} className="px-2 py-0.5 rounded-full text-[11px] font-medium bg-primary-muted text-primary">
                          {FEATURE_LABELS[f] || f}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="px-5 py-4">
                    <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium ${
                      client.status === "active" ? "bg-green-50 text-success" : "bg-red-50 text-danger"
                    }`}>
                      <span className={`w-1.5 h-1.5 rounded-full ${client.status === "active" ? "bg-success" : "bg-danger"}`} />
                      {client.status}
                    </span>
                  </td>
                  <td className="px-5 py-4 text-xs text-ink-muted">
                    {new Date(client.created_at).toLocaleDateString("en-IN")}
                  </td>
                  <td className="px-5 py-4">
                    <ActionButtons client={client} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Bulk action bar */}
      {selectedIds.size > 0 && (
        <div className="fixed inset-x-0 bottom-6 z-40 flex justify-center px-4 motion-safe:animate-in motion-safe:slide-in-from-bottom-4 motion-safe:fade-in motion-safe:duration-200">
          <div className="flex items-center gap-4 bg-ink text-white rounded-full shadow-xl pl-5 pr-3 py-2.5">
            <span className="text-sm font-medium">
              {selectedIds.size} client{selectedIds.size === 1 ? "" : "s"} selected
            </span>
            <div className="h-4 w-px bg-white/20" />
            <div className="flex items-center gap-2">
              <button
                onClick={() => requestBulkAction("suspended")}
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-full bg-white/10 hover:bg-white/20 transition-colors"
              >
                <PowerOff size={13} /> Suspend
              </button>
              <button
                onClick={() => requestBulkAction("active")}
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-full bg-white/10 hover:bg-white/20 transition-colors"
              >
                <Power size={13} /> Activate
              </button>
              <button
                onClick={clearSelection}
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-white/70 hover:text-white rounded-full hover:bg-white/10 transition-colors"
                aria-label="Clear selection"
              >
                <X size={13} /> Clear
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Bulk action confirmation */}
      <ActionConfirm
        open={bulkAction !== null}
        onClose={() => { if (!bulkRunning) setBulkAction(null); }}
        onConfirm={confirmBulkAction}
        title={
          bulkAction === "suspended"
            ? `Suspend ${selectedIds.size} client${selectedIds.size === 1 ? "" : "s"}?`
            : `Activate ${selectedIds.size} client${selectedIds.size === 1 ? "" : "s"}?`
        }
        description={
          bulkProgress
            ? `Updating ${bulkProgress.done}/${bulkProgress.total}…`
            : bulkAction === "suspended"
              ? "Suspended clients will lose access immediately. This action is applied one at a time."
              : "These clients will regain access immediately. This action is applied one at a time."
        }
        confirmText={bulkAction === "suspended" ? "Suspend" : "Activate"}
        tone={bulkAction === "suspended" ? "danger" : "primary"}
        loading={bulkRunning}
      />

      {/* Bulk action result summary */}
      {bulkSummary && (
        <div className={`fixed inset-x-0 bottom-6 z-40 flex justify-center px-4 motion-safe:animate-in motion-safe:slide-in-from-bottom-4 motion-safe:fade-in motion-safe:duration-200`}>
          <div className={`flex items-center gap-3 rounded-full shadow-xl pl-5 pr-3 py-2.5 text-sm font-medium ${
            bulkSummary.failed > 0 ? "bg-red-50 border border-danger/20 text-danger" : "bg-green-50 border border-success/20 text-success"
          }`}>
            <span>
              {bulkSummary.failed > 0
                ? `${bulkSummary.succeeded} succeeded, ${bulkSummary.failed} failed`
                : `${bulkSummary.succeeded} client${bulkSummary.succeeded === 1 ? "" : "s"} updated`}
            </span>
            <button onClick={() => setBulkSummary(null)} aria-label="Dismiss" className="hover:opacity-70">
              <X size={13} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
