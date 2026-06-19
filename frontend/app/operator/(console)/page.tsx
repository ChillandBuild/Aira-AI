"use client";
import { useEffect, useState } from "react";
import { Plus, Pencil, RefreshCw, PowerOff, Power } from "lucide-react";
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
  const [filteredClients, setFilteredClients] = useState<Client[]>([]);
  const [search, setSearch] = useState("");
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
      setFilteredClients(res.data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  useEffect(() => {
    if (!search) {
      setFilteredClients(clients);
      return;
    }
    const q = search.toLowerCase();
    setFilteredClients(clients.filter(c => c.name.toLowerCase().includes(q) || c.id.toLowerCase().includes(q)));
  }, [search, clients]);

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

  return (
    <div>
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold text-white tracking-tight">Clients</h1>
          <p className="text-sm text-slate-400 mt-1">Provision and manage tenant accounts on the Aira AI platform.</p>
        </div>
        <div className="flex items-center gap-4">
          <div className="relative">
            <input
              type="text"
              placeholder="Search clients..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-64 bg-white/[0.04] border border-white/[0.08] rounded-xl pl-10 pr-4 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/50"
            />
            <div className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
            </div>
          </div>
          <button
            onClick={() => setShowCreate(true)}
            className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-cyan-500 via-emerald-500 to-violet-500 text-white text-sm font-semibold rounded-xl hover:shadow-[0_0_15px_rgba(16,185,129,0.3)] transition-all duration-300"
          >
            <Plus size={16} /> New Client
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-6 p-4 bg-red-500/[0.06] border border-red-500/20 rounded-xl text-sm text-red-400 backdrop-blur-md">
          {error}
        </div>
      )}

      {tempPw && (
        <div className="mb-6 p-4 bg-emerald-500/[0.06] border border-emerald-500/20 rounded-xl backdrop-blur-md">
          <p className="text-sm font-medium text-emerald-400">Password reset for {tempPw.name}</p>
          <p className="text-sm text-emerald-300 mt-2 flex items-center gap-2">
            Temp password: 
            <code className="font-mono bg-black/30 px-3 py-1 rounded text-white">{tempPw.pw}</code>
          </p>
          <button onClick={() => setTempPw(null)} className="text-xs text-emerald-500 mt-3 hover:text-emerald-300 transition-colors">Dismiss</button>
        </div>
      )}

      {showCreate && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-[#0f172a] border border-white/[0.1] rounded-2xl shadow-2xl w-full max-w-md p-6">
            <h2 className="text-xl font-bold text-white mb-6">Create New Client</h2>
            <form onSubmit={handleCreate} className="space-y-4">
              <div>
                <label className="text-sm font-medium text-slate-300 block mb-1.5">Company Name <span className="text-red-400">*</span></label>
                <input
                  value={companyName} onChange={e => setCompanyName(e.target.value)} required
                  className="w-full bg-black/30 border border-white/[0.08] rounded-xl px-4 py-2.5 text-sm text-white focus:outline-none focus:border-cyan-500/50"
                  placeholder="ABC Coaching"
                />
              </div>
              <div>
                <label className="text-sm font-medium text-slate-300 block mb-1.5">Owner Email <span className="text-red-400">*</span></label>
                <input
                  type="email" value={email} onChange={e => setEmail(e.target.value)} required
                  className="w-full bg-black/30 border border-white/[0.08] rounded-xl px-4 py-2.5 text-sm text-white focus:outline-none focus:border-cyan-500/50"
                  placeholder="owner@client.com"
                />
              </div>
              <div>
                <label className="text-sm font-medium text-slate-300 block mb-1.5">Temporary Password <span className="text-red-400">*</span></label>
                <input
                  type="text" value={password} onChange={e => setPassword(e.target.value)} required
                  className="w-full bg-black/30 border border-white/[0.08] rounded-xl px-4 py-2.5 text-sm text-white focus:outline-none focus:border-cyan-500/50"
                  placeholder="Aira@123456"
                />
              </div>
              <div>
                <label className="text-sm font-medium text-slate-300 block mb-1.5">Service Package</label>
                <select
                  value={service} onChange={e => setService(e.target.value as ServiceTier)}
                  className="w-full bg-black/30 border border-white/[0.08] rounded-xl px-4 py-2.5 text-sm text-white focus:outline-none focus:border-cyan-500/50 [&>option]:bg-[#0f172a]"
                >
                  {(Object.entries(SERVICE_LABELS) as [ServiceTier, string][]).map(([value, label]) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </select>
              </div>
              <div className="flex gap-3 pt-4">
                <button type="button" onClick={() => setShowCreate(false)} className="flex-1 px-4 py-2.5 bg-white/[0.05] hover:bg-white/[0.1] text-sm text-white font-medium rounded-xl transition-colors">Cancel</button>
                <button type="submit" disabled={submitting} className="flex-1 px-4 py-2.5 bg-gradient-to-r from-cyan-500 to-violet-500 text-white text-sm font-semibold rounded-xl hover:opacity-90 disabled:opacity-50 transition-all">
                  {submitting ? "Creating…" : "Create Client"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {editClient && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-[#0f172a] border border-white/[0.1] rounded-2xl shadow-2xl w-full max-w-sm p-6">
            <h2 className="text-xl font-bold text-white mb-2">Edit Service Plan</h2>
            <p className="text-sm text-cyan-400 mb-6">{editClient.name}</p>
            <div className="space-y-2">
              {(Object.entries(SERVICE_LABELS) as [ServiceTier, string][]).map(([tier, label]) => (
                <button
                  key={tier}
                  onClick={() => handleUpdateService(editClient.id, tier)}
                  className="w-full text-left px-4 py-3 rounded-xl border border-white/[0.08] bg-white/[0.02] text-sm text-slate-300 hover:text-white hover:border-cyan-500/50 hover:bg-cyan-500/10 transition-all"
                >
                  {label}
                </button>
              ))}
            </div>
            <button onClick={() => setEditClient(null)} className="mt-6 w-full text-sm text-slate-400 hover:text-white transition-colors">Cancel</button>
          </div>
        </div>
      )}

      <div className="bg-white/[0.02] backdrop-blur-md rounded-2xl border border-white/[0.08] overflow-hidden">
        {loading ? (
          <div className="p-12 text-center text-sm text-slate-400 flex flex-col items-center">
            <RefreshCw className="animate-spin mb-3 text-cyan-500" size={24} />
            Loading clients...
          </div>
        ) : filteredClients.length === 0 ? (
          <div className="p-16 text-center">
            <p className="text-white font-medium text-lg">No clients found</p>
            <p className="text-sm text-slate-400 mt-2">Try a different search or create a new client.</p>
          </div>
        ) : (
          <table className="w-full">
            <thead>
              <tr className="border-b border-white/[0.06] bg-black/20">
                {["Company", "Service", "Status", "Created", "Actions"].map(h => (
                  <th key={h} className="px-6 py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-widest">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-white/[0.04]">
              {filteredClients.map(client => (
                <tr key={client.id} className="hover:bg-white/[0.04] transition-colors group">
                  <td className="px-6 py-4">
                    <a href={`/operator/client/${client.id}`} className="block">
                      <p className="text-sm font-semibold text-white group-hover:text-cyan-400 transition-colors">{client.name}</p>
                      <p className="text-xs text-slate-500 mt-0.5 font-mono">{client.id.slice(0, 8)}…</p>
                    </a>
                  </td>
                  <td className="px-6 py-4">
                    <span className="inline-flex items-center px-2.5 py-1 rounded-md text-xs font-medium bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
                      {SERVICE_LABELS[featuresToService(client.enabled_features)] ?? "Custom"}
                    </span>
                  </td>
                  <td className="px-6 py-4">
                    <span className={`inline-flex items-center px-2.5 py-1 rounded-md text-xs font-medium border ${
                      client.status === "active" 
                        ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20" 
                        : "bg-red-500/10 text-red-400 border-red-500/20"
                    }`}>
                      {client.status.toUpperCase()}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-xs text-slate-400">
                    {new Date(client.created_at).toLocaleDateString("en-US", { month: 'short', day: 'numeric', year: 'numeric' })}
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-1 opacity-60 group-hover:opacity-100 transition-opacity">
                      <button onClick={() => setEditClient(client)} className="p-2 rounded-lg hover:bg-white/[0.08] text-slate-400 hover:text-white transition-colors" title="Edit service">
                        <Pencil size={15} />
                      </button>
                      <button
                        onClick={() => handleToggleStatus(client)}
                        className={`p-2 rounded-lg hover:bg-white/[0.08] transition-colors ${client.status === "active" ? "text-slate-400 hover:text-red-400" : "text-slate-400 hover:text-emerald-400"}`}
                        title={client.status === "active" ? "Suspend Client" : "Activate Client"}
                      >
                        {client.status === "active" ? <PowerOff size={15} /> : <Power size={15} />}
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
