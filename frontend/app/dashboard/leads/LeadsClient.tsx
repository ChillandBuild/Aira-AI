"use client";
import { toast } from "sonner";
import { useEffect, useState } from "react";
import { api, Lead, Caller, SegmentTemplate, BroadcastResult, BroadcastHistoryItem, WabaTemplate, getAuthHeaders, API_URL } from "@/lib/api";
import { Download, Send, Save, Pencil, Plus, X, Loader2, Clock } from "lucide-react";
import { cn } from "@/lib/utils";
import { timeAgo, formatPhone } from "@/lib/utils";
import { useAuthRole } from "../contexts/AuthRoleContext";
import { AssignButton } from "./AssignButton";
import ReengagementBuilder from "./ReengagementBuilder";
import { useLeads } from "@/hooks/useApi";
import { useSearchParams, useRouter } from "next/navigation";
import { MobileRecordCard, MobileRecordField, MobileRecordGrid, MobileRecordHeader } from "@/components/MobileRecord";

function pillClass(active: boolean) {
  return `px-5 py-2.5 rounded-xl font-label text-xs font-bold transition-all ${
    active ? "bg-white text-[#1c1917] shadow-sm" : "text-[#78716c] hover:text-[#292524]"
  }`;
}

function NameCell({ lead, onUpdate }: { lead: Lead; onUpdate: (l: Lead) => void }) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(lead.name || "");

  async function save() {
    setEditing(false);
    const trimmed = value.trim();
    if (!trimmed || trimmed === (lead.name || "")) return;
    try {
      const updated = await api.leads.update(lead.id, { name: trimmed });
      onUpdate(updated);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Rename failed");
      setValue(lead.name || "");
    }
  }

  if (editing) {
    return (
      <input
        autoFocus
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onBlur={save}
        onKeyDown={(e) => {
          if (e.key === "Enter") save();
          if (e.key === "Escape") {
            setValue(lead.name || "");
            setEditing(false);
          }
        }}
        className="font-body text-sm text-on-surface bg-surface-low px-2 py-0.5 rounded border border-primary focus:outline-none focus:ring-1 focus:ring-primary w-40"
      />
    );
  }

  return (
    <button
      onClick={(e) => {
        e.stopPropagation();
        setValue(lead.name || "");
        setEditing(true);
      }}
      className="group flex items-center gap-1.5 font-body text-sm text-on-surface"
      title="Click to rename"
    >
      <span className={lead.name ? "" : "text-on-surface-muted italic"}>
        {lead.name || "Add name"}
      </span>
      <Pencil size={11} className="opacity-0 group-hover:opacity-60 text-on-surface-muted" />
    </button>
  );
}

const SEGMENTS = ["A", "B", "C", "D"] as const;

const SEGMENT_LABELS: Record<string, string> = {
  A: "Hot",
  B: "Warm",
  C: "Cold",
  D: "Disqualified",
};

