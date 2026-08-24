import { API_URL, getAuthHeaders } from "@/lib/api";

export type EscalationLead = {
  name: string | null;
  phone: string | null;
  segment: "A" | "B" | "C" | "D";
  source?: string;
  tg_username?: string | null;
  ig_user_id?: string | null;
  fb_user_id?: string | null;
} | null;

export type Handover = {
  id: string;
  lead_id: string;
  assigned_to: string | null;
  caller_name: string | null;
  reason: string | null;
  status: string;
  opened_at: string;
  leads: EscalationLead;
};

export type ResolvedHandover = Omit<Handover, "caller_name"> & {
  resolved_at: string | null;
  resolved_by: string | null;
  resolved_by_name: string | null;
  duration_seconds: number | null;
};

export type HistoryStats = {
  total: number;
  median_seconds: number | null;
  top_resolver: string | null;
  top_resolver_count: number;
  top_reason: string | null;
  resolvers: string[];
  reasons: string[];
};

export type HistoryPage = {
  data: ResolvedHandover[];
  total: number;
  stats: HistoryStats;
};

export type Caller = { id: string; name: string };

/** The five reasons `ai_reply.py` can hand a conversation over with. The raw
 *  sentence is what the AI writes into `chat_handovers.reason`; the short label
 *  is what fits in a table cell. An unrecognised reason falls back to the raw
 *  text so a new trigger never renders as a blank chip. */
export const TRIGGERS: Record<string, { label: string; className: string }> = {
  "User requested a human agent": {
    label: "Asked for human",
    className: "bg-blue-50 text-blue-700 border-blue-100",
  },
  "AI failed to generate a response": {
    label: "AI failed",
    className: "bg-red-50 text-red-700 border-red-100",
  },
  "AI gave a generic fallback reply": {
    label: "Generic reply",
    className: "bg-amber-50 text-amber-700 border-amber-100",
  },
  "User repeated the same question": {
    label: "Repeated question",
    className: "bg-orange-50 text-orange-700 border-orange-100",
  },
  "AI indicated team will follow up": {
    label: "Follow-up needed",
    className: "bg-purple-50 text-purple-700 border-purple-100",
  },
};

export const EMPTY_HISTORY_STATS: HistoryStats = {
  total: 0,
  median_seconds: null,
  top_resolver: null,
  top_resolver_count: 0,
  top_reason: null,
  resolvers: [],
  reasons: [],
};

/** Wait-time severity. Escalations sitting past a day are the ones that get
 *  forgotten, so 24h is the line where a row turns red. */
export type Severity = "ok" | "warn" | "bad";

export function severityForWait(seconds: number | null): Severity {
  if (seconds === null) return "ok";
  if (seconds >= 86_400) return "bad";
  if (seconds >= 14_400) return "warn";
  return "ok";
}

export const SEVERITY_TEXT: Record<Severity, string> = {
  ok: "text-success",
  warn: "text-warning",
  bad: "text-danger",
};

export function initialsOf(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .map((w) => w[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
}

export function channelOf(lead: EscalationLead): { label: string; handle: string; className: string } {
  const source = lead?.source ?? "whatsapp";
  if (source === "telegram")
    return { label: "Telegram", handle: lead?.tg_username ? `@${lead.tg_username}` : "unknown", className: "text-sky-600" };
  if (source === "instagram")
    return { label: "Instagram", handle: lead?.ig_user_id ?? "unknown", className: "text-pink-600" };
  if (source === "facebook")
    return { label: "Facebook", handle: lead?.fb_user_id ?? "unknown", className: "text-blue-600" };
  return { label: "WhatsApp", handle: lead?.phone ?? "unknown", className: "text-emerald-600" };
}

// ── API ──────────────────────────────────────────────────────────────────────

export async function fetchHandovers(): Promise<Handover[]> {
  const auth = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/v1/chat-handovers`, { headers: auth });
  if (!res.ok) return [];
  return (await res.json()).data ?? [];
}

export async function fetchCallers(): Promise<Caller[]> {
  const auth = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/v1/callers?active=true`, { headers: auth });
  if (!res.ok) return [];
  const data = await res.json();
  return (data.callers ?? data.data ?? []).map((c: { id: string; name: string }) => ({ id: c.id, name: c.name }));
}

export async function fetchHistory(params: {
  limit: number;
  offset: number;
  q?: string;
  resolver?: string;
  reason?: string;
}): Promise<HistoryPage> {
  const auth = await getAuthHeaders();
  const qs = new URLSearchParams({ limit: String(params.limit), offset: String(params.offset) });
  if (params.q) qs.set("q", params.q);
  if (params.resolver) qs.set("resolver", params.resolver);
  if (params.reason) qs.set("reason", params.reason);
  const res = await fetch(`${API_URL}/api/v1/chat-handovers/history?${qs}`, { headers: auth });
  if (!res.ok) throw new Error("Couldn't load escalation history");
  return res.json();
}

export async function resolveHandover(id: string): Promise<void> {
  const auth = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/v1/chat-handovers/${id}/resolve`, { method: "PATCH", headers: auth });
  if (!res.ok) throw new Error("Couldn't resolve this escalation");
}

export async function reopenHandover(id: string): Promise<void> {
  const auth = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/v1/chat-handovers/${id}/reopen`, { method: "PATCH", headers: auth });
  if (!res.ok) throw new Error("Couldn't reopen this escalation");
}

export async function assignHandover(handoverId: string, callerId: string): Promise<void> {
  const auth = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/v1/chat-handovers/${handoverId}/assign`, {
    method: "PATCH",
    headers: { ...auth, "Content-Type": "application/json" },
    body: JSON.stringify({ caller_id: callerId }),
  });
  if (!res.ok) throw new Error("Couldn't assign this escalation");
}
