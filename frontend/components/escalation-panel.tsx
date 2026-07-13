"use client";
import { useEffect, useState, useRef, useCallback } from "react";
import { MessageSquare, CheckCircle, UserCog, AlertTriangle, Search, X } from "lucide-react";
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
  canReplyToConversations?: boolean;
}

async function fetchHandovers(): Promise<Handover[]> {
  const auth = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/v1/chat-handovers`, { headers: auth });
  if (!res.ok) return [];
  return (await res.json()).data ?? [];
}

async function resolveHandover(id: string): Promise<void> {
  const auth = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/v1/chat-handovers/${id}/resolve`, {
    method: "PATCH",
    headers: auth,
  });
  if (!res.ok) throw new Error("Failed to resolve escalation");
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
  "User requested a human agent": { label: "Asked for human", color: "text-blue-600 bg-blue-50 border-blue-100" },
  "AI failed to generate a response": { label: "AI failed", color: "text-red-600 bg-red-50 border-red-100" },
  "AI gave a generic fallback reply": { label: "Generic reply", color: "text-amber-600 bg-amber-50 border-amber-100" },
  "User repeated the same question": { label: "Repeated question", color: "text-orange-600 bg-orange-50 border-orange-100" },
  "AI indicated team will follow up": { label: "Follow-up needed", color: "text-purple-600 bg-purple-50 border-purple-100" },
};

function channelBadge(source?: string, lead?: Handover["leads"]) {
  if (source === "telegram") return <span className="text-sky-500 font-bold">Telegram · @{lead?.tg_username || "unknown"}</span>;
  if (source === "instagram") return <span className="text-pink-500 font-bold">Instagram · {lead?.ig_user_id}</span>;
  if (source === "facebook") return <span className="text-blue-600 font-bold">Facebook · {lead?.fb_user_id}</span>;
  return <span className="text-emerald-600 font-bold">WhatsApp · {lead?.phone}</span>;
}