function ComposeModal({ onClose, onSent, canManageLeads }: { onClose: () => void; onSent: () => void; canManageLeads: boolean }) {
  const [phone, setPhone] = useState("");
  const [name, setName] = useState("");
  const [message, setMessage] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function send() {
    if (!canManageLeads) return;
    if (!phone.trim() || !message.trim()) {
      setError("Phone and message are required");
      return;
    }
    setSending(true);
    setError(null);
    try {
      await api.leads.compose(phone.trim(), message.trim(), name.trim() || undefined);
      onSent();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Send failed");
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div className="bg-surface rounded-card shadow-card w-full max-w-md p-6" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-5">
          <h3 className="font-display text-lg font-bold text-primary">New WhatsApp Message</h3>
          <button onClick={onClose} className="text-on-surface-muted hover:text-on-surface">
            <X size={18} />
          </button>
        </div>

        <div className="space-y-4">
          <div>
            <label className="font-label text-xs font-semibold text-on-surface-muted uppercase tracking-wider">
              Phone Number
            </label>
            <input
              autoFocus
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="+919876543210"
              className="mt-1 w-full px-4 py-2.5 bg-surface-low rounded-xl font-body text-sm border border-surface-mid focus:ring-2 focus:ring-primary focus:outline-none"
            />
          </div>

          <div>
            <label className="font-label text-xs font-semibold text-on-surface-muted uppercase tracking-wider">
              Name <span className="text-on-surface-muted/60 normal-case">(optional)</span>
            </label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Lead name"
              className="mt-1 w-full px-4 py-2.5 bg-surface-low rounded-xl font-body text-sm border border-surface-mid focus:ring-2 focus:ring-primary focus:outline-none"
            />
          </div>

          <div>
            <label className="font-label text-xs font-semibold text-on-surface-muted uppercase tracking-wider">
              Message
            </label>
            <textarea
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              rows={4}
              placeholder="Hello! ..."
              className="mt-1 w-full px-4 py-2.5 bg-surface-low rounded-xl font-body text-sm border border-surface-mid focus:ring-2 focus:ring-primary focus:outline-none resize-none"
            />
          </div>

          <div className="flex items-start gap-2 p-3 rounded-xl bg-amber-50 border border-amber-100">
            <p className="font-label text-xs text-amber-800 leading-relaxed">
              <strong>Heads up:</strong> If this person hasn&apos;t messaged you in the last 24 hours, WhatsApp requires an <strong>approved template message</strong> — freeform text will fail. Use the Templates page to send templated outreach.
            </p>
          </div>

          {error && (
            <div className="p-3 rounded-xl bg-red-50 border border-red-100">
              <p className="font-label text-xs text-red-700">{error}</p>
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2 mt-6">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-surface-low text-on-surface-muted rounded-xl font-label text-sm font-semibold hover:bg-surface-mid"
          >
            Cancel
          </button>
          <button
            onClick={send}
            disabled={sending || !canManageLeads}
            title={canManageLeads ? "Send message" : "Read-only role: sending is disabled"}
            className="flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-xl font-label text-sm font-semibold hover:bg-primary/90 disabled:opacity-50"
          >
            {sending ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
            {sending ? "Sending…" : canManageLeads ? "Send" : "Send Disabled"}
          </button>
        </div>
      </div>
    </div>
  );
}

export function LeadsClient({ fallbackLeads, initialTab = "A" }: { fallbackLeads: Lead[] | null; initialTab?: typeof SEGMENTS[number] }) {
  const { role, permissions } = useAuthRole();
  const canManageLeads = role === "owner" || permissions.includes("leads.manage");
  const [tab, setTab] = useState<typeof SEGMENTS[number]>(initialTab);
  const [templates, setTemplates] = useState<Record<string, SegmentTemplate>>({});
  const [draft, setDraft] = useState("");
  const [savingTpl, setSavingTpl] = useState(false);
  const [broadcasting, setBroadcasting] = useState(false);
  const [lastResult, setLastResult] = useState<BroadcastResult | null>(null);
  const [composing, setComposing] = useState(false);
  const [callers, setCallers] = useState<Caller[]>([]);

  // Filtering states
  const [sourceFilter, setSourceFilter] = useState("ALL");
  const [selectedCampaignId, setSelectedCampaignId] = useState("");
  const [selectedBroadcastId, setSelectedBroadcastId] = useState("");
  const [campaigns, setCampaigns] = useState<{ id: string; campaign_name: string; platform: string }[]>([]);
  const [broadcastHistory, setBroadcastHistory] = useState<BroadcastHistoryItem[]>([]);

  // Re-engagement states
  const [wabaTemplates, setWabaTemplates] = useState<WabaTemplate[]>([]);
  const router = useRouter();
  const searchParams = useSearchParams();
  const rawTab = searchParams.get("tab");
  const pageView = (rawTab === "reengagement" ? "reengagement" : "leads") as "leads" | "reengagement";

  const setPageView = (val: "leads" | "reengagement") => {
    const params = new URLSearchParams(searchParams.toString());
    params.set("tab", val);
    router.replace(`/dashboard/leads?${params.toString()}`, { scroll: false });
  };
  const [reengageTrigger, setReengageTrigger] = useState<"broadcast" | "inbound">("inbound");

  // SWR Hook
  const { data: leadsData, mutate } = useLeads(
    {
      segment: tab,
      limit: 200,
      source_filter: sourceFilter !== "ALL" ? sourceFilter.toLowerCase() : undefined,
      ad_campaign_id: (sourceFilter === "META_ADS" && selectedCampaignId) ? selectedCampaignId : undefined,
      broadcast_id: (sourceFilter === "BROADCAST" && selectedBroadcastId) ? selectedBroadcastId : undefined,
    },
    true,
    (tab === initialTab && sourceFilter === "ALL") ? (fallbackLeads ?? undefined) : undefined
  );

  const leads = leadsData ?? [];
  const loading = !leadsData;

  useEffect(() => {
    api.callers.list().then((res) => setCallers((res.data || []).filter((c) => c.active))).catch(() => {});
    api.inboundLeads.campaigns().then(setCampaigns).catch(() => {});
    api.broadcasts.history().then(setBroadcastHistory).catch(() => {});

    // Fetch WABA templates
    getAuthHeaders().then(auth => {
      fetch(`${API_URL}/api/v1/templates`, { headers: auth })
        .then(r => r.json())
        .then((res: { data: WabaTemplate[] }) => {
          setWabaTemplates((res.data || []).filter((t: WabaTemplate) => t.status === "APPROVED"));
        })
        .catch(() => {});
    });
  }, []);

  useEffect(() => {
    setLastResult(null);
  }, [tab, sourceFilter, selectedCampaignId, selectedBroadcastId]);

  useEffect(() => {
    api.segments.templates().then((rows) => {
      const map: Record<string, SegmentTemplate> = {};
      rows.forEach((r) => (map[r.segment] = r));
      setTemplates(map);
    });
  }, []);

  useEffect(() => {
    setDraft(templates[tab]?.message ?? "");
  }, [tab, templates]);

  async function saveTemplate() {
    if (!canManageLeads) return;
    setSavingTpl(true);
    try {
      const updated = await api.segments.saveTemplate(tab, draft);
      setTemplates((prev) => ({ ...prev, [tab]: updated }));
    } catch {
      // no-op
    } finally {
      setSavingTpl(false);
    }
  }

  async function broadcast() {
    if (!canManageLeads) return;
    if (!draft.trim()) return;
    const targetLabel = sourceFilter !== "ALL" ? "filtered" : `${SEGMENT_LABELS[tab]}`;
    if (!confirm(`Send this message to all ${targetLabel} leads?`)) return;
    setBroadcasting(true);
    setLastResult(null);
    try {
      if (sourceFilter !== "ALL") {
        const payload: Parameters<typeof api.leads.broadcast>[0] = {
          message: draft,
          segment: tab,
          source_filter: sourceFilter.toLowerCase(),
        };
        if (sourceFilter === "META_ADS" && selectedCampaignId) {
          payload.ad_campaign_id = selectedCampaignId;
        } else if (sourceFilter === "BROADCAST" && selectedBroadcastId) {
          payload.broadcast_id = selectedBroadcastId;
        }
        const result = await api.leads.broadcast(payload);
        setLastResult(result);
      } else {
        if (draft !== templates[tab]?.message) await saveTemplate();
        const result = await api.segments.broadcast(tab);
        setLastResult(result);
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Broadcast failed");
    } finally {
      setBroadcasting(false);
    }
  }

  function format24hWindow(lastInboundAt?: string | null) {
    if (!lastInboundAt) return <span className="text-on-surface-muted/50">—</span>;
    const lastInbound = new Date(lastInboundAt).getTime();
    const now = new Date().getTime();
    const diffMs = now - lastInbound;
    const hoursLeft = 24 - diffMs / (1000 * 60 * 60);

    if (hoursLeft <= 0) {
      return (
        <span className="inline-flex items-center font-label text-[10px] font-bold text-red-600 bg-red-50/50 px-2 py-0.5 rounded-full border border-red-100">
          Expired
        </span>
      );
    }

    const h = Math.floor(hoursLeft);
    const m = Math.floor((hoursLeft - h) * 60);
    if (h === 0) {
      return (
        <span className="inline-flex items-center font-label text-[10px] font-bold text-amber-600 bg-amber-50/50 px-2 py-0.5 rounded-full border border-amber-100 animate-pulse">
          {m}m left
        </span>
      );
    }
    return (
      <span className="inline-flex items-center font-label text-[10px] font-bold text-emerald-600 bg-emerald-50/50 px-2 py-0.5 rounded-full border border-emerald-100">
        {h}h {m}m left
      </span>
    );
  }

  function getBroadcastWindowText(timestamp: string): string {
    const lastBroadcast = new Date(timestamp).getTime();
    const now = new Date().getTime();
    const diffMs = now - lastBroadcast;
    const hoursLeft = 24 - diffMs / (1000 * 60 * 60);

    if (hoursLeft <= 0) {
      return "Expired";
    }

    const h = Math.floor(hoursLeft);
    const m = Math.floor((hoursLeft - h) * 60);
    if (h === 0) {
      return `${m}m left`;
    }
    return `${h}h ${m}m left`;
  }

  return (
    <div className="min-w-0">
      {composing && (
        <ComposeModal
          onClose={() => setComposing(false)}
          canManageLeads={canManageLeads}
          onSent={() => {
            mutate();
          }}
        />
      )}

      {/* Tabs and Actions merged in a single row */}
      <div className="mb-5 flex min-w-0 flex-col gap-3 border-b border-[#e8e3db] pb-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="grid grid-cols-2 gap-1 rounded-2xl bg-[#e8e3db]/60 p-1 sm:flex sm:w-fit">
          <button
            onClick={() => setPageView("leads")}
            className={pillClass(pageView === "leads")}
          >
            Leads
          </button>
          <button
            onClick={() => setPageView("reengagement")}
            className={pillClass(pageView === "reengagement")}
          >
            Re-engagement
          </button>
        </div>

        <div className="grid grid-cols-2 gap-2 sm:flex sm:items-center">
          <button
            onClick={() => setComposing(true)}
            disabled={!canManageLeads}
            title={canManageLeads ? "New message" : "Read-only role: sending is disabled"}
            className="flex items-center justify-center gap-2 rounded-xl bg-[#1c1917] px-3 py-2 font-label text-xs font-bold text-white shadow-sm transition-all hover:bg-[#292524] disabled:cursor-not-allowed disabled:opacity-40 sm:px-4"
          >
            <Plus size={14} />
            New Message
          </button>
          <button
            onClick={async () => {
              try {
                await api.leads.exportLeads(tab);
                toast.success("Export downloaded");
              } catch (err) {
                toast.error(err instanceof Error ? err.message : "Export failed");
              }
            }}
            className="flex items-center justify-center gap-2 rounded-xl border border-[#e8e3db] bg-white px-3 py-2 font-label text-xs font-bold text-[#1c1917] shadow-sm transition-all hover:bg-[#f0ece4] sm:px-4"
          >
            <Download size={14} />
            Export {SEGMENT_LABELS[tab]}
          </button>
        </div>
      </div>

      {pageView === "reengagement" && (
        <div className="space-y-6">
          <div className="flex gap-2">
            <button
              onClick={() => setReengageTrigger("inbound")}
              className={`rounded-xl px-4 py-2 text-sm ${reengageTrigger === "inbound" ? "bg-on-surface text-surface" : "bg-on-surface/10 text-on-surface"}`}
            >
              Reply Follow-up
            </button>
            <button
              onClick={() => setReengageTrigger("broadcast")}
              className={`rounded-xl px-4 py-2 text-sm ${reengageTrigger === "broadcast" ? "bg-on-surface text-surface" : "bg-on-surface/10 text-on-surface"}`}
            >
              Campaign Follow-up
            </button>
          </div>

          {reengageTrigger === "broadcast" && (
            <label className="block">
              <span className="font-label text-xs uppercase tracking-widest text-on-surface-muted">Broadcast</span>
              <select
                value={selectedBroadcastId}
                onChange={(e) => setSelectedBroadcastId(e.target.value)}
                className="mt-1 w-full max-w-md rounded-xl border border-on-surface/20 px-3 py-2 text-sm"
              >
                <option value="">Select a broadcast…</option>
                {broadcastHistory.filter((b) => b.broadcast_id).map((b) => (
                  <option key={b.broadcast_id} value={b.broadcast_id}>
                    {b.template_name} · {new Date(b.timestamp).toLocaleString()}
                  </option>
                ))}
              </select>
            </label>
          )}

          <ReengagementBuilder
            key={`${reengageTrigger}:${selectedBroadcastId ?? ""}`}
            type={reengageTrigger}
            broadcastId={reengageTrigger === "broadcast" ? selectedBroadcastId : undefined}
            templates={wabaTemplates}
            canManage={canManageLeads}
          />
        </div>
      )}

      {pageView === "leads" && (
      <div>
        <div className="mb-5 flex min-w-0 flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center sm:gap-4">
          {/* Segment tabs */}
          <div className="-mx-1 overflow-x-auto px-1 pb-1 sm:mx-0 sm:overflow-visible sm:p-0">
          <div className="flex w-max gap-1 rounded-2xl bg-[#e8e3db]/60 p-1 sm:w-fit">
            {SEGMENTS.map((seg) => (
              <button
                key={seg}
                onClick={() => setTab(seg)}
                className={cn(
                  "shrink-0 rounded-xl px-4 py-2.5 font-label text-xs font-bold transition-all sm:px-5",
                  tab === seg
                    ? "bg-white text-primary shadow-sm"
                    : "text-[#78716c] hover:text-[#292524]"
                )}
              >
                {SEGMENT_LABELS[seg]}
              </button>
            ))}
          </div>
          </div>

          {/* Source Filter Dropdown */}
          <div className="flex w-full min-w-0 items-center gap-2 rounded-xl border border-surface-mid/80 bg-surface p-2.5 shadow-sm sm:w-auto">
            <span className="shrink-0 font-label text-xs font-bold uppercase tracking-wider text-on-surface-muted">Source:</span>
            <select
              value={sourceFilter}
              onChange={(e) => {
                setSourceFilter(e.target.value);
                setSelectedCampaignId("");
                setSelectedBroadcastId("");
              }}
              className="min-w-0 flex-1 cursor-pointer bg-transparent font-body text-xs font-semibold text-primary focus:outline-none sm:flex-none"
            >
              <option value="ALL">All Leads</option>
              <option value="INBOUND">Inbound Leads</option>
              <option value="ORGANIC">Organic Inbound</option>
              <option value="META_ADS">Meta Ads</option>
              <option value="BROADCAST">Broadcast Specific</option>
            </select>
          </div>

          {/* Conditional Campaign Dropdown */}
          {sourceFilter === "META_ADS" && campaigns.length > 0 && (
            <div className="flex w-full min-w-0 items-center gap-2 rounded-xl border border-surface-mid/80 bg-surface p-2.5 shadow-sm animate-slide-up sm:w-auto">
              <span className="font-label text-xs text-on-surface-muted font-bold uppercase tracking-wider shrink-0">Campaign:</span>
              <select
                value={selectedCampaignId}
                onChange={(e) => setSelectedCampaignId(e.target.value)}
                className="min-w-0 flex-1 cursor-pointer bg-transparent pr-6 font-body text-xs font-semibold text-primary focus:outline-none sm:max-w-[300px]"
              >
                <option value="">Select Campaign</option>
                {campaigns.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.campaign_name}
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* Conditional Broadcast Dropdown */}
          {sourceFilter === "BROADCAST" && broadcastHistory.length > 0 && (
            <div className="flex w-full min-w-0 flex-wrap items-center gap-3 animate-slide-up sm:w-auto">
              <div className="flex w-full min-w-0 items-center gap-2 rounded-xl border border-surface-mid/80 bg-surface p-2.5 shadow-sm sm:w-auto">
                <span className="font-label text-xs text-on-surface-muted font-bold uppercase tracking-wider shrink-0">Broadcast:</span>
                <select
                  value={selectedBroadcastId}
                  onChange={(e) => setSelectedBroadcastId(e.target.value)}
                  className="min-w-0 flex-1 cursor-pointer bg-transparent pr-6 font-body text-xs font-semibold text-primary focus:outline-none sm:max-w-[340px]"
                >
                  <option value="">Select Broadcast</option>
                  {broadcastHistory.map((h) => (
                    <option key={h.broadcast_id} value={h.broadcast_id}>
                      {h.template_name} ({new Date(h.timestamp).toLocaleDateString()} · {getBroadcastWindowText(h.timestamp)})
                    </option>
                  ))}
                </select>
              </div>

              {/* Selected Broadcast 24h Window Badge */}
              {(() => {
                const selectedBroadcast = broadcastHistory.find(h => h.broadcast_id === selectedBroadcastId);
                if (!selectedBroadcast) return null;
                const windowText = getBroadcastWindowText(selectedBroadcast.timestamp);
                return (
                  <div className={cn(
                    "flex items-center gap-1.5 px-3 py-2 rounded-xl border font-label text-xs font-bold shadow-sm",
                    windowText === "Expired"
                      ? "bg-red-50 text-red-600 border-red-100"
                      : "bg-emerald-50 text-emerald-600 border-emerald-100"
                  )}>
                    <Clock size={12} />
                    <span>Broadcast Window: {windowText}</span>
                  </div>
                );
              })()}
            </div>
          )}
        </div>

        <div className="mb-5 rounded-card bg-surface p-4 shadow-card ring-1 ring-[#c4c7c7]/15 sm:mb-6 sm:p-6">
          <div className="mb-3 flex min-w-0 flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <h2 className="font-display text-sm font-bold text-primary">
              {sourceFilter !== "ALL" ? `Action Box — Filtered Leads` : `Action Box — ${SEGMENT_LABELS[tab]} Leads`}
            </h2>
            {lastResult && (
              <p className="font-label text-xs text-on-surface-muted">
                Sent {lastResult.sent} · Failed {lastResult.failed} · Outside 24h window{" "}
                {lastResult.skipped_window}
              </p>
            )}
          </div>
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={3}
            placeholder={sourceFilter !== "ALL" ? "Message to broadcast to filtered leads…" : `Message to broadcast to ${SEGMENT_LABELS[tab]} leads…`}
            className="w-full px-4 py-3 bg-surface-low rounded-xl font-body text-sm text-on-surface border-0 focus:ring-2 focus:ring-primary resize-none"
          />
          <div className="mt-3 flex flex-wrap gap-2">
            {sourceFilter === "ALL" && (
              <button
                onClick={saveTemplate}
            disabled={savingTpl || draft === (templates[tab]?.message ?? "") || !canManageLeads}
                className="flex items-center gap-2 px-4 py-2 bg-surface-low text-on-surface rounded-xl font-label text-xs font-semibold hover:bg-surface-mid transition-colors disabled:opacity-50"
              >
                <Save size={14} />
                {savingTpl ? "Saving…" : "Save"}
              </button>
            )}
            <button
              onClick={broadcast}
            disabled={broadcasting || !draft.trim() || !canManageLeads}
              className="flex items-center gap-2 px-4 py-2 bg-secondary text-white rounded-xl font-label text-xs font-semibold hover:bg-secondary/90 transition-colors disabled:opacity-50"
            >
              <Send size={14} />
              {broadcasting ? "Sending…" : sourceFilter !== "ALL" ? "Send to Filtered Leads" : `Send to ${SEGMENT_LABELS[tab]}`}
            </button>
          </div>
        </div>

        <div className="bg-surface rounded-card shadow-card ring-1 ring-[#c4c7c7]/15">
          {loading ? (
            <div className="p-8 text-center font-body text-on-surface-muted">Loading…</div>
          ) : leads.length === 0 ? (
            <div className="p-8 text-center font-body text-on-surface-muted">No leads found for these filters</div>
          ) : (
            <>
            <div className="space-y-3 p-3 md:hidden">
              {leads.map((lead) => (
                <MobileRecordCard key={lead.id}>
                  <MobileRecordHeader
                    title={lead.phone ? formatPhone(lead.phone) : (lead.name || "No contact")}
                    subtitle={<NameCell lead={lead} onUpdate={(updated) => mutate(leads.map((l) => (l.id === updated.id ? updated : l)), false)} />}
                    aside={
                      <span className="rounded-full bg-primary/10 px-2.5 py-1 font-label text-[11px] font-bold text-primary">
                        {SEGMENT_LABELS[lead.segment] ?? lead.segment}
                      </span>
                    }
                  />
                  <MobileRecordGrid>
                    <MobileRecordField
                      label="Score"
                      value={
                        <span className="flex items-center gap-2">
                          <span className="h-1.5 w-14 overflow-hidden rounded-full bg-surface-mid">
                            <span className="block h-full rounded-full bg-secondary" style={{ width: `${lead.score * 10}%` }} />
                          </span>
                          {lead.score}/10
                        </span>
                      }
                    />
                    <MobileRecordField
                      label="Assigned"
                      value={lead.assigned_to ? (callers.find((c) => c.id === lead.assigned_to)?.name ?? "Caller") : "Unassigned"}
                    />
                    <MobileRecordField label="Source" value={<span className="capitalize">{lead.source}</span>} />
                    <MobileRecordField label="24h Window" value={format24hWindow(lead.last_inbound_at)} />
                    <MobileRecordField label="Added" value={timeAgo(lead.created_at)} />
                    {sourceFilter === "BROADCAST" && (
                      <MobileRecordField label="Broadcast" value={lead.broadcast_sent_at ? timeAgo(lead.broadcast_sent_at) : "Not sent"} />
                    )}
                  </MobileRecordGrid>
                  {role === "owner" && (
                    <div className="mt-4 flex justify-end">
                      <AssignButton
                        leadId={lead.id}
                        currentAssignedTo={lead.assigned_to}
                        callers={callers}
                        onAssigned={(callerId) => {
                          mutate(
                            leads.map((l) =>
                              l.id === lead.id ? { ...l, assigned_to: callerId } : l
                            ),
                            false
                          );
                        }}
                      />
                    </div>
                  )}
                </MobileRecordCard>
              ))}
            </div>
            <table className="hidden w-full md:table">
              <thead>
                <tr className="border-b border-surface-mid">
                  <th className="px-6 py-4 text-left font-label text-xs text-on-surface-muted uppercase tracking-widest">Contact/ID</th>
                  <th className="px-6 py-4 text-left font-label text-xs text-on-surface-muted uppercase tracking-widest">Name</th>
                  <th className="px-6 py-4 text-left font-label text-xs text-on-surface-muted uppercase tracking-widest">Score</th>
                  <th className="px-6 py-4 text-left font-label text-xs text-on-surface-muted uppercase tracking-widest">Assigned To</th>
                  <th className="px-6 py-4 text-left font-label text-xs text-on-surface-muted uppercase tracking-widest">Source</th>
                  {sourceFilter === "BROADCAST" && (
                    <th className="px-6 py-4 text-left font-label text-xs text-on-surface-muted uppercase tracking-widest">Broadcast Sent</th>
                  )}
                  <th className="px-6 py-4 text-left font-label text-xs text-on-surface-muted uppercase tracking-widest">24h Window</th>
                  <th className="px-6 py-4 text-left font-label text-xs text-on-surface-muted uppercase tracking-widest">Added</th>
                  {role === "owner" && (
                    <th className="px-6 py-4 text-left font-label text-xs text-on-surface-muted uppercase tracking-widest">Actions</th>
                  )}
                </tr>
              </thead>
              <tbody>
                {leads.map((lead, i) => (
                  <tr
                    key={lead.id}
                    className={`border-b border-surface-mid/50 hover:bg-surface-low transition-colors ${
                      i % 2 === 0 ? "" : "bg-surface-low/30"
                    }`}
                  >
                    <td className="px-6 py-4 font-body text-sm text-on-surface">
                      {lead.phone ? formatPhone(lead.phone) : (lead.source === "telegram" ? `@${lead.tg_username || "unknown"}` : (lead.source === "instagram" ? lead.ig_user_id : (lead.source === "facebook" ? lead.fb_user_id : "No Contact")))}
                    </td>
                    <td className="px-6 py-4">
                      <NameCell
                        lead={lead}
                        onUpdate={(updated) => {
                          mutate(
                            leads.map((l) => (l.id === updated.id ? updated : l)),
                            false
                          );
                        }}
                      />
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-2">
                        <div className="w-16 h-1.5 rounded-full bg-surface-mid overflow-hidden">
                          <div className="h-full rounded-full bg-secondary transition-all" style={{ width: `${lead.score * 10}%` }} />
                        </div>
                        <span className="font-label text-xs text-on-surface-muted">{lead.score}</span>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      {lead.assigned_to ? (
                        <span className="font-label text-xs font-semibold text-ink">
                          {callers.find((c) => c.id === lead.assigned_to)?.name ?? "Caller"}
                        </span>
                      ) : (
                        <span className="font-label text-xs text-ink-muted">—</span>
                      )}
                    </td>
                    <td className="px-6 py-4 font-label text-xs text-on-surface-muted capitalize">{lead.source}</td>
                    {sourceFilter === "BROADCAST" && (
                      <td className="px-6 py-4 font-label text-xs text-on-surface-muted">{lead.broadcast_sent_at ? timeAgo(lead.broadcast_sent_at) : "—"}</td>
                    )}
                    <td className="px-6 py-4">
                      {format24hWindow(lead.last_inbound_at)}
                    </td>
                    <td className="px-6 py-4 font-label text-xs text-on-surface-muted">{timeAgo(lead.created_at)}</td>
                    {role === "owner" && (
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-2">
                          <AssignButton
                            leadId={lead.id}
                            currentAssignedTo={lead.assigned_to}
                            callers={callers}
                            onAssigned={(callerId) => {
                              mutate(
                                leads.map((l) =>
                                  l.id === lead.id ? { ...l, assigned_to: callerId } : l
                                ),
                                false
                              );
                            }}
                          />
                        </div>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
            </>
          )}
        </div>
      </div>
      )}
    </div>
  );
}
