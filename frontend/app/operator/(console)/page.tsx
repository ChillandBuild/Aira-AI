"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Plus, RefreshCw, PowerOff, Power, Trash2, List, LayoutGrid, Copy, Check } from "lucide-react";
import { API_URL, getAuthHeaders } from "@/lib/api";

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

const ALL_FEATURES = ["whatsapp", "telecalling", "instagram", "facebook", "telegram"] as const;

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

export default function OperatorPage() {
  const router = useRouter();
  const [clients, setClients] = useState<Client[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tempPw, setTempPw] = useState<{ name: string; pw: string } | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const [companyName, setCompanyName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [features, setFeatures] = useState<string[]>(["whatsapp", "telecalling"]);
  const [submitting, setSubmitting] = useState(false);

  const [view, setView] = useState<"grid" | "table">(() => {
    if (typeof window !== "undefined") {
      return (localStorage.getItem("operator-clients-view") as "grid" | "table") || "grid";
    }
    return "grid";
  });

  useEffect(() => {
    localStorage.setItem("operator-clients-view", view);
  }, [view]);

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

  useEffect(() => { load(); }, []);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await apiFetch("/api/v1/operator/clients", {
        method: "POST",
        body: JSON.stringify({ company_name: companyName, email, password, features }),
      });
      setShowCreate(false);
      setCompanyName(""); setEmail(""); setPassword(""); setFeatures(["whatsapp", "telecalling"]);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create client");
    } finally {
      setSubmitting(false);
    }
  }

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

  async function handleWipeLeads(client: Client) {
    if (!confirm(`⚠️ Wipe ALL leads for "${client.name}"?\n\nThis permanently deletes every lead, message, note, and handover for this client. This cannot be undone.`)) return;
    if (!confirm(`Second confirmation: permanently delete all leads for "${client.name}"?`)) return;
    try {
      const res = await apiFetch<{ deleted: number }>(`/api/v1/operator/clients/${client.id}/wipe-leads`, { method: "POST" });
      setError(null);
      alert(`Wiped ${res.deleted} leads for ${client.name}.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Wipe failed");
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
        <button
          onClick={(e) => { e.stopPropagation(); handleWipeLeads(client); }}
          className="p-1.5 rounded-lg hover:bg-red-50 text-ink-muted hover:text-danger transition-colors"
          title="Wipe all leads"
        >
          <Trash2 size={13} />
        </button>
      </div>
    );
  }

  return (
    <div>
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
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-card shadow-xl w-full max-w-md p-6">
            <h2 className="text-lg font-bold text-ink mb-4">New Client</h2>
            <form onSubmit={handleCreate} className="space-y-3">
              <div>
                <label className="text-sm font-medium text-ink-secondary block mb-1">Company Name *</label>
                <input
                  value={companyName} onChange={e => setCompanyName(e.target.value)} required
                  className="w-full border border-border rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
                  placeholder="ABC Coaching"
                />
              </div>
              <div>
                <label className="text-sm font-medium text-ink-secondary block mb-1">Owner Email *</label>
                <input
                  type="email" value={email} onChange={e => setEmail(e.target.value)} required
                  className="w-full border border-border rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
                  placeholder="owner@client.com"
                />
              </div>
              <div>
                <label className="text-sm font-medium text-ink-secondary block mb-1">Temporary Password *</label>
                <input
                  type="text" value={password} onChange={e => setPassword(e.target.value)} required
                  className="w-full border border-border rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
                  placeholder="Aira@123456"
                />
              </div>
              <div>
                <label className="text-sm font-medium text-ink-secondary block mb-2">Features</label>
                <div className="flex flex-wrap gap-2">
                  {ALL_FEATURES.map(f => (
                    <button
                      key={f}
                      type="button"
                      onClick={() => setFeatures(prev => prev.includes(f) ? prev.filter(x => x !== f) : [...prev, f])}
                      className={`px-3 py-1.5 rounded-full text-xs font-medium transition-all ${
                        features.includes(f)
                          ? "bg-primary text-white shadow-sm"
                          : "bg-surface-mid text-ink-secondary hover:text-ink"
                      }`}
                    >
                      {FEATURE_DISPLAY[f]}
                    </button>
                  ))}
                </div>
              </div>
              <div className="flex gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowCreate(false)}
                  className="flex-1 px-4 py-2 border border-border text-sm text-ink-secondary rounded-lg hover:bg-surface-mid transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="flex-1 px-4 py-2 bg-primary text-white text-sm font-medium rounded-lg hover:bg-primary-dark disabled:opacity-50 transition-colors"
                >
                  {submitting ? "Creating…" : "Create"}
                </button>
              </div>
            </form>
          </div>
        </div>
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