export function EscalationPanel({ onReply, onCountChange, currentCallerId, currentCallerName, canReplyToConversations = false }: EscalationPanelProps) {
  const { role } = useAuthRole();
  const [handovers, setHandovers] = useState<Handover[]>([]);
  const [callers, setCallers] = useState<Caller[]>([]);
  const [loading, setLoading] = useState(true);
  const [reassigningId, setReassigningId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const dropdownRef = useRef<HTMLDivElement>(null);

  const visibleHandovers = role === "owner"
    ? handovers
    : handovers.filter((h) => !h.assigned_to || h.assigned_to === currentCallerId);

  const filteredHandovers = visibleHandovers.filter((h) => {
    const q = searchQuery.toLowerCase().trim();
    if (!q) return true;
    const name = h.leads?.name?.toLowerCase() || "";
    const phone = h.leads?.phone || "";
    const tg = h.leads?.tg_username?.toLowerCase() || "";
    const ig = h.leads?.ig_user_id?.toLowerCase() || "";
    const fb = h.leads?.fb_user_id?.toLowerCase() || "";
    const reason = h.reason?.toLowerCase() || "";
    return name.includes(q) || phone.includes(q) || tg.includes(q) || ig.includes(q) || fb.includes(q) || reason.includes(q);
  });

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
    if (!canReplyToConversations) return;
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
    if (!canReplyToConversations) return;
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
    <div className="flex-1 overflow-y-auto bg-surface-mid/10">
      <div className="max-w-7xl mx-auto px-6 md:px-10 py-10 space-y-8">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-6 border-b border-surface-mid pb-6">
          <div>
            <h2 className="font-display text-3xl font-extrabold text-ink tracking-tight flex items-center gap-2">
              <span>Escalations</span>
              {filteredHandovers.length > 0 && (
                <span className="text-xs font-bold px-3 py-0.5 rounded-full bg-red-100 border border-red-200 text-red-600 animate-pulse">
                  {filteredHandovers.length} active
                </span>
              )}
            </h2>
            <p className="font-body text-sm text-ink-muted mt-1.5">
              Leads that need human attention — AI couldn&apos;t handle the conversation.
            </p>
          </div>

          {/* Search bar */}
          <div className="relative w-full sm:w-80">
            <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-ink-muted" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search by name, phone, channel..."
              className="w-full pl-10 pr-9 py-2 text-sm border border-border bg-white rounded-xl focus:outline-none focus:ring-2 focus:ring-primary/20 transition-all placeholder:text-ink-muted/70"
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery("")}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-ink-muted hover:text-ink transition-colors"
              >
                <X size={15} />
              </button>
            )}
          </div>
        </div>

        {loading ? (
          <div className="bg-white border border-border rounded-2xl p-16 text-center font-body text-base text-ink-muted shadow-sm">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent mx-auto mb-4" />
            Loading escalations…
          </div>
        ) : visibleHandovers.length === 0 ? (
          <div className="bg-white border border-border rounded-3xl p-16 text-center max-w-lg mx-auto shadow-sm bg-gradient-to-br from-green-50/20 to-white/10 mt-12">
            <div className="w-16 h-16 rounded-full bg-green-50 border border-green-100 flex items-center justify-center mx-auto mb-5 shadow-inner">
              <CheckCircle size={28} className="text-green-500" />
            </div>
            <p className="font-display font-bold text-ink text-xl">All caught up</p>
            <p className="font-body text-base text-ink-muted mt-2">No conversations need your attention right now.</p>
          </div>
        ) : filteredHandovers.length === 0 ? (
          <div className="bg-white border border-border rounded-3xl p-16 text-center max-w-lg mx-auto shadow-sm mt-12">
            <div className="w-16 h-16 rounded-full bg-surface-mid flex items-center justify-center mx-auto mb-5">
              <Search size={26} className="text-ink-muted" />
            </div>
            <p className="font-display font-bold text-ink text-xl">No matches found</p>
            <p className="font-body text-base text-ink-muted mt-2">We couldn&apos;t find any escalations matching your query.</p>
          </div>
        ) : (
          <div className="space-y-6">
            {filteredHandovers.map((h) => {
              const trigger = TRIGGER_LABELS[h.reason ?? ""] ?? null;
              const isMine = h.assigned_to === currentCallerId;
              return (
                <div key={h.id} className="bg-white border border-border rounded-2xl p-6 md:p-8 flex flex-col md:flex-row md:items-start justify-between gap-6 hover:-translate-y-0.5 hover:shadow-md transition-all duration-200">
                  <div className="flex items-start gap-5 flex-1 min-w-0">
                    <div className="w-12 h-12 rounded-xl bg-red-50 border border-red-100 flex items-center justify-center flex-shrink-0 shadow-xs">
                      <AlertTriangle size={22} className="text-red-500" />
                    </div>
                    <div className="flex-1 min-w-0 space-y-2">
                      <div className="flex items-center gap-2.5 flex-wrap">
                        <span className="font-label font-bold text-ink text-base md:text-lg">
                          {h.leads?.name || "Unknown Lead"}
                        </span>
                        {h.leads?.segment && <SegmentBadge segment={h.leads.segment} />}
                        {trigger && (
                          <span className={cn("font-label text-xs font-bold px-2.5 py-0.5 rounded-full border shadow-xs", trigger.color)}>
                            {trigger.label}
                          </span>
                        )}
                      </div>
                      <p className="font-body text-xs md:text-sm text-ink-muted">
                        {channelBadge(h.leads?.source, h.leads)}
                      </p>
                      {h.reason && (
                        <div className="font-body text-sm text-ink bg-slate-50 border-l-4 border-rose-400 rounded-r-xl px-5 py-3.5 my-3 shadow-xs max-w-4xl relative">
                          <p className="italic text-ink-secondary leading-relaxed font-medium">&ldquo;{h.reason}&rdquo;</p>
                        </div>
                      )}
                      <div className="flex items-center gap-4 flex-wrap pt-1">
                        <p className="font-body text-xs text-ink-muted">
                          {new Date(h.opened_at).toLocaleString("en-IN")}
                        </p>
                        <div className="relative" ref={reassigningId === h.id ? dropdownRef : null}>
                          <button
                            onClick={() => role === "owner" ? setReassigningId(reassigningId === h.id ? null : h.id) : undefined}
                            className={cn(
                              "font-label text-xs px-3 py-1 rounded-full font-bold flex items-center gap-1.5 border transition-all shadow-xs",
                              h.assigned_to
                                ? "bg-green-50 text-green-700 border-green-200/50 hover:bg-green-100"
                                : "bg-amber-50 text-amber-600 border-amber-200/50 hover:bg-amber-100",
                              role !== "owner" && "cursor-default"
                            )}
                          >
                            <span>{h.assigned_to ? `Assigned to ${h.caller_name ?? "caller"}` : "Unassigned"}</span>
                            {role === "owner" && <UserCog size={11} className="opacity-80" />}
                          </button>
                          {reassigningId === h.id && (
                            <div className="absolute left-0 top-full mt-2 z-20 bg-white border border-border rounded-xl shadow-lg py-1 min-w-[180px] animate-in fade-in slide-in-from-top-1 duration-150">
                              <p className="px-3 py-1 text-[10px] text-ink-muted font-label font-bold uppercase tracking-wider">Assign to</p>
                              <div className="my-0.5 border-t border-border-subtle" />
                              {callers.length === 0 ? (
                                <p className="px-3 py-2 text-xs text-ink-muted">No active callers</p>
                              ) : callers.map((c) => (
                                <button
                                  key={c.id}
                                  onClick={() => handleAssign(h.id, c.id, c.name)}
                                  className="w-full text-left px-3 py-2 text-xs font-body hover:bg-primary-light hover:text-primary text-ink transition-colors"
                                >
                                  {c.name}
                                </button>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                  <div className="flex flex-row md:flex-col gap-2.5 flex-shrink-0 self-end md:self-start w-full md:w-auto md:min-w-[140px] mt-3 md:mt-0 border-t md:border-t-0 border-border-subtle pt-3 md:pt-0">
                    <button
                      onClick={() => handleClaimAndReply(h)}
                      disabled={!canReplyToConversations}
                      title={canReplyToConversations ? undefined : "You have read-only access to conversations"}
                      className="flex-1 md:flex-initial text-xs md:text-sm px-4 py-2 flex items-center justify-center gap-2 bg-primary hover:bg-primary-dark text-white rounded-xl transition-all duration-150 hover:scale-[1.02] active:scale-[0.98] font-bold shadow-sm disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-primary disabled:hover:scale-100"
                    >
                      <MessageSquare size={14} /> {h.assigned_to ? "Reply" : "Pick up"}
                    </button>
                    {(isMine || role === "owner" || !canReplyToConversations) && (
                      <button
                        onClick={() => handleResolve(h.id)}
                        disabled={!canReplyToConversations}
                        title={canReplyToConversations ? undefined : "You have read-only access to conversations"}
                        className="flex-1 md:flex-initial text-xs md:text-sm px-4 py-2 rounded-xl border border-green-200 text-green-700 hover:bg-green-50 flex items-center justify-center gap-2 transition-all duration-150 hover:scale-[1.02] active:scale-[0.98] bg-white font-bold shadow-xs disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-white disabled:hover:scale-100"
                      >
                        <CheckCircle size={14} /> Resolve
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
