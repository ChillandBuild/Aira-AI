"use client";
import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft, Users, MessageSquare, Activity, Clock,
  CheckCircle2, XCircle, AlertTriangle,
  Key, Trash2, PowerOff, Power,
} from "lucide-react";
import { API_URL, getAuthHeaders } from "@/lib/api";

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

const ALL_FEATURES = ["whatsapp", "telecalling", "instagram", "facebook", "telegram"] as const;
const FEATURE_LABELS: Record<string, string> = {
  whatsapp: "WhatsApp",
  telecalling: "Telecalling",
  instagram: "Instagram",
  facebook: "Facebook",
  telegram: "Telegram",
};

type Tab = "overview" | "config" | "health" | "management";

interface OverviewData {
  tenant: { id: string; name: string; status: string; enabled_features: string[]; created_at: string; plan: string };
  owner: { user_id: string | null; email: string | null; created_at: string | null };
  stats: {
    total_leads: number; active_leads: number;
    messages_sent_30d: number; messages_received_30d: number;
    team_members: number; last_activity: string | null;
  };
}

interface ConfigData {
  enabled_features: string[];
  credentials_status: Record<string, "configured" | "incomplete" | "not_configured">;
  settings: {
    ai_auto_reply_enabled: boolean; reengagement_enabled: boolean;
    booking_event_name: string | null; booking_ref_prefix: string | null;
    booking_amount_paise: string | null;
  };
}

interface HealthData {
  channels: Record<string, { status: string; last_inbound: string | null }>;
  token_status: "valid" | "expired" | "not_set";
  delivery_7d: { sent: number; delivered: number; failed: number; success_rate: number };
  recent_errors: { message_id: string; error: string | null; created_at: string }[];
  open_incidents: { id: string; type: string; severity: string; message: string; created_at: string }[];
}

interface CallerInfo {
  id: string; name: string; active: boolean; overall_score: number;
  shift_start_hour: number | null; shift_end_hour: number | null; role: string;
}

interface TeamData {
  owner: { user_id: string | null; email: string | null; created_at: string | null };
  callers: CallerInfo[];
}

