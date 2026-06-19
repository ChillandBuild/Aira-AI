"use client";
import { useCallback, useEffect, useState } from "react";
import { Phone, ChevronDown, Settings, Sparkles, User, Inbox, Clock } from "lucide-react";
import type { Caller, Lead } from "@/lib/api";
import { useAdminDashboard, useLeads } from "@/hooks/useApi";
import type { AdminDashboardData } from "@/hooks/useApi";
import { formatPhone } from "@/lib/utils";
import { TelecallingConfigPanel } from "../settings/TelecallingConfigPanel";
import NotesHistoryModal from "./components/notes-history-modal";
import LeadDetailPanel from "./components/LeadDetailPanel";
import CockpitModals from "./components/CockpitModals";
import NumpadDialer from "./components/NumpadDialer";
import { useCallingCockpit } from "./lib/useCallingCockpit";

export default function AdminView({ fallbackData }: { fallbackData?: AdminDashboardData }) {
  const { data: dashboard, mutate: refreshDashboard } = useAdminDashboard(fallbackData);
  const callers: Caller[] = dashboard?.callers ?? [];

  // Who the call dials as (null = admin self).
  const [selectedCallerId, setSelectedCallerId] = useState<string | null>(null);
  const [showConfigModal, setShowConfigModal] = useState(false);

  // Left-panel: Queue vs Manual Dial
  const [leftTab, setLeftTab] = useState<"queue" | "dialer">("queue");
  const [historyLead, setHistoryLead] = useState<Lead | null>(null);

  // Queue filters
  const [queueSegment, setQueueSegment] = useState<string>("all");
  const [queueStatus, setQueueStatus] = useState<string>("all");
  const [queueAssignedTo, setQueueAssignedTo] = useState<string>("all");

  const { data: queueLeadsData, mutate: refreshQueueLeads } = useLeads({
    segment: queueSegment !== "all" ? queueSegment : undefined,
    assigned_to: (queueAssignedTo !== "all" && queueAssignedTo !== "unassigned") ? queueAssignedTo : undefined,
    limit: 50,
  });

  const refreshQueue = useCallback(() => {
    refreshQueueLeads();
    refreshDashboard();
  }, [refreshQueueLeads, refreshDashboard]);

  const cockpit = useCallingCockpit({ callerId: selectedCallerId, blockingWrapups: false, refreshQueue });

  const filteredQueueLeads = (queueLeadsData ?? []).filter((lead) => {
    if (queueStatus !== "all" && lead.call_status !== queueStatus) return false;
    if (queueAssignedTo === "unassigned" && lead.assigned_to) return false;
    return true;
  });

  // Lock body scroll when the config modal is open
  useEffect(() => {
    document.body.style.overflow = showConfigModal ? "hidden" : "";
    return () => { document.body.style.overflow = ""; };
  }, [showConfigModal]);

  const selectedCallerName = callers.find((c) => c.id === selectedCallerId)?.name ?? "Admin (me)";

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)] bg-transparent">
      <div className="flex-1 grid grid-cols-12 gap-4 min-h-0 pb-4">
        {/* Left Side: Admin Queue (4/12) */}
        <div className="col-span-4 flex flex-col gap-5 min-h-0 pr-1">
          <div className="flex-1 bg-[#faf8f5] rounded-3xl p-5 shadow-sm border border-[#e8e3db] flex flex-col min-h-0">
            {/* Header: title + Calling as + Config */}
            <div className="flex items-start justify-between mb-4 shrink-0 gap-2">
              <div>
                <h2 className="font-manrope text-xl font-extrabold text-[#1c1917] tracking-tight">Lead Queue</h2>
                <p className="font-manrope text-xs text-[#78716c] mt-0.5">
                  Calling as <span className="text-[#5b21b6] font-semibold">{selectedCallerName}</span>
                </p>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <button
                  onClick={() => setShowConfigModal(true)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-white border border-[#e8e3db]/80 hover:border-amber-300 hover:text-amber-600 font-manrope text-xs font-bold transition-colors shadow-sm"
                >
                  <Settings size={13} /> Config
                </button>
              </div>
            </div>

            {/* Calling as selector */}
            <div className="mb-3 shrink-0">
              <label className="block font-manrope text-[9px] text-[#a8a29e] uppercase tracking-widest mb-1 font-extrabold">Calling as</label>
              <div className="relative">
                <select
                  value={selectedCallerId || ""}
                  onChange={(e) => setSelectedCallerId(e.target.value || null)}
                  className="w-full appearance-none pl-3 pr-8 py-2 rounded-xl bg-white border border-[#e8e3db]/80 font-manrope text-xs font-semibold text-[#44403c] focus:outline-none focus:ring-2 focus:ring-[#5b21b6] cursor-pointer"
                >
                  <option value="">Admin (me)</option>
                  {callers.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
                <ChevronDown size={13} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[#a8a29e] pointer-events-none" />
              </div>
            </div>

            {/* Queue / Manual Dial tabs */}
            <div className="flex gap-0.5 p-0.5 bg-[#e8e3db]/60 rounded-2xl shrink-0 mb-4">
              {[
                { id: "queue", label: "Queue" },
                { id: "dialer", label: "Manual Dial" },
              ].map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setLeftTab(tab.id as typeof leftTab)}
                  className={`flex-1 py-1.5 rounded-xl font-label text-[11px] font-extrabold text-center transition-all ${
                    leftTab === tab.id ? "bg-white text-orange-600 shadow-sm" : "text-amber-700/70 hover:text-[#292524]"
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            {leftTab === "dialer" ? (
              <div className="flex-1 overflow-y-auto flex flex-col items-center pt-4 pb-2">
                <NumpadDialer value={cockpit.manualPhone} onChange={cockpit.setManualPhone} onDial={cockpit.manualDialWithGuard} dialing={cockpit.manualDialing} />
              </div>
            ) : (
              <>
                {/* Filters */}
                <div className="grid grid-cols-3 gap-2 mb-4 shrink-0">
                  {[
                    { value: queueSegment, set: setQueueSegment, label: "Segment", opts: [["all", "All Seg"], ["A", "A"], ["B", "B"], ["C", "C"], ["D", "D"]] },
                    { value: queueStatus, set: setQueueStatus, label: "Status", opts: [["all", "All"], ["new", "New"], ["in_progress", "In Prog"], ["callback", "Callback"], ["converted", "Converted"], ["not_interested", "Not Int."], ["dnc", "DNC"], ["unreachable", "Unreach."]] },
                    { value: queueAssignedTo, set: setQueueAssignedTo, label: "Assigned", opts: [["all", "All"], ["unassigned", "Unassigned"], ...callers.map((c) => [c.id, c.name] as [string, string])] },
                  ].map((f) => (
                    <div key={f.label}>
                      <label className="block font-label text-[8px] text-[#a8a29e] uppercase tracking-widest mb-1 font-extrabold">{f.label}</label>
                      <div className="relative">
                        <select
                          value={f.value}
                          onChange={(e) => f.set(e.target.value)}
                          className="w-full appearance-none pl-2 pr-6 py-1.5 rounded-lg bg-white border border-[#e8e3db]/80 font-body text-[11px] font-semibold text-[#44403c] focus:outline-none focus:ring-2 focus:ring-indigo-500 cursor-pointer"
                        >
                          {f.opts.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                        </select>
                        <ChevronDown size={11} className="absolute right-1.5 top-1/2 -translate-y-1/2 text-[#a8a29e] pointer-events-none" />
                      </div>
                    </div>
                  ))}
                </div>

                {/* Lead cards */}
                {filteredQueueLeads.length === 0 ? (
                  <div className="text-center py-12 flex-1 flex flex-col justify-center items-center">
                    <div className="w-12 h-12 bg-[#faf8f5] rounded-full flex items-center justify-center text-[#a8a29e] border border-[#f0ece4] mb-3">
                      <Inbox size={18} />
                    </div>
                    <p className="font-body text-sm font-semibold text-[#78716c]">No leads match the filters</p>
                    <p className="font-label text-xs text-[#a8a29e] mt-1">Adjust segment, status, or assignment above.</p>
                  </div>
                ) : (
                  <div className="flex-1 overflow-y-auto space-y-2 pr-1">
                    {filteredQueueLeads.map((lead) => {
                      const assignedCaller = callers.find((c) => c.id === lead.assigned_to);
                      const isSelected = cockpit.selectedLeadId === lead.id;

                      let borderAccent = "border-l-indigo-400";
                      let avatarBg = "bg-indigo-500";
                      let callBtnBg = "bg-emerald-500 hover:bg-emerald-600";
                      if (lead.score >= 8) {
                        borderAccent = "border-l-red-500"; avatarBg = "bg-red-500"; callBtnBg = "bg-rose-500 hover:bg-rose-600";
                      } else if (lead.call_status === "callback") {
                        borderAccent = "border-l-amber-500"; avatarBg = "bg-amber-500"; callBtnBg = "bg-amber-500 hover:bg-amber-600";
                      } else if (lead.call_status && ["converted", "not_interested", "dnc", "unreachable"].includes(lead.call_status)) {
                        borderAccent = "border-l-[#d6cfc9]"; avatarBg = "bg-[#a8a29e]"; callBtnBg = "bg-[#a8a29e] hover:bg-[#78716c]";
                      }

                      return (
                        <div
                          key={lead.id}
                          onClick={() => cockpit.setSelectedLeadId(lead.id)}
                          className={`rounded-2xl border-y border-r border-l-[6px] transition-all duration-200 cursor-pointer p-3 flex items-center justify-between gap-3 ${borderAccent} ${
                            isSelected
                              ? "bg-gradient-to-r from-indigo-50/70 to-purple-50/20 border-indigo-200 shadow-[0_4px_15px_rgba(99,102,241,0.06)] ring-1 ring-indigo-500/10 translate-x-1"
                              : "bg-[#faf8f5]/30 border-[#f0ece4] hover:bg-[#faf8f5] hover:shadow-sm"
                          }`}
                        >
                          <div className="flex items-center gap-3 min-w-0 flex-1">
                            <div className={`w-9 h-9 rounded-full flex items-center justify-center font-display text-xs font-bold text-white shrink-0 ${avatarBg}`}>
                              {lead.name ? lead.name.charAt(0).toUpperCase() : <User size={14} />}
                            </div>
                            <div className="min-w-0 flex-1">
                              <div className="flex items-center gap-1.5 flex-wrap">
                                <p className="font-body text-sm font-bold text-[#292524] truncate">{lead.name || formatPhone(lead.phone)}</p>
                                {lead.score >= 7 && <span className="px-1.5 py-0.5 bg-rose-100 text-rose-600 rounded font-label text-[8px] font-black uppercase tracking-wider">HOT</span>}
                                <span className="px-1.5 py-0.5 bg-indigo-50 text-indigo-700 rounded font-label text-[8px] font-black uppercase">SEG {lead.segment}</span>
                              </div>
                              <div className="flex items-center gap-1.5 mt-0.5">
                                <p className="font-label text-xs text-[#78716c]">{lead.name ? formatPhone(lead.phone) + " · " : ""}Score {lead.score}/10</p>
                              </div>
                              <div className="flex items-center gap-1 text-[10px] text-[#a8a29e] mt-0.5">
                                <Clock size={10} />
                                <span>{assignedCaller ? assignedCaller.name : <span className="text-amber-500">Unassigned</span>}</span>
                              </div>
                            </div>
                          </div>
                          <button
                            onClick={(e) => { e.stopPropagation(); cockpit.dialWithGuard(lead.id, lead); }}
                            disabled={cockpit.dialing === lead.id}
                            className={`p-2.5 rounded-xl transition-all shadow-sm shrink-0 flex items-center justify-center text-white ${callBtnBg} hover:scale-105 active:scale-95`}
                          >
                            <Phone size={14} className="fill-white" />
                          </button>
                        </div>
                      );
                    })}
                  </div>
                )}
              </>
            )}
          </div>
        </div>

        {/* Right Side: Lead Profile (8/12) — identical to telecaller cockpit */}
        <div className="col-span-8 flex flex-col min-h-0 bg-[#faf8f5] rounded-3xl border border-[#e8e3db] shadow-sm overflow-hidden">
          <div className="flex-1 overflow-y-auto">
            {!cockpit.selectedLeadId ? (
              <div className="min-h-full flex flex-col items-center justify-center p-12 text-center bg-gradient-to-br from-[#faf8f5]/40 to-indigo-50/10">
                <div className="relative mb-6">
                  <div className="absolute inset-0 bg-indigo-400/5 blur-2xl rounded-full scale-150 animate-pulse" />
                  <div className="relative p-6 rounded-3xl bg-white border border-[#f0ece4] shadow-md text-indigo-500">
                    <Sparkles size={38} className="text-indigo-500" />
                  </div>
                </div>
                <h3 className="font-display text-xl font-extrabold text-[#1c1917] tracking-tight">Lead Profile Workspace</h3>
                <p className="font-body text-sm text-[#78716c] max-w-md mt-2 leading-relaxed">
                  Pick a lead from the queue on the left to review attribution, call history, and log feedback — then dial as {selectedCallerName}.
                </p>
              </div>
            ) : (
              <LeadDetailPanel {...cockpit.leadDetailProps} setHistoryLead={setHistoryLead} />
            )}
          </div>
        </div>
      </div>

      {historyLead && <NotesHistoryModal lead={historyLead} onClose={() => setHistoryLead(null)} />}

      {showConfigModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm cursor-pointer"
          onClick={() => setShowConfigModal(false)}
        >
          <div className="w-full max-w-2xl max-h-[90vh] overflow-y-auto cursor-default" onClick={(e) => e.stopPropagation()}>
            <TelecallingConfigPanel />
          </div>
        </div>
      )}

      <CockpitModals cockpit={cockpit} />
    </div>
  );
}
