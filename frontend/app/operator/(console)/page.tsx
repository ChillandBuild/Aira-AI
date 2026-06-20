"use client";
import { useEffect, useState } from "react";
import { Plus, Pencil, RefreshCw, PowerOff, Power, Trash2 } from "lucide-react";
import { API_URL, getAuthHeaders } from "@/lib/api";

type ServiceTier =
  | "whatsapp_only"
  | "telecalling_only"
  | "combined"
  | "whatsapp_instagram"
  | "whatsapp_facebook"
  | "whatsapp_telegram"
  | "omnichannel"
  | "omnichannel_telecalling";

type Client = {
  id: string;
  name: string;
  enabled_features: string[];
  status: string;
  created_at: string;
  owner_user_id: string | null;
};

const SERVICE_LABELS: Record<ServiceTier, string> = {
  whatsapp_only:           "WhatsApp Only",
  telecalling_only:        "Telecalling Only",
  combined:                "WhatsApp + Telecalling",
  whatsapp_instagram:      "WhatsApp + Instagram",
  whatsapp_facebook:       "WhatsApp + Facebook",
  whatsapp_telegram:       "WhatsApp + Telegram",
  omnichannel:             "Omnichannel (WA + IG + FB + TG)",
  omnichannel_telecalling: "Omnichannel + Telecalling",
};

