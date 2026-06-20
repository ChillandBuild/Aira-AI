"use client";
import { useEffect, useState, useRef, useCallback } from "react";
import { MessageSquare, CheckCircle, UserCog, AlertTriangle } from "lucide-react";
import { SegmentBadge } from "@/components/segment-badge";
import { API_URL, getAuthHeaders } from "@/lib/api";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import { useAuthRole } from "@/app/dashboard/contexts/AuthRoleContext";
import { usePolling } from "@/hooks/usePolling";

type Caller = { id: string; name: string };

type Handover = {
  id: string;
  lead_id: string;
  assigned_to: string | null;
  caller_name: string | null;
  reason: string | null;
  status: string;
  opened_at: string;
  leads: {
    name: string | null;
    phone: string | null;
    segment: "A" | "B" | "C" | "D";
    source?: string;
    tg_username?: string | null;
    ig_user_id?: string | null;
    fb_user_id?: string | null;
  } | null;
};

interface EscalationPanelProps {
  onReply: (leadId: string) => void;
  onCountChange: (count: number) => void;
  currentCallerId?: string | null;
  currentCallerName?: string | null;
}

async function fetchHandovers(): Promise<Handover[]> {
  const auth = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/v1/chat-handovers`, { headers: auth });
  if (!res.ok) return [];
  return (await res.json()).data ?? [];
}

async function resolveHandover(id: string): Promise<void> {
  const auth = await getAuthHeaders();
  await fetch(`${API_URL}/api/v1/chat-handovers/${id}/resolve`, {
    method: "PATCH",
    headers: auth,
  });
}

async function fetchCallers(): Promise<Caller[]> {
  const auth = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/v1/callers?active=true`, { headers: auth });
  if (!res.ok) return [];
  const data = await res.json();
  return (data.callers ?? data.data ?? []).map((c: { id: string; name: string }) => ({ id: c.id, name: c.name }));
}

