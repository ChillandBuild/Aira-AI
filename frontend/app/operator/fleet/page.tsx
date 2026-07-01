"use client";
import { useEffect, useState } from "react";
import { API_URL, getAuthHeaders } from "@/lib/api";
import { Users, MessageSquare, Phone, Activity, AlertTriangle, Calendar, CreditCard } from "lucide-react";

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
}

async function apiFetch<T>(path: string): Promise<T> {
  const auth = await getAuthHeaders();
  const res = await fetch(`${API_URL}${path}`, { headers: auth });
  if (!res.ok) throw new Error("Request failed");
  const json = await res.json();
  return (json as any).data ?? json;
}

export default function FleetPage() {
  const [clients, setClients] = useState<FleetClient[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<FleetClient[]>("/api/v1/operator/fleet")
      .then(setClients)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const totalMrr = clients.reduce((sum, c) => sum + (c.mrr || 0), 0);
  const activeCount = clients.filter(c => c.status === "active").length;
  const trialCount = clients.filter(c => c.status === "trial").length;
  const suspendedCount = clients.filter(c => c.status === "suspended").length;
  const nearCap = clients.filter(c => c.ai_usage >= 80).length;

  if (loading) return <div className="p-8 text-center">Loading fleet…</div>;
  if (error) return <div className="p-8 text-danger">{error}</div>;

  return (
    <div className="max-w-7xl mx-auto px-8 py-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-ink">Fleet Cockpit</h1>
          <p className="text-sm text-ink-muted mt-1">All clients summary and attention queue.</p>
        </div>
      </div>

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
      ) : (
        <div className="bg-white rounded-card border border-border shadow-card overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-surface-mid">
              <tr>
                {["Company", "Status", "MRR", "Msgs 30d", "AI Usage %", "Health", "Last Activity"].map(h => (
                  <th key={h} className="px-5 py-3 text-left font-semibold text-ink-secondary whitespace-nowrap">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-border-subtle">
              {clients.map(c => (
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
                  <td className="px-5 py-3">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                      c.health === "healthy" ? "bg-green-50 text-success" : c.health === "warning" ? "bg-warning/10 text-warning" : "bg-red-50 text-danger"
                    }`}>
                      {c.health}
                    </span>
                  </td>
                  <td className="px-5 py-3 text-ink-muted">
                    {c.last_activity ? new Date(c.last_activity).toLocaleDateString("en-IN") : "—"}
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