function featuresToService(features: string[]): ServiceTier {
  const has = (f: string) => features.includes(f);
  const wa = has("whatsapp"), tc = has("telecalling");
  const ig = has("instagram"), fb = has("facebook"), tg = has("telegram");
  if (wa && tc && ig && fb && tg) return "omnichannel_telecalling";
  if (wa && ig && fb && tg)       return "omnichannel";
  if (wa && ig)                   return "whatsapp_instagram";
  if (wa && fb)                   return "whatsapp_facebook";
  if (wa && tg)                   return "whatsapp_telegram";
  if (wa && tc)                   return "combined";
  if (wa)                         return "whatsapp_only";
  if (tc)                         return "telecalling_only";
  return "combined";
}

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
  const [clients, setClients] = useState<Client[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [editClient, setEditClient] = useState<Client | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tempPw, setTempPw] = useState<{ name: string; pw: string } | null>(null);

  const [companyName, setCompanyName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [service, setService] = useState<ServiceTier>("combined");
  const [submitting, setSubmitting] = useState(false);

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
        body: JSON.stringify({ company_name: companyName, email, password, service }),
      });
      setShowCreate(false);
      setCompanyName(""); setEmail(""); setPassword(""); setService("combined");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create client");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleUpdateService(tenantId: string, newService: ServiceTier) {
    try {
      await apiFetch(`/api/v1/operator/clients/${tenantId}/features`, {
        method: "PATCH",
        body: JSON.stringify({ service: newService }),
      });
      setEditClient(null);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update");
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

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Clients</h1>
          <p className="text-sm text-gray-500 mt-1">Provision and manage tenant accounts.</p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700 transition-colors"
        >
          <Plus size={14} /> New Client
        </button>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">{error}</div>
      )}

      {tempPw && (
        <div className="mb-4 p-4 bg-green-50 border border-green-200 rounded-lg">
          <p className="text-sm font-medium text-green-800">Password reset for {tempPw.name}</p>
          <p className="text-sm text-green-700 mt-1">
            Temp password: <code className="font-mono bg-green-100 px-2 py-0.5 rounded">{tempPw.pw}</code>
          </p>
          <button onClick={() => setTempPw(null)} className="text-xs text-green-600 mt-2 underline">Dismiss</button>
        </div>
      )}

      {showCreate && (
        <div className="fixed inset-0 bg-black/30 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-md p-6">
            <h2 className="text-lg font-bold text-gray-900 mb-4">New Client</h2>
            <form onSubmit={handleCreate} className="space-y-3">
              <div>
                <label className="text-sm font-medium text-gray-700 block mb-1">Company Name *</label>
                <input
                  value={companyName} onChange={e => setCompanyName(e.target.value)} required
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  placeholder="ABC Coaching"
                />
              </div>
              <div>
                <label className="text-sm font-medium text-gray-700 block mb-1">Owner Email *</label>
                <input
                  type="email" value={email} onChange={e => setEmail(e.target.value)} required
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  placeholder="owner@client.com"
                />
              </div>
              <div>
                <label className="text-sm font-medium text-gray-700 block mb-1">Temporary Password *</label>
                <input
                  type="text" value={password} onChange={e => setPassword(e.target.value)} required
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  placeholder="Aira@123456"
                />
              </div>
              <div>
                <label className="text-sm font-medium text-gray-700 block mb-1">Service</label>
                <select
                  value={service} onChange={e => setService(e.target.value as ServiceTier)}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                >
                  {(Object.entries(SERVICE_LABELS) as [ServiceTier, string][]).map(([value, label]) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </select>
              </div>
              <div className="flex gap-2 pt-2">
                <button type="button" onClick={() => setShowCreate(false)} className="flex-1 px-4 py-2 border border-gray-200 text-sm text-gray-700 rounded-lg hover:bg-gray-50">Cancel</button>
                <button type="submit" disabled={submitting} className="flex-1 px-4 py-2 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700 disabled:opacity-50">
                  {submitting ? "Creating…" : "Create"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {editClient && (
        <div className="fixed inset-0 bg-black/30 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-sm p-6">
            <h2 className="text-lg font-bold text-gray-900 mb-1">Edit Service</h2>
            <p className="text-sm text-gray-500 mb-4">{editClient.name}</p>
            <div className="space-y-2">
              {(Object.entries(SERVICE_LABELS) as [ServiceTier, string][]).map(([tier, label]) => (
                <button
                  key={tier}
                  onClick={() => handleUpdateService(editClient.id, tier)}
                  className="w-full text-left px-4 py-3 rounded-lg border border-gray-200 text-sm hover:border-indigo-400 hover:bg-indigo-50 transition-colors"
                >
                  {label}
                </button>
              ))}
            </div>
            <button onClick={() => setEditClient(null)} className="mt-4 w-full text-sm text-gray-500 hover:text-gray-700">Cancel</button>
          </div>
        </div>
      )}

      <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-sm text-gray-400">Loading…</div>
        ) : clients.length === 0 ? (
          <div className="p-12 text-center">
            <p className="text-gray-900 font-semibold">No clients yet</p>
            <p className="text-sm text-gray-400 mt-1">Create your first client to get started.</p>
          </div>
        ) : (
          <table className="w-full">
            <thead>
              <tr className="border-b border-gray-100">
                {["Company", "Service", "Status", "Created", "Actions"].map(h => (
                  <th key={h} className="px-5 py-3 text-left text-xs font-semibold text-gray-400 uppercase tracking-wider">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {clients.map(client => (
                <tr key={client.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-5 py-4">
                    <p className="text-sm font-semibold text-gray-900">{client.name}</p>
                    <p className="text-xs text-gray-400">{client.id.slice(0, 8)}…</p>
                  </td>
                  <td className="px-5 py-4">
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-indigo-50 text-indigo-700">
                      {SERVICE_LABELS[featuresToService(client.enabled_features)] ?? "Custom"}
                    </span>
                  </td>
                  <td className="px-5 py-4">
                    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${client.status === "active" ? "bg-green-50 text-green-700" : "bg-red-50 text-red-600"}`}>
                      {client.status}
                    </span>
                  </td>
                  <td className="px-5 py-4 text-xs text-gray-400">
                    {new Date(client.created_at).toLocaleDateString("en-IN")}
                  </td>
                  <td className="px-5 py-4">
                    <div className="flex items-center gap-2">
                      <button onClick={() => setEditClient(client)} className="p-1.5 rounded hover:bg-gray-100 text-gray-400 hover:text-gray-700" title="Edit service">
                        <Pencil size={13} />
                      </button>
                      <button onClick={() => handleResetPassword(client)} className="p-1.5 rounded hover:bg-gray-100 text-gray-400 hover:text-gray-700" title="Reset password">
                        <RefreshCw size={13} />
                      </button>
                      <button
                        onClick={() => handleToggleStatus(client)}
                        className={`p-1.5 rounded hover:bg-gray-100 ${client.status === "active" ? "text-gray-400 hover:text-red-500" : "text-gray-400 hover:text-green-600"}`}
                        title={client.status === "active" ? "Suspend" : "Activate"}
                      >
                        {client.status === "active" ? <PowerOff size={13} /> : <Power size={13} />}
                      </button>
                      <button
                        onClick={() => handleWipeLeads(client)}
                        className="p-1.5 rounded hover:bg-red-50 text-gray-300 hover:text-red-600 transition-colors"
                        title="Wipe all leads"
                      >
                        <Trash2 size={13} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
