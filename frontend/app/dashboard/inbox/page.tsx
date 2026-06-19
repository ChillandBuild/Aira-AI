"use client";
import { useEffect, useState, useRef } from "react";
import { MessageSquare, CheckCircle, Settings, UserCog } from "lucide-react";
import Link from "next/link";
import { SegmentBadge } from "@/components/segment-badge";
import { API_URL, getAuthHeaders } from "@/lib/api";
import { cn } from "@/lib/utils";
import { InboxConfigPanel } from "../settings/InboxConfigPanel";
import { toast } from "sonner";
import { useAuthRole } from "../contexts/AuthRoleContext";

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

export default function InboxPage() {
  const { role } = useAuthRole();
  const [handovers, setHandovers] = useState<Handover[]>([]);
  const [callers, setCallers] = useState<Caller[]>([]);
  const [loading, setLoading] = useState(true);
  const [showConfig, setShowConfig] = useState(false);
  const [reassigningId, setReassigningId] = useState<string | null>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  async function load() {
    setLoading(true);
    const [hs, cs] = await Promise.all([fetchHandovers(), fetchCallers()]);
    setHandovers(hs);
    setCallers(cs);
    setLoading(false);
  }

  useEffect(() => { load(); }, []);

  useEffect(() => {
    const handleToggle = () => {
      setShowConfig((prev) => !prev);
    };
    window.addEventListener("toggle-escalation-rules", handleToggle);
    return () => {
      window.removeEventListener("toggle-escalation-rules", handleToggle);
    };
  }, []);

  useEffect(() => {
    window.dispatchEvent(new CustomEvent("escalation-rules-state", { detail: { open: showConfig } }));
  }, [showConfig]);

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
    const originalHandovers = handovers;
    setHandovers((prev) => prev.filter((h) => h.id !== id));
    try {
      await resolveHandover(id);
      toast.success("Handover resolved");
    } catch (err) {
      setHandovers(originalHandovers);
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

  return (
    <div>

      <div className="flex flex-col lg:flex-row gap-6 items-start">
        <div className="flex-grow flex-1 min-w-0 w-full">
          {loading ? (
            <div className="card rounded-3xl p-8 text-center font-body text-sm text-ink-muted">Loading…</div>
          ) : handovers.length === 0 ? (
            <div className="card rounded-3xl p-12 text-center">
              <CheckCircle size={32} className="text-green-500 mx-auto mb-3" />
              <p className="font-display font-bold text-ink">All caught up</p>
              <p className="font-body text-sm text-ink-muted mt-1">No conversations need your attention right now.</p>
            </div>
          ) : (
            <div className="space-y-3">
              {handovers.map((h) => (
                <div key={h.id} className="card rounded-2xl p-5 flex items-start gap-4">
                  <div className="w-9 h-9 rounded-xl bg-amber-50 flex items-center justify-center flex-shrink-0">
                    <MessageSquare size={16} className="text-amber-600" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-label font-semibold text-ink text-sm">
                        {h.leads?.name || "Unknown Lead"}
                      </span>
                      {h.leads?.segment && <SegmentBadge segment={h.leads.segment} />}
                    </div>
                    <p className="font-body text-xs text-ink-muted mb-1.5 font-medium">
                      {h.leads?.source === "telegram" ? (
                        <span className="text-sky-500">Telegram · @{h.leads.tg_username || "unknown"}</span>
                      ) : h.leads?.source === "instagram" ? (
                        <span className="text-pink-500">Instagram · {h.leads.ig_user_id}</span>
                      ) : h.leads?.source === "facebook" ? (
                        <span className="text-blue-600">Facebook · {h.leads.fb_user_id}</span>
                      ) : (
                        <span>WhatsApp · {h.leads?.phone}</span>
                      )}
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
                    <Link
                      href={`/dashboard/conversations?lead=${h.lead_id}`}
                      className="btn-ghost text-xs px-3 py-1.5 flex items-center gap-1.5"
                    >
                      <MessageSquare size={12} /> Reply
                    </Link>
                    <button
                      onClick={() => handleResolve(h.id)}
                      className="text-xs px-3 py-1.5 rounded-xl border border-green-200 text-green-700 hover:bg-green-50 flex items-center gap-1.5 transition-colors"
                    >
                      <CheckCircle size={12} /> Resolve
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {role === "owner" && (
          <div className={cn(
            "w-full lg:w-[420px] shrink-0 sticky top-4 transition-all duration-300 ease-in-out origin-right transform",
            showConfig ? "opacity-100 translate-x-0 scale-100 max-w-[420px]" : "opacity-0 translate-x-4 scale-95 max-w-0 overflow-hidden pointer-events-none"
          )}>
            <InboxConfigPanel />
          </div>
        )}
      </div>
    </div>
  );
}