export default function ClientDetailPage() {
  const { id: tenantId } = useParams<{ id: string }>();
  const router = useRouter();
  const [tab, setTab] = useState<Tab>("overview");
  const [overview, setOverview] = useState<OverviewData | null>(null);
  const [config, setConfig] = useState<ConfigData | null>(null);
  const [health, setHealth] = useState<HealthData | null>(null);
  const [team, setTeam] = useState<TeamData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [featureUpdating, setFeatureUpdating] = useState(false);
  const [tempPw, setTempPw] = useState<string | null>(null);

  const loadOverview = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiFetch<OverviewData>(`/api/v1/operator/clients/${tenantId}/overview`);
      setOverview(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, [tenantId]);

  const loadConfig = useCallback(async () => {
    try {
      const data = await apiFetch<ConfigData>(`/api/v1/operator/clients/${tenantId}/config`);
      setConfig(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load config");
    }
  }, [tenantId]);

  const loadHealth = useCallback(async () => {
    try {
      const data = await apiFetch<HealthData>(`/api/v1/operator/clients/${tenantId}/health`);
      setHealth(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load health");
    }
  }, [tenantId]);

  const loadTeam = useCallback(async () => {
    try {
      const data = await apiFetch<TeamData>(`/api/v1/operator/clients/${tenantId}/team`);
      setTeam(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load team");
    }
  }, [tenantId]);

  useEffect(() => { loadOverview(); }, [loadOverview]);

  useEffect(() => {
    if (tab === "config" && !config) loadConfig();
    if (tab === "health" && !health) loadHealth();
    if (tab === "management" && !team) loadTeam();
  }, [tab, config, health, team, loadConfig, loadHealth, loadTeam]);

  async function toggleFeature(feature: string) {
    if (!config) return;
    setFeatureUpdating(true);
    const current = config.enabled_features;
    const updated = current.includes(feature)
      ? current.filter(f => f !== feature)
      : [...current, feature];
    try {
      await apiFetch(`/api/v1/operator/clients/${tenantId}/features`, {
        method: "PATCH",
        body: JSON.stringify({ features: updated }),
      });
      setConfig({ ...config, enabled_features: updated });
      if (overview) {
        setOverview({ ...overview, tenant: { ...overview.tenant, enabled_features: updated } });
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update features");
    } finally {
      setFeatureUpdating(false);
    }
  }

  async function handleResetPassword() {
    if (!confirm("Reset owner password?")) return;
    try {
      const res = await apiFetch<{ temp_password: string }>(`/api/v1/operator/clients/${tenantId}/reset-password`, { method: "POST" });
      setTempPw(res.temp_password);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to reset password");
    }
  }

  async function handleToggleStatus() {
    if (!overview) return;
    const newStatus = overview.tenant.status === "active" ? "suspended" : "active";
    if (!confirm(`${newStatus === "suspended" ? "Suspend" : "Activate"} ${overview.tenant.name}?`)) return;
    try {
      await apiFetch(`/api/v1/operator/clients/${tenantId}/status`, {
        method: "PATCH",
        body: JSON.stringify({ status: newStatus }),
      });
      setOverview({ ...overview, tenant: { ...overview.tenant, status: newStatus } });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update status");
    }
  }

  async function handleWipeLeads() {
    if (!overview) return;
    if (!confirm(`⚠️ Wipe ALL leads for "${overview.tenant.name}"?\n\nThis permanently deletes every lead, message, note, and handover. Cannot be undone.`)) return;
    if (!confirm(`Second confirmation: permanently delete all leads for "${overview.tenant.name}"?`)) return;
    try {
      const res = await apiFetch<{ deleted: number }>(`/api/v1/operator/clients/${tenantId}/wipe-leads`, { method: "POST" });
      alert(`Wiped ${res.deleted} leads.`);
      loadOverview();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Wipe failed");
    }
  }

  if (loading && !overview) {
    return <div className="p-12 text-center text-sm text-gray-400">Loading…</div>;
  }

  const tenant = overview?.tenant;
  const tabs: { key: Tab; label: string }[] = [
    { key: "overview", label: "Overview" },
    { key: "config", label: "Configuration" },
    { key: "health", label: "Health" },
    { key: "management", label: "Management" },
  ];

  return (
    <div>
      {/* Breadcrumb */}
      <button onClick={() => router.push("/operator")} className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-800 mb-4">
        <ArrowLeft size={14} /> Clients
      </button>

      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">{error}
          <button onClick={() => setError(null)} className="ml-2 underline text-xs">dismiss</button>
        </div>
      )}

      {tempPw && (
        <div className="mb-4 p-4 bg-green-50 border border-green-200 rounded-lg">
          <p className="text-sm font-medium text-green-800">Password reset</p>
          <p className="text-sm text-green-700 mt-1">Temp password: <code className="font-mono bg-green-100 px-2 py-0.5 rounded">{tempPw}</code></p>
          <button onClick={() => setTempPw(null)} className="text-xs text-green-600 mt-2 underline">Dismiss</button>
        </div>
      )}

      {/* Header */}
      {tenant && (
        <div className="bg-white rounded-2xl border border-gray-200 p-6 mb-6">
          <div className="flex items-start justify-between">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">{tenant.name}</h1>
              <p className="text-xs text-gray-400 font-mono mt-1">{tenant.id}
                <button onClick={() => navigator.clipboard.writeText(tenant.id)} className="ml-2 text-gray-300 hover:text-gray-500" title="Copy ID">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>
                </button>
              </p>
              {overview?.owner?.email && (
                <p className="text-sm text-gray-500 mt-2">Owner: {overview.owner.email}</p>
              )}
              <p className="text-xs text-gray-400 mt-1">Created {new Date(tenant.created_at).toLocaleDateString("en-IN")}</p>
            </div>
            <div className="flex items-center gap-2">
              <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${tenant.status === "active" ? "bg-green-50 text-green-700" : "bg-red-50 text-red-600"}`}>
                {tenant.status}
              </span>
              {(tenant.enabled_features || []).map((f: string) => (
                <span key={f} className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-indigo-50 text-indigo-700">
                  {FEATURE_LABELS[f] || f}
                </span>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 mb-6 border-b border-gray-200">
        {tabs.map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-px ${tab === t.key ? "border-indigo-600 text-indigo-700" : "border-transparent text-gray-500 hover:text-gray-700"}`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {tab === "overview" && overview && (
        <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
          <StatCard icon={<Users size={18} />} label="Total Leads" value={overview.stats.total_leads} />
          <StatCard icon={<Activity size={18} />} label="Active Leads (A+B)" value={overview.stats.active_leads} />
          <StatCard icon={<MessageSquare size={18} />} label="Msgs Sent (30d)" value={overview.stats.messages_sent_30d} />
          <StatCard icon={<MessageSquare size={18} />} label="Msgs Received (30d)" value={overview.stats.messages_received_30d} />
          <StatCard icon={<Users size={18} />} label="Team Members" value={overview.stats.team_members} />
          <StatCard icon={<Clock size={18} />} label="Last Activity" value={overview.stats.last_activity ? relTime(overview.stats.last_activity) : "—"} />
        </div>
      )}

      {tab === "config" && config && (
        <div className="space-y-6">
          {/* Feature Toggles */}
          <div className="bg-white rounded-2xl border border-gray-200 p-6">
            <h2 className="text-sm font-bold text-gray-700 mb-4">Feature Toggles</h2>
            <div className="space-y-3">
              {ALL_FEATURES.map(f => (
                <div key={f} className="flex items-center justify-between py-2 px-3 rounded-lg hover:bg-gray-50">
                  <span className="text-sm font-medium text-gray-800">{FEATURE_LABELS[f]}</span>
                  <button
                    disabled={featureUpdating}
                    onClick={() => toggleFeature(f)}
                    className={`relative w-11 h-6 rounded-full transition-colors ${config.enabled_features.includes(f) ? "bg-indigo-600" : "bg-gray-200"} ${featureUpdating ? "opacity-50" : ""}`}
                  >
                    <span className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full transition-transform shadow-sm ${config.enabled_features.includes(f) ? "translate-x-5" : ""}`} />
                  </button>
                </div>
              ))}
            </div>
          </div>

          {/* Credential Status */}
          <div className="bg-white rounded-2xl border border-gray-200 p-6">
            <h2 className="text-sm font-bold text-gray-700 mb-4">Channel Credentials</h2>
            <div className="grid grid-cols-2 gap-3">
              {(["whatsapp", "telecalling", "ai", "payments"] as const).map(ch => {
                const status = config.credentials_status[ch];
                const labels: Record<string, string> = { whatsapp: "WhatsApp (Meta)", telecalling: "Telecalling (TeleCMI)", ai: "AI (Groq)", payments: "Payments (Razorpay)" };
                return (
                  <div key={ch} className="flex items-center gap-3 p-3 rounded-lg border border-gray-100">
                    {status === "configured" ? <CheckCircle2 size={16} className="text-green-600" /> : status === "incomplete" ? <AlertTriangle size={16} className="text-amber-500" /> : <XCircle size={16} className="text-gray-300" />}
                    <div>
                      <p className="text-sm font-medium text-gray-800">{labels[ch]}</p>
                      <p className={`text-xs ${status === "configured" ? "text-green-600" : status === "incomplete" ? "text-amber-500" : "text-gray-400"}`}>
                        {status === "configured" ? "Configured" : status === "incomplete" ? "Incomplete" : "Not configured"}
                      </p>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Key Settings */}
          <div className="bg-white rounded-2xl border border-gray-200 p-6">
            <h2 className="text-sm font-bold text-gray-700 mb-4">Key Settings</h2>
            <dl className="space-y-2">
              <SettingRow label="AI Auto-Reply" value={config.settings.ai_auto_reply_enabled ? "Enabled" : "Disabled"} ok={config.settings.ai_auto_reply_enabled} />
              <SettingRow label="Re-engagement" value={config.settings.reengagement_enabled ? "Enabled" : "Disabled"} ok={config.settings.reengagement_enabled} />
              <SettingRow label="Booking Event" value={config.settings.booking_event_name || "Not set"} ok={!!config.settings.booking_event_name} />
            </dl>
          </div>
        </div>
      )}

      {tab === "health" && health && (
        <div className="space-y-6">
          {/* Channel Health */}
          <div className="bg-white rounded-2xl border border-gray-200 p-6">
            <h2 className="text-sm font-bold text-gray-700 mb-4">Channel Health</h2>
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
              {Object.entries(health.channels).map(([ch, info]) => (
                <div key={ch} className={`p-4 rounded-xl border ${info.status === "healthy" ? "border-green-200" : info.status === "unhealthy" ? "border-red-200" : "border-gray-100"}`}>
                  <p className="text-sm font-semibold text-gray-800 capitalize">{ch}</p>
                  <p className={`text-xs mt-1 ${info.status === "healthy" ? "text-green-600" : info.status === "unhealthy" ? "text-red-500" : "text-gray-400"}`}>
                    {info.status === "healthy" ? "Healthy" : info.status === "unhealthy" ? "Unhealthy" : "Not configured"}
                  </p>
                  {info.last_inbound && <p className="text-[11px] text-gray-400 mt-1">Last inbound: {relTime(info.last_inbound)}</p>}
                </div>
              ))}
            </div>
          </div>

          {/* Token + Delivery */}
          <div className="grid grid-cols-2 gap-4">
            <div className="bg-white rounded-2xl border border-gray-200 p-6">
              <h2 className="text-sm font-bold text-gray-700 mb-3">Meta Token</h2>
              <div className="flex items-center gap-2">
                {health.token_status === "valid" ? <CheckCircle2 size={16} className="text-green-600" /> : health.token_status === "expired" ? <XCircle size={16} className="text-red-500" /> : <AlertTriangle size={16} className="text-gray-300" />}
                <span className={`text-sm font-medium ${health.token_status === "valid" ? "text-green-700" : health.token_status === "expired" ? "text-red-600" : "text-gray-400"}`}>
                  {health.token_status === "valid" ? "Valid" : health.token_status === "expired" ? "Expired" : "Not set"}
                </span>
              </div>
            </div>
            <div className="bg-white rounded-2xl border border-gray-200 p-6">
              <h2 className="text-sm font-bold text-gray-700 mb-3">Delivery (7 days)</h2>
              <div className="flex gap-4 text-sm">
                <div><p className="text-gray-400 text-xs">Sent</p><p className="font-semibold text-gray-900">{health.delivery_7d.sent}</p></div>
                <div><p className="text-gray-400 text-xs">Delivered</p><p className="font-semibold text-green-700">{health.delivery_7d.delivered}</p></div>
                <div><p className="text-gray-400 text-xs">Failed</p><p className="font-semibold text-red-600">{health.delivery_7d.failed}</p></div>
                <div><p className="text-gray-400 text-xs">Rate</p><p className="font-semibold text-gray-900">{health.delivery_7d.success_rate}%</p></div>
              </div>
            </div>
          </div>

          {/* Recent Errors */}
          {health.recent_errors.length > 0 && (
            <div className="bg-white rounded-2xl border border-gray-200 p-6">
              <h2 className="text-sm font-bold text-gray-700 mb-3">Recent Delivery Errors</h2>
              <div className="divide-y divide-gray-100">
                {health.recent_errors.map(e => (
                  <div key={e.message_id} className="py-2 flex justify-between text-xs">
                    <span className="text-gray-600 truncate max-w-[70%]">{e.error || "Unknown error"}</span>
                    <span className="text-gray-400">{relTime(e.created_at)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Open Incidents */}
          {health.open_incidents.length > 0 && (
            <div className="bg-white rounded-2xl border border-gray-200 p-6">
              <h2 className="text-sm font-bold text-gray-700 mb-3">Incidents</h2>
              <div className="divide-y divide-gray-100">
                {health.open_incidents.map(inc => (
                  <div key={inc.id} className="py-2 flex justify-between text-xs">
                    <div>
                      <span className="font-medium text-gray-700">{inc.type}</span>
                      <span className="text-gray-400 ml-2">{inc.message}</span>
                    </div>
                    <span className="text-gray-400">{relTime(inc.created_at)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {tab === "management" && team && (
        <div className="space-y-6">
          {/* Actions */}
          <div className="bg-white rounded-2xl border border-gray-200 p-6">
            <h2 className="text-sm font-bold text-gray-700 mb-4">Actions</h2>
            <div className="flex flex-wrap gap-3">
              <button onClick={handleResetPassword} className="flex items-center gap-2 px-4 py-2 border border-gray-200 rounded-lg text-sm text-gray-700 hover:bg-gray-50">
                <Key size={14} /> Reset Owner Password
              </button>
              <button onClick={handleToggleStatus} className={`flex items-center gap-2 px-4 py-2 border rounded-lg text-sm ${overview?.tenant.status === "active" ? "border-red-200 text-red-600 hover:bg-red-50" : "border-green-200 text-green-700 hover:bg-green-50"}`}>
                {overview?.tenant.status === "active" ? <><PowerOff size={14} /> Suspend</> : <><Power size={14} /> Activate</>}
              </button>
              <button onClick={handleWipeLeads} className="flex items-center gap-2 px-4 py-2 border border-red-200 rounded-lg text-sm text-red-600 hover:bg-red-50">
                <Trash2 size={14} /> Wipe All Leads
              </button>
            </div>
          </div>

          {/* Owner Info */}
          <div className="bg-white rounded-2xl border border-gray-200 p-6">
            <h2 className="text-sm font-bold text-gray-700 mb-3">Owner</h2>
            <dl className="space-y-1 text-sm">
              <div className="flex gap-2"><dt className="text-gray-400 w-24">Email</dt><dd className="text-gray-800">{team.owner.email || "—"}</dd></div>
              <div className="flex gap-2"><dt className="text-gray-400 w-24">User ID</dt><dd className="text-gray-800 font-mono text-xs">{team.owner.user_id || "—"}</dd></div>
              <div className="flex gap-2"><dt className="text-gray-400 w-24">Since</dt><dd className="text-gray-800">{team.owner.created_at ? new Date(team.owner.created_at).toLocaleDateString("en-IN") : "—"}</dd></div>
            </dl>
          </div>

          {/* Team Members */}
          <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-100">
              <h2 className="text-sm font-bold text-gray-700">Team Members ({team.callers.length})</h2>
            </div>
            {team.callers.length === 0 ? (
              <p className="p-6 text-sm text-gray-400 text-center">No team members</p>
            ) : (
              <table className="w-full">
                <thead>
                  <tr className="border-b border-gray-100">
                    {["Name", "Role", "Active", "Score", "Shift"].map(h => (
                      <th key={h} className="px-5 py-2 text-left text-xs font-semibold text-gray-400 uppercase tracking-wider">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {team.callers.map(c => (
                    <tr key={c.id}>
                      <td className="px-5 py-3 text-sm font-medium text-gray-900">{c.name}</td>
                      <td className="px-5 py-3">
                        <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${c.role === "owner" ? "bg-purple-50 text-purple-700" : "bg-gray-100 text-gray-600"}`}>
                          {c.role}
                        </span>
                      </td>
                      <td className="px-5 py-3">
                        <span className={`w-2 h-2 rounded-full inline-block ${c.active ? "bg-green-500" : "bg-gray-300"}`} />
                      </td>
                      <td className="px-5 py-3 text-sm text-gray-700">{c.overall_score?.toFixed(1) ?? "—"}</td>
                      <td className="px-5 py-3 text-xs text-gray-400">
                        {c.shift_start_hour != null && c.shift_end_hour != null ? `${c.shift_start_hour}:00 – ${c.shift_end_hour}:00` : "Default"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function StatCard({ icon, label, value }: { icon: React.ReactNode; label: string; value: string | number }) {
  return (
    <div className="bg-white rounded-2xl border border-gray-200 p-5">
      <div className="flex items-center gap-2 text-gray-400 mb-2">{icon}<span className="text-xs font-medium uppercase tracking-wider">{label}</span></div>
      <p className="text-2xl font-bold text-gray-900">{typeof value === "number" ? value.toLocaleString() : value}</p>
    </div>
  );
}

function SettingRow({ label, value, ok }: { label: string; value: string; ok: boolean }) {
  return (
    <div className="flex items-center justify-between py-1.5">
      <dt className="text-sm text-gray-500">{label}</dt>
      <dd className={`text-sm font-medium ${ok ? "text-green-700" : "text-gray-400"}`}>{value}</dd>
    </div>
  );
}

function relTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const s = Math.abs(diff) / 1000;
  if (s < 60) return `${Math.round(s)}s ago`;
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
}
