"use client";
import { useEffect, useState, useCallback } from "react";
import { Phone, RefreshCw, Download, Inbox, User, Sparkles, Search, Clock } from "lucide-react";
import { api, Caller, Lead } from "@/lib/api";
import { formatPhone, timeAgo } from "@/lib/utils";
import { toast } from "sonner";
import NotesHistoryModal from "./components/notes-history-modal";
import NumpadDialer from "./components/NumpadDialer";
import LeadDetailPanel from "./components/LeadDetailPanel";
import CockpitModals from "./components/CockpitModals";
import { useCallingCockpit } from "./lib/useCallingCockpit";
import { CoachingOneLiner } from "@/components/CoachingDigest";

export default function CallerView({ callerId }: { callerId: string | null }) {
  // caller profile + my assigned queue
  const [myStatus, setMyStatus] = useState<"active" | "break" | "logged_out">("active");
  const [myLeads, setMyLeads] = useState<Lead[]>([]);
  const [lastCalledMap, setLastCalledMap] = useState<Record<string, string>>({});
  const [exporting, setExporting] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [queueSubTab, setQueueSubTab] = useState<"new" | "callback" | "in_progress" | "closed" | "dialer">("new");
  const [historyLead, setHistoryLead] = useState<Lead | null>(null);

  // Load my assigned leads (the cockpit owns callbacks/config/wrap-ups itself).
  const loadQueue = useCallback(async () => {
    try {
      const [rawCallers, rawLeads] = await Promise.all([
        api.callers.list(),
        api.leads.list({ assigned_to: callerId || undefined, limit: 1000 }),
      ]);
      const callers = Array.isArray(rawCallers) ? rawCallers : (rawCallers?.data ?? []);
      const leads = Array.isArray(rawLeads) ? rawLeads : [];
      const me = callers.find((c: Caller) => c.id === callerId) || null;
      if (me) setMyStatus((me.status as "active" | "break" | "logged_out") || "active");

      const dialable = leads.filter((l: Lead) => l != null && l.phone && l.phone.trim() !== "");
      const sorted = dialable.sort((a: Lead, b: Lead) => (b.score ?? 0) - (a.score ?? 0));
      setMyLeads(sorted);

      const ids = sorted.map((l: Lead) => l.id).filter(Boolean);
      if (ids.length) api.calls.recentByLeads(ids).then(setLastCalledMap).catch(() => {});
    } catch (err) {
      console.error("CallerView load error:", err);
    }
  }, [callerId]);

  useEffect(() => { loadQueue(); }, [loadQueue]);

  const cockpit = useCallingCockpit({ callerId, blockingWrapups: true, refreshQueue: loadQueue });

  async function handleDownloadCSV() {
    setExporting(true);
    try {
      await api.leads.exportAssigned();
      toast.success("CSV downloaded successfully");
    } catch (err) {
      toast.error("Failed to download CSV");
      console.error(err);
    } finally {
      setExporting(false);
    }
  }

  const filteredLeads = myLeads.filter((lead) => {
    if (!lead) return false;
    const query = searchQuery.toLowerCase().trim();
    if (!query) return true;
    const nameMatch = lead.name?.toLowerCase().includes(query) ?? false;
    const phoneMatch = lead.phone?.toLowerCase().includes(query) ?? false;
    return nameMatch || phoneMatch;
  });

  const newLeads = filteredLeads.filter((l) => !l.call_status || l.call_status === "new");
  const callbackLeads = filteredLeads.filter((l) => l.call_status === "callback");
  const inProgressLeads = filteredLeads.filter((l) => l.call_status === "in_progress");
  const closedLeads = filteredLeads.filter((l) => l.call_status && ["converted", "not_interested", "dnc", "unreachable"].includes(l.call_status));

  const activeSubTabLeads =
    queueSubTab === "new" ? newLeads :
    queueSubTab === "callback" ? callbackLeads :
    queueSubTab === "in_progress" ? inProgressLeads :
    queueSubTab === "dialer" ? [] :
    closedLeads;

  return (
    <div className="flex min-h-[calc(100vh-8rem)] flex-col bg-transparent xl:h-[calc(100vh-4rem)]">
      <CoachingOneLiner callerId={callerId} />
      <div className="grid flex-1 grid-cols-1 gap-4 pb-4 xl:grid-cols-12 xl:min-h-0">
        {/* Left Side: Lead List (4/12) */}
        <div className="flex flex-col gap-5 pr-0 xl:col-span-4 xl:min-h-0 xl:pr-1">
          <div className="flex flex-1 flex-col rounded-3xl border border-[#e8e3db] bg-[#faf8f5] p-4 shadow-sm xl:min-h-0 xl:p-5">
            <div className="flex items-center justify-between mb-4 shrink-0">
              <div>
                <h2 className="font-display text-xl font-extrabold text-[#1c1917] tracking-tight">Lead Queue</h2>
                <p className="font-body text-xs text-[#78716c] mt-0.5">{myLeads.length} leads assigned</p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={handleDownloadCSV}
                  disabled={exporting || myLeads.length === 0}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-white border border-[#e8e3db]/80 rounded-xl font-label text-xs font-bold hover:bg-[#faf8f5] transition-all text-[#44403c] shadow-sm hover:border-primary hover:text-primary disabled:opacity-50 hover:scale-[1.01] active:scale-[0.99]"
                  title="Download CSV of all assigned leads"
                >
                  {exporting ? <RefreshCw size={12} className="animate-spin text-primary" /> : <Download size={12} />}
                  Export CSV
                </button>
                <button
                  onClick={cockpit.handleCallNext}
                  disabled={cockpit.dialingNext || myStatus !== "active"}
                  className="flex items-center gap-1.5 px-4 py-2 bg-gradient-to-r from-primary to-primary-dark text-white rounded-2xl font-label text-xs font-bold transition-all shadow-sm hover:scale-[1.02] active:scale-[0.98] disabled:opacity-50"
                  title="Call next hot lead in queue"
                >
                  {cockpit.dialingNext ? <RefreshCw size={12} className="animate-spin mr-1" /> : <Sparkles size={12} className="mr-1 fill-white text-white" />}
                  Call Next
                </button>
              </div>
            </div>

            {/* Search */}
            <div className="mb-4 shrink-0">
              <div className="relative">
                <Search size={14} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-[#a8a29e]" />
                <input
                  type="text"
                  placeholder="Search by name or phone..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full pl-10 pr-4 py-2.5 bg-[#faf8f5] border border-[#e8e3db] rounded-xl text-xs font-body focus:outline-none focus:ring-2 focus:ring-primary focus:bg-white transition-all shadow-inner"
                />
              </div>
            </div>

            {/* Sub-tabs */}
            <div className="flex gap-0.5 p-0.5 bg-[#e8e3db]/60 rounded-2xl shrink-0 mb-4">
              {[
                { id: "new", label: `To Call (${newLeads.length})` },
                { id: "callback", label: `Callbacks (${callbackLeads.length})` },
                { id: "in_progress", label: `In Prog (${inProgressLeads.length})` },
                { id: "closed", label: `Closed (${closedLeads.length})` },
                { id: "dialer", label: "Manual Dial" },
              ].map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setQueueSubTab(tab.id as typeof queueSubTab)}
                  className={`flex-1 py-1.5 px-0 rounded-xl font-label text-[9.5px] font-extrabold text-center whitespace-nowrap transition-all ${
                    queueSubTab === tab.id ? "bg-white text-orange-600 shadow-sm" : "text-amber-700/70 hover:text-[#292524]"
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            {/* Lead cards or numpad */}
            {queueSubTab === "dialer" ? (
              <div className="flex-1 overflow-y-auto flex flex-col items-center pt-4 pb-2">
                <NumpadDialer value={cockpit.manualPhone} onChange={cockpit.setManualPhone} onDial={cockpit.manualDialWithGuard} dialing={cockpit.manualDialing} />
              </div>
            ) : myLeads.length === 0 ? (
              <div className="text-center py-12 flex-1 flex flex-col justify-center items-center">
                <div className="w-12 h-12 bg-[#faf8f5] rounded-full flex items-center justify-center text-[#a8a29e] border border-[#f0ece4] mb-3">
                  <Inbox size={18} />
                </div>
                <p className="font-body text-sm font-semibold text-[#78716c]">No leads assigned to you</p>
                <p className="font-label text-xs text-[#a8a29e] mt-1">Queue automations will route hot leads as they arrive.</p>
              </div>
            ) : activeSubTabLeads.length === 0 ? (
              <div className="text-center py-12 flex-1 flex flex-col justify-center items-center">
                <div className="w-12 h-12 bg-[#faf8f5] rounded-full flex items-center justify-center text-[#a8a29e] border border-[#f0ece4] mb-3">
                  <Inbox size={18} />
                </div>
                <p className="font-body text-sm font-semibold text-[#78716c]">No matching leads found</p>
                <p className="font-label text-xs text-[#a8a29e] mt-1">Try switching tabs or adjusting your search query.</p>
              </div>
            ) : (
              <div className="flex-1 overflow-y-auto space-y-2 pr-1">
                {activeSubTabLeads.map((lead) => {
                  if (!lead) return null;
                  const isSelected = cockpit.selectedLeadId === lead.id;

                  let borderAccent = "border-l-primary";
                  let avatarBg = "bg-primary";
                  let callBtnBg = "bg-emerald-500 hover:bg-emerald-600";

                  if (lead.score >= 8) {
                    borderAccent = "border-l-red-500";
                    avatarBg = "bg-red-500";
                    callBtnBg = "bg-rose-500 hover:bg-rose-600 shadow-rose-500/10";
                  } else if (lead.call_status === "callback") {
                    borderAccent = "border-l-amber-500";
                    avatarBg = "bg-amber-500";
                    callBtnBg = "bg-amber-500 hover:bg-amber-600 shadow-amber-500/10";
                  } else if (lead.call_status && ["converted", "not_interested", "dnc", "unreachable"].includes(lead.call_status)) {
                    borderAccent = "border-l-[#d6cfc9]";
                    avatarBg = "bg-[#a8a29e]";
                    callBtnBg = "bg-[#a8a29e] hover:bg-[#78716c] shadow-[#78716c]/10";
                  }

                  return (
                    <div
                      key={lead.id}
                      onClick={() => cockpit.setSelectedLeadId(lead.id)}
                      className={`rounded-2xl border-y border-r border-l-[6px] transition-all duration-200 cursor-pointer p-3 flex items-center justify-between gap-3 ${borderAccent} ${
                        isSelected
                          ? "bg-gradient-to-r from-primary-light/70 to-purple-50/20 border-primary-muted shadow-[0_4px_15px_rgba(99,102,241,0.06)] ring-1 ring-primary/10 translate-x-1"
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
                            {lead.score >= 7 && (
                              <span className="px-1.5 py-0.5 bg-rose-100 text-rose-600 rounded font-label text-[8px] font-black uppercase tracking-wider">HOT</span>
                            )}
                            <span className="px-1.5 py-0.5 bg-primary-light text-primary rounded font-label text-[8px] font-black uppercase">SEG {lead.segment}</span>
                            {lead.call_status === "callback" && (
                              <span className="px-1.5 py-0.5 bg-amber-100 text-amber-800 rounded font-label text-[8px] font-black uppercase">CALLBACK</span>
                            )}
                          </div>
                          <div className="flex items-center gap-1.5 mt-0.5">
                            <p className="font-label text-xs text-[#78716c]">{lead.name ? formatPhone(lead.phone) + " · " : ""}Score {lead.score}/10</p>
                          </div>
                          <div className="flex items-center gap-1 text-[10px] text-[#a8a29e] mt-0.5">
                            <Clock size={10} />
                            {lead.call_status === "callback" ? (
                              <span>Scheduled callback</span>
                            ) : lastCalledMap[lead.id] ? (
                              <span>Called {timeAgo(lastCalledMap[lead.id])}</span>
                            ) : (
                              <span>Not called yet</span>
                            )}
                          </div>
                        </div>
                      </div>

                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          cockpit.dialWithGuard(lead.id, lead);
                        }}
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
          </div>
        </div>

        {/* Right Side: Lead Profile (8/12) */}
        <div className="flex min-h-[380px] flex-col overflow-hidden rounded-3xl border border-[#e8e3db] bg-[#faf8f5] shadow-sm xl:col-span-8 xl:min-h-0">
          <div className="flex-1 overflow-y-auto">
            {!cockpit.selectedLeadId ? (
              <div className="min-h-full flex flex-col items-center justify-center p-12 text-center bg-gradient-to-br from-[#faf8f5]/40 to-primary-light/10">
                <div className="relative mb-6">
                  <div className="absolute inset-0 bg-primary/5 blur-2xl rounded-full scale-150 animate-pulse" />
                  <div className="relative p-6 rounded-3xl bg-white border border-[#f0ece4] shadow-md text-primary">
                    <Sparkles size={38} className="text-primary" />
                  </div>
                </div>
                <h3 className="font-display text-xl font-extrabold text-[#1c1917] tracking-tight">Lead Profile Workspace</h3>
                <p className="font-body text-sm text-[#78716c] max-w-md mt-2 leading-relaxed">
                  Choose a lead from your active queue on the left to review campaign source attribution details, previous calls history, and log feedback notes.
                </p>
                <div className="grid grid-cols-2 gap-4 mt-8 w-full max-w-xs">
                  <div className="p-4 bg-white border border-[#f0ece4] rounded-2xl shadow-sm text-left">
                    <span className="text-[10px] font-bold text-[#a8a29e] uppercase tracking-wider block">Total Queue</span>
                    <span className="text-xl font-bold text-[#292524] mt-1 block">{myLeads.length}</span>
                  </div>
                  <div className="p-4 bg-white border border-[#f0ece4] rounded-2xl shadow-sm text-left">
                    <span className="text-[10px] font-bold text-[#a8a29e] uppercase tracking-wider block">Today Callbacks</span>
                    <span className="text-xl font-bold text-[#292524] mt-1 block">{cockpit.todayCallbacks.length}</span>
                  </div>
                </div>
              </div>
            ) : (
              <LeadDetailPanel {...cockpit.leadDetailProps} setHistoryLead={setHistoryLead} />
            )}
          </div>
        </div>
      </div>

      {historyLead && <NotesHistoryModal lead={historyLead} onClose={() => setHistoryLead(null)} />}
      <CockpitModals cockpit={cockpit} />
    </div>
  );
}