async function assignHandover(handoverId: string, callerId: string): Promise<void> {
  const auth = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/v1/chat-handovers/${handoverId}/assign`, {
    method: "PATCH",
    headers: { ...auth, "Content-Type": "application/json" },
    body: JSON.stringify({ caller_id: callerId }),
  });
  if (!res.ok) throw new Error("Assignment failed");
}

const TRIGGER_LABELS: Record<string, { label: string; color: string }> = {
  "User requested a human agent": { label: "Asked for human", color: "text-blue-600 bg-blue-50" },
  "AI failed to generate a response": { label: "AI failed", color: "text-red-600 bg-red-50" },
  "AI gave a generic fallback reply": { label: "Generic reply", color: "text-amber-600 bg-amber-50" },
  "User repeated the same question": { label: "Repeated question", color: "text-orange-600 bg-orange-50" },
  "AI indicated team will follow up": { label: "Follow-up needed", color: "text-purple-600 bg-purple-50" },
};

function channelBadge(source?: string, lead?: Handover["leads"]) {
  if (source === "telegram") return <span className="text-sky-500">Telegram · @{lead?.tg_username || "unknown"}</span>;
  if (source === "instagram") return <span className="text-pink-500">Instagram · {lead?.ig_user_id}</span>;
  if (source === "facebook") return <span className="text-blue-600">Facebook · {lead?.fb_user_id}</span>;
  return <span>WhatsApp · {lead?.phone}</span>;
}

export function EscalationPanel({ onReply, onCountChange, currentCallerId, currentCallerName }: EscalationPanelProps) {
  const { role } = useAuthRole();
  const [handovers, setHandovers] = useState<Handover[]>([]);
  const [callers, setCallers] = useState<Caller[]>([]);
  const [loading, setLoading] = useState(true);
  const [reassigningId, setReassigningId] = useState<string | null>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const visibleHandovers = role === "owner"
    ? handovers
    : handovers.filter((h) => !h.assigned_to || h.assigned_to === currentCallerId);

  const load = useCallback(async () => {
    const [hs, cs] = await Promise.all([fetchHandovers(), fetchCallers()]);
    setHandovers(hs);
    setCallers(cs);
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);
  usePolling(load, 15000);

  useEffect(() => {
    if (!loading) onCountChange(visibleHandovers.length);
  }, [visibleHandovers.length, loading, onCountChange]);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setReassigningId(null);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  async function handleResolve(id: string) {
    const prev = handovers;
    setHandovers(handovers.filter((h) => h.id !== id));
    try {
      await resolveHandover(id);
      toast.success("Escalation resolved");
    } catch (err) {
      setHandovers(prev);
      toast.error(err instanceof Error ? err.message : "Failed to resolve");
    }
  }

  async function handleAssign(handoverId: string, callerId: string, callerName: string) {
    setReassigningId(null);
    const prev = handovers;
    setHandovers((hs) => hs.map((h) =>
      h.id === handoverId ? { ...h, assigned_to: callerId, caller_name: callerName } : h
    ));
    try {
      await assignHandover(handoverId, callerId);
      toast.success(`Assigned to ${callerName}`);
    } catch {
      setHandovers(prev);
      toast.error("Assignment failed");
    }
  }

  const myName = callers.find((c) => c.id === currentCallerId)?.name ?? currentCallerName ?? "You";

  async function handleClaimAndReply(handover: Handover) {
    if (currentCallerId && !handover.assigned_to) {
      const prev = handovers;
      setHandovers((hs) => hs.map((h) =>
        h.id === handover.id ? { ...h, assigned_to: currentCallerId, caller_name: myName } : h
      ));
      try {
        await assignHandover(handover.id, currentCallerId);
        toast.success("Claimed — you're handling this lead");
      } catch {
        setHandovers(prev);
      }
    }
    onReply(handover.lead_id);
  }

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-3xl mx-auto px-6 py-8">
        <div className="mb-6">
          <h2 className="font-display text-xl font-bold text-ink">Escalations</h2>
          <p className="font-body text-sm text-ink-muted mt-1">
            Leads that need human attention — AI couldn&apos;t handle the conversation.
          </p>
        </div>

        {loading ? (
          <div className="card rounded-3xl p-8 text-center font-body text-sm text-ink-muted">Loading…</div>
        ) : visibleHandovers.length === 0 ? (
          <div className="card rounded-3xl p-12 text-center">
            <CheckCircle size={36} className="text-green-500 mx-auto mb-3" />
            <p className="font-display font-bold text-ink text-lg">All caught up</p>
            <p className="font-body text-sm text-ink-muted mt-1">No conversations need your attention right now.</p>
          </div>
        ) : (
          <div className="space-y-3">
            {visibleHandovers.map((h) => {
              const trigger = TRIGGER_LABELS[h.reason ?? ""] ?? null;
              const isMine = h.assigned_to === currentCallerId;
              return (
                <div key={h.id} className="card rounded-2xl p-5 flex items-start gap-4 hover:shadow-md transition-shadow">
                  <div className="w-9 h-9 rounded-xl bg-amber-50 flex items-center justify-center flex-shrink-0">
                    <AlertTriangle size={16} className="text-amber-600" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1 flex-wrap">
                      <span className="font-label font-semibold text-ink text-sm">
                        {h.leads?.name || "Unknown Lead"}
                      </span>
                      {h.leads?.segment && <SegmentBadge segment={h.leads.segment} />}
                      {trigger && (
                        <span className={cn("font-label text-[10px] font-semibold px-1.5 py-0.5 rounded-full", trigger.color)}>
                          {trigger.label}
                        </span>
                      )}
                    </div>
                    <p className="font-body text-xs text-ink-muted mb-1.5 font-medium">
                      {channelBadge(h.leads?.source, h.leads)}
                    </p>
                    {h.reason && (
                      <p className="font-body text-sm text-ink bg-surface-subtle rounded-lg px-3 py-2 mb-3">
                        &ldquo;{h.reason}&rdquo;
                      </p>
                    )}
                    <div className="flex items-center gap-3 flex-wrap">
                      <p className="font-body text-xs text-ink-muted">
                        {new Date(h.opened_at).toLocaleString("en-IN")}
                      </p>
                      <div className="relative" ref={reassigningId === h.id ? dropdownRef : null}>
                        <button
                          onClick={() => role === "owner" ? setReassigningId(reassigningId === h.id ? null : h.id) : undefined}
                          className={cn(
                            "font-label text-xs px-2 py-0.5 rounded-full font-medium flex items-center gap-1",
                            h.assigned_to
                              ? "bg-green-50 text-green-700 hover:bg-green-100"
                              : "bg-amber-50 text-amber-600 hover:bg-amber-100",
                            role !== "owner" && "cursor-default"
                          )}
                        >
                          {h.assigned_to ? `Assigned to ${h.caller_name ?? "caller"}` : "Unassigned"}
                          {role === "owner" && <UserCog size={10} />}
                        </button>
                        {reassigningId === h.id && (
                          <div className="absolute left-0 top-full mt-1 z-20 bg-white border border-surface-mid rounded-xl shadow-lg py-1 min-w-[160px]">
                            <p className="px-3 py-1 text-xs text-ink-muted font-label font-semibold">Assign to</p>
                            {callers.length === 0 ? (
                              <p className="px-3 py-2 text-xs text-ink-muted">No active callers</p>
                            ) : callers.map((c) => (
                              <button
                                key={c.id}
                                onClick={() => handleAssign(h.id, c.id, c.name)}
                                className="w-full text-left px-3 py-2 text-sm font-body hover:bg-surface-subtle text-ink transition-colors"
                              >
                                {c.name}
                              </button>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                  <div className="flex flex-col gap-2 flex-shrink-0">
                    <button
                      onClick={() => handleClaimAndReply(h)}
                      className="btn-ghost text-xs px-3 py-1.5 flex items-center gap-1.5"
                    >
                      <MessageSquare size={12} /> {h.assigned_to ? "Reply" : "Pick up"}
                    </button>
                    {(isMine || role === "owner") && (
                      <button
                        onClick={() => handleResolve(h.id)}
                        className="text-xs px-3 py-1.5 rounded-xl border border-green-200 text-green-700 hover:bg-green-50 flex items-center gap-1.5 transition-colors"
                      >
                        <CheckCircle size={12} /> Resolve
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
