"use client";
import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Plus, RefreshCw, PowerOff, Power, List, LayoutGrid, Copy, Check, Activity, Clock, Cpu, HardDrive } from "lucide-react";
import { API_URL, getAuthHeaders } from "@/lib/api";
import { OnboardingWizard } from "./components/onboarding-wizard";

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

const FEATURE_DISPLAY: Record<string, string> = {
  whatsapp: "WhatsApp",
  telecalling: "Telecalling",
  instagram: "Instagram",
  facebook: "Facebook",
  telegram: "Telegram",
};

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
  const [copiedId, setCopiedId] = useState<string | null>(null);

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
        apiFetch<OperatorHealth>("/api/v1/operator/system-health"),
      ]);
      if (healthRes.status === "fulfilled") setSystemHealth(healthRes.value);
      if (opRes.status === "fulfilled") setOperatorHealth(opRes.value);
    } catch {
      // silent — card shows stale or loading state
    } finally {
      setHealthLoading(false);
    }
  }, []);

  async function load() {
    setLoading(true);
    try {
      const res = await apiFetch<{ data: Client[] }>("/api/v1/operator/clients");
      setClients(res.data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); loadHealth(); }, [loadHealth]);

  // Auto-refresh health every 60s
  useEffect(() => {
    const id = setInterval(loadHealth, 60_000);
    return () => clearInterval(id);
  }, [loadHealth]);

  async function handleToggleStatus(client: Client) {
    const newStatus = client.status === "active" ? "suspended" : "active";
    try {
      await apiFetch(`/api/v1/operator/clients/${client.id}/status`, {
        method: "PATCH",
        body: JSON.stringify({ status: newStatus }),
      });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update status");
    }
  }

  async function handleResetPassword(client: Client) {
    if (!confirm(`Reset password for ${client.name}?`)) return;
    try {
      const res = await apiFetch<{ temp_password: string }>(
        `/api/v1/operator/clients/${client.id}/reset-password`,
        { method: "POST" }
      );
      setTempPw({ name: client.name, pw: res.temp_password });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to reset password");
    }
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

  return (
    <div className="max-w-6xl mx-auto px-8 py-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-ink">Clients</h1>
          <p className="text-sm text-ink-muted mt-1">Provision and manage tenant accounts.</p>
        </div>
        <div className="flex items-center gap-3">
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
          <p className="text-sm text-success mt-1">
            Temp password: <code className="font-mono bg-green-100 px-2 py-0.5 rounded">{tempPw.pw}</code>
          </p>
          <button onClick={() => setTempPw(null)} className="text-xs text-success mt-2 underline">Dismiss</button>
        </div>
      )}

      {/* Create modal */}
      {showCreate && (
        <OnboardingWizard open={showCreate} onClose={() => setShowCreate(false)} onComplete={load} />
      )}

      {/* Content */}
      {loading ? (
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
              className="bg-white rounded-card border border-border shadow-card hover:shadow-card-hover transition-all duration-200 cursor-pointer p-5"
              onClick={() => router.push(`/operator/client/${client.id}`)}
            >
              <div className="flex items-start justify-between mb-3">
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
                {["Company", "Service", "Status", "Created", "Actions"].map(h => (
                  <th key={h} className="px-5 py-3 text-left text-xs font-semibold text-ink-secondary uppercase tracking-wider bg-surface-mid">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-border-subtle">
              {clients.map(client => (
                <tr
                  key={client.id}
                  className="hover:bg-surface-mid/50 transition-colors cursor-pointer"
                  onClick={() => router.push(`/operator/client/${client.id}`)}
                >
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
    </div>
  );
}
