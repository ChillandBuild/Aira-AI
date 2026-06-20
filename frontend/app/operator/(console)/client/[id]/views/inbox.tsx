"use client";
import { useEffect, useState } from "react";
import { Inbox, MessageSquare, Hash } from "lucide-react";
import { API_URL, getAuthHeaders } from "@/lib/api";
import { StatCard } from "../components/stat-card";
import { SkeletonCard, SkeletonTable } from "../components/skeleton";

async function apiFetch<T>(path: string): Promise<T> {
  const auth = await getAuthHeaders();
  const res = await fetch(`${API_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...auth },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail || "Request failed");
  }
  return res.json() as Promise<T>;
}

function relTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const s = Math.abs(diff) / 1000;
  if (s < 60) return `${Math.round(s)}s ago`;
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
}

interface Conversation {
  lead_id: string;
  lead_name: string | null;
  last_message: string | null;
  channel: string | null;
  updated_at: string;
}

interface InboxData {
  handover_count: number;
  conversations: Conversation[];
}

const CHANNEL_COLORS: Record<string, string> = {
  whatsapp: "bg-green-50 text-success",
  instagram: "bg-pink-50 text-pink-600",
  facebook: "bg-blue-50 text-blue-600",
  telegram: "bg-sky-50 text-sky-600",
};

export function InboxView({ tenantId }: { tenantId: string }) {
  const [data, setData] = useState<InboxData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    apiFetch<InboxData>(`/api/v1/operator/clients/${tenantId}/dashboard/inbox`)
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, [tenantId]);

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <SkeletonCard />
          <SkeletonCard />
        </div>
        <SkeletonTable rows={5} />
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

  if (!data) return null;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4">
        <StatCard icon={<Inbox size={18} />} label="Handovers" value={data.handover_count} />
        <StatCard icon={<Hash size={18} />} label="Conversations" value={data.conversations.length} />
      </div>

      {data.conversations.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-ink-muted">
          <MessageSquare size={40} className="mb-3 opacity-40" />
          <p className="text-sm">No conversations yet</p>
        </div>
      ) : (
        <div className="bg-white rounded-card border border-border overflow-hidden shadow-sm">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-surface-mid text-ink-secondary uppercase text-xs">
                <th className="text-left px-4 py-3 font-medium">Lead</th>
                <th className="text-left px-4 py-3 font-medium">Last Message</th>
                <th className="text-left px-4 py-3 font-medium">Channel</th>
                <th className="text-left px-4 py-3 font-medium">Time</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border-subtle">
              {data.conversations.map((c) => (
                <tr key={c.lead_id} className="hover:bg-surface-mid/50 transition-colors">
                  <td className="px-4 py-3 font-medium text-ink">{c.lead_name || "Unknown"}</td>
                  <td className="px-4 py-3 text-ink-secondary truncate max-w-[240px]">
                    {c.last_message ? (c.last_message.length > 60 ? c.last_message.slice(0, 60) + "..." : c.last_message) : "—"}
                  </td>
                  <td className="px-4 py-3">
                    {c.channel ? (
                      <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${CHANNEL_COLORS[c.channel] || "bg-surface-mid text-ink-muted"}`}>
                        {c.channel}
                      </span>
                    ) : "—"}
                  </td>
                  <td className="px-4 py-3 text-ink-muted text-xs">{relTime(c.updated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
