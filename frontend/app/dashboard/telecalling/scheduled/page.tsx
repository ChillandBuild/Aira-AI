"use client";
import { useEffect, useState, useCallback } from "react";
import { toast } from "sonner";
import {
  Phone,
  RefreshCw,
  Check,
  Calendar,
  Clock,
  AlertTriangle,
  ChevronRight,
  Inbox,
  User,
  Zap,
  Shield,
  MessageSquare,
  FileText,
  X,
  PhoneCall,
  Activity,
  Award,
  Sparkles
} from "lucide-react";
import { api, CallbackBoardItem, CallLog } from "@/lib/api";
import { formatPhone, timeAgo } from "@/lib/utils";
import { fetchAllNotes, markCallbackDone } from "../lib/notes-api";
import type { Note } from "../types";
import { usePolling } from "@/hooks/usePolling";
import { useActiveCall } from "../../contexts/ActiveCallContext";
import { useAuthRole } from "../../contexts/AuthRoleContext";

type GroupedCallbacks = {
  overdue: CallbackBoardItem[];
  today: CallbackBoardItem[];
  tomorrow: CallbackBoardItem[];
  upcoming: CallbackBoardItem[];
};

function groupCallbacks(cbs: CallbackBoardItem[]): GroupedCallbacks {
  const now = new Date();
  const todayStr = now.toDateString();
  const tomorrowDate = new Date(now);
  tomorrowDate.setDate(tomorrowDate.getDate() + 1);
  const tomorrowStr = tomorrowDate.toDateString();

  const groups: GroupedCallbacks = { overdue: [], today: [], tomorrow: [], upcoming: [] };
  for (const cb of cbs) {
    const d = new Date(cb.scheduled_for);
    if (d < now) {
      groups.overdue.push(cb);
    } else if (d.toDateString() === todayStr) {
      groups.today.push(cb);
    } else if (d.toDateString() === tomorrowStr) {
      groups.tomorrow.push(cb);
    } else {
      groups.upcoming.push(cb);
    }
  }
  return groups;
}

export default function ScheduledCallsPage() {
  const [callbacks, setCallbacks] = useState<CallbackBoardItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [markingDone, setMarkingDone] = useState<string | null>(null);
  const { setActiveCall: setActiveCallCtx } = useActiveCall();
  const { role, callerId } = useAuthRole();

  // Context Handoff Modal State
  const [handoffCallback, setHandoffCallback] = useState<CallbackBoardItem | null>(null);
  const [notes, setNotes] = useState<Note[]>([]);
  const [callLogs, setCallLogs] = useState<CallLog[]>([]);
  const [loadingHandoff, setLoadingHandoff] = useState(false);
  const [takeoverLoading, setTakeoverLoading] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await api.followUps.callbacksBoard();
      setCallbacks(Array.isArray(res?.data) ? res.data : []);
    } catch {
      toast.error("Failed to load scheduled calls");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Poll every 10 seconds to keep caller statuses and assignments in sync
  usePolling(load, 10_000);

  async function handleMarkDone(jobId: string) {
    setMarkingDone(jobId);
    try {
      await markCallbackDone(jobId);
      setCallbacks((prev) => prev.filter((c) => c.id !== jobId));
      toast.success("Callback marked as completed");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to mark done");
    } finally {
      setMarkingDone(null);
    }
  }

  async function handleCallLead(cb: CallbackBoardItem) {
    if (!callerId) {
      toast.error("No caller profile found");
      return;
    }
    try {
      const res = await api.calls.initiate({ leadId: cb.lead_id, callbackJobId: cb.id }, callerId);
      setActiveCallCtx({
        leadId: res.lead_id ?? cb.lead_id,
        name: res.lead_name ?? cb.lead.name ?? null,
        phone: cb.lead.phone ?? "",
        callLogId: res.call_log_id ?? null,
      });
      toast.success(`Calling ${cb.lead.name || cb.lead.phone}...`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Call failed");
    }
  }

  async function handleOpenTakeoverHandoff(cb: CallbackBoardItem) {
    setHandoffCallback(cb);
    setLoadingHandoff(true);
    setNotes([]);
    setCallLogs([]);
    try {
      const [fetchedNotes, fetchedLogs] = await Promise.all([
        fetchAllNotes(cb.lead_id).catch(() => []),
        api.leads.callLogs(cb.lead_id)
      ]);
      setNotes(Array.isArray(fetchedNotes) ? fetchedNotes : []);
      setCallLogs(Array.isArray(fetchedLogs) ? fetchedLogs : []);
    } catch (err) {
      toast.error("Failed to load lead context details");
      console.error(err);
    } finally {
      setLoadingHandoff(false);
    }
  }

  async function handleConfirmTakeover(cb: CallbackBoardItem) {
    if (!callerId) {
      toast.error("You must be logged in as a telecaller to take over leads");
      return;
    }
    setTakeoverLoading(true);
    try {
      await api.leads.takeover(cb.lead_id);
      toast.success("Callback claimed");

      // Close modal and refresh board
      setHandoffCallback(null);
      load();
    } catch (err) {
      if ((err as { status?: number })?.status === 409) {
        toast.error("Already claimed by another caller");
        setHandoffCallback(null);
        load();
        return;
      }
      toast.error(err instanceof Error ? err.message : "Claim failed");
    } finally {
      setTakeoverLoading(false);
    }
  }

  function checkTakeoverEligible(cb: CallbackBoardItem) {
    // Claimable purely on time: 15 minutes past the scheduled slot, regardless of
    // anyone's status. Anyone with a caller profile (incl. the admin) can claim.
    if (!callerId) return false;
    if (cb.lead.assigned_to === callerId) return false;
    const scheduledTime = new Date(cb.scheduled_for).getTime();
    const fifteenMinInMs = 15 * 60 * 1000;
    return Date.now() >= scheduledTime + fifteenMinInMs;
  }

  function renderCallerStatus(cb: CallbackBoardItem) {
    const caller = cb.assigned_caller;
    if (!caller) {
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] font-medium bg-slate-100 text-slate-600 border border-slate-200">
          <User size={11} />
          Unassigned
        </span>
      );
    }

    // One self-explanatory pill: colored dot + caller name + plain-language state.
    // active → free · break → stepped away · else → logged out.
    const variants =
      caller.status === "active"
        ? { state: "Active", wrap: "bg-emerald-50 text-emerald-700 border-emerald-200/60", dot: "bg-emerald-500" }
        : caller.status === "break"
          ? { state: "On break", wrap: "bg-amber-50 text-amber-700 border-amber-200/60", dot: "bg-amber-500" }
          : { state: "Logged out", wrap: "bg-slate-100 text-slate-500 border-slate-200", dot: "bg-slate-400" };

    return (
      <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] font-medium border ${variants.wrap}`}>
        <span className={`w-1.5 h-1.5 rounded-full ${variants.dot}`} />
        <span className="font-semibold">{caller.name}</span>
        <span className="opacity-70">·</span>
        {variants.state}
      </span>
    );
  }

  const groups = groupCallbacks(callbacks);

  const sectionConfig = [
    { key: "overdue" as const, label: "Overdue", icon: AlertTriangle, iconColor: "text-rose-500", bgGradient: "from-rose-50/70 to-red-50/20", borderColor: "border-rose-200/60", badgeColor: "bg-rose-100 text-rose-700" },
    { key: "today" as const, label: "Today", icon: Clock, iconColor: "text-amber-500", bgGradient: "from-amber-50/70 to-orange-50/20", borderColor: "border-amber-200/60", badgeColor: "bg-amber-100 text-amber-700" },
    { key: "tomorrow" as const, label: "Tomorrow", icon: Calendar, iconColor: "text-indigo-500", bgGradient: "from-indigo-50/70 to-purple-50/20", borderColor: "border-indigo-200/60", badgeColor: "bg-indigo-100 text-indigo-700" },
    { key: "upcoming" as const, label: "Upcoming", icon: ChevronRight, iconColor: "text-slate-500", bgGradient: "from-slate-50/70 to-gray-50/20", borderColor: "border-slate-200/60", badgeColor: "bg-slate-100 text-slate-600" },
  ];

  return (
    <div className="max-w-4xl mx-auto px-4 pb-12">
      {/* Custom Keyframe Animations */}
      <style dangerouslySetInnerHTML={{__html: `
        @keyframes fadeIn {
          from { opacity: 0; }
          to { opacity: 1; }
        }
        @keyframes zoomIn {
          from { transform: scale(0.95); opacity: 0; }
          to { transform: scale(1); opacity: 1; }
        }
        .animate-fade-in {
          animation: fadeIn 0.2s ease-out forwards;
        }
        .animate-zoom-in {
          animation: zoomIn 0.25s cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
        }
      `}} />

      {/* Header */}
      <div className="mb-8">
        <h1 className="font-display text-3xl font-extrabold text-slate-900 tracking-tight flex items-center gap-3">
          <div className="p-2.5 bg-gradient-to-br from-indigo-500 to-purple-600 rounded-2xl shadow-md">
            <Calendar size={22} className="text-white" />
          </div>
          Scheduled Calls Board
        </h1>
        <p className="font-body text-sm text-slate-500 mt-1.5">
          Shared callback queue. When a callback&apos;s owner is logged out, on break, or on another call, an overdue call becomes claimable by any teammate.
        </p>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-24">
          <RefreshCw size={32} className="animate-spin text-indigo-500" />
        </div>
      ) : callbacks.length === 0 ? (
        <div className="text-center py-20 bg-white rounded-3xl border border-slate-200/60 shadow-sm">
          <div className="w-14 h-14 bg-slate-50 rounded-full flex items-center justify-center text-slate-400 border border-slate-100 mx-auto mb-4">
            <Inbox size={22} />
          </div>
          <h3 className="font-display text-lg font-bold text-slate-700">No scheduled callbacks</h3>
          <p className="font-body text-sm text-slate-400 mt-1 max-w-sm mx-auto">
            Schedule callbacks from the Dialer workspace to view them on the shared board.
          </p>
        </div>
      ) : (
        <div className="space-y-8">
          {sectionConfig.map(({ key, label, icon: Icon, iconColor, bgGradient, borderColor, badgeColor }) => {
            const items = groups[key];
            if (items.length === 0) return null;
            return (
              <div key={key} className={`bg-gradient-to-br ${bgGradient} border ${borderColor} rounded-3xl p-6 shadow-sm`}>
                <h2 className="font-display text-xs font-black uppercase tracking-widest flex items-center gap-2 mb-4 text-slate-800">
                  <Icon size={14} className={iconColor} />
                  {label}
                  <span className={`px-2 py-0.5 rounded-full font-label text-[10px] font-bold ${badgeColor}`}>
                    {items.length}
                  </span>
                </h2>
                <div className="space-y-3">
                  {items.map((cb) => {
                    const isTakeoverEligible = checkTakeoverEligible(cb);
                    const isAssignedToMe = cb.lead.assigned_to === callerId;
                    const actsAsCaller = !!callerId; // owner-with-caller-profile behaves like a telecaller here
                    const scheduledByMe = !!callerId && cb.scheduled_by?.id === callerId;
                    // "Claimed" = the callback is owned by a telecaller who isn't the scheduler
                    // (covers auto-/pre-103 callbacks with no recorded scheduler too).
                    const isClaimed =
                      !!cb.lead.assigned_to &&
                      cb.lead.assigned_to !== cb.scheduled_by?.id;

                    return (
                      <div
                        key={cb.id}
                        className={`flex flex-col md:flex-row md:items-center justify-between bg-white rounded-2xl p-5 shadow-sm border gap-4 transition-all ${
                          isTakeoverEligible
                            ? "border-indigo-200 hover:border-indigo-300 hover:shadow-indigo-50/50 bg-gradient-to-r from-white to-indigo-50/10"
                            : isAssignedToMe
                              ? "border-emerald-200 bg-gradient-to-r from-white to-emerald-50/10"
                              : "border-slate-100 hover:border-slate-200"
                        } hover:shadow-md hover:scale-[1.01]`}
                      >
                        {/* Left Info Column */}
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2 flex-wrap">
                            <p className="font-body text-sm font-bold text-slate-800 truncate">
                              {cb.lead.name ?? "Unnamed"}
                            </p>
                            <span className="font-label text-[10px] text-slate-500 font-semibold">
                              {formatPhone(cb.lead.phone ?? "")}
                            </span>
                            {cb.lead.segment && (
                              <span className={`px-1.5 py-0.5 rounded font-label text-[9px] font-black uppercase ${
                                cb.lead.segment === "A" ? "bg-emerald-50 text-emerald-700 border border-emerald-200/50" :
                                cb.lead.segment === "B" ? "bg-blue-50 text-blue-700 border border-blue-200/50" :
                                "bg-amber-50 text-amber-700 border border-amber-200/50"
                              }`}>
                                SEG {cb.lead.segment}
                              </span>
                            )}
                            {isTakeoverEligible && (
                              <span className="inline-flex items-center gap-0.5 px-2 py-0.5 rounded-full font-label text-[9px] font-bold uppercase tracking-wider bg-indigo-100 text-indigo-700 border border-indigo-200 shadow-sm animate-pulse">
                                <Zap size={8} className="fill-indigo-500 text-indigo-500" />
                                Claimable
                              </span>
                            )}
                          </div>

                          <div className="flex items-center gap-2 flex-wrap mt-2">
                            <span className="font-label text-[10px] text-slate-400 flex items-center gap-1">
                              <Clock size={10} />
                              {new Date(cb.scheduled_for).toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" })}
                            </span>
                            <span className={`font-label text-[10px] flex items-center gap-1 px-2 py-0.5 rounded-lg border ${
                              isAssignedToMe
                                ? "bg-emerald-50 text-emerald-700 border-emerald-200/60"
                                : isClaimed
                                  ? "bg-indigo-50 text-indigo-700 border-indigo-200/60"
                                  : "bg-slate-50 text-slate-500 border-slate-100"
                            }`}>
                              {isClaimed ? <Zap size={10} /> : <User size={10} />}
                              {isClaimed
                                ? (isAssignedToMe ? "Claimed by you" : `Claimed by ${cb.assigned_caller?.name ?? "telecaller"}`)
                                : scheduledByMe
                                  ? "Scheduled by you"
                                  : cb.scheduled_by?.name
                                    ? `Scheduled by ${cb.scheduled_by.name}`
                                    : "Auto-scheduled"}
                            </span>
                            {cb.message_preview && (
                              <span className="font-label text-[10px] text-slate-500 bg-slate-50 border border-slate-100 px-2 py-0.5 rounded-lg truncate max-w-[240px]">
                                {cb.message_preview}
                              </span>
                            )}
                          </div>
                        </div>

                        {/* Middle Status Column */}
                        <div className="flex items-center gap-2 shrink-0 md:justify-center">
                          {renderCallerStatus(cb)}
                        </div>

                        {/* Right Actions Column */}
                        <div className="flex items-center gap-2 shrink-0 justify-end">
                          {isAssignedToMe && (
                            <>
                              <button
                                onClick={() => handleCallLead(cb)}
                                className="flex items-center gap-1.5 px-4 py-2 bg-gradient-to-r from-emerald-500 to-teal-600 text-white rounded-xl font-label text-[10px] font-bold hover:from-emerald-600 hover:to-teal-700 transition-all shadow-sm hover:shadow-md hover:scale-[1.02] active:scale-[0.98]"
                              >
                                <Phone size={12} className="fill-white text-white" /> Call
                              </button>
                              <button
                                onClick={() => handleMarkDone(cb.id)}
                                disabled={markingDone === cb.id}
                                className="flex items-center gap-1.5 px-4 py-2 bg-slate-100 text-slate-600 rounded-xl font-label text-[10px] font-bold hover:bg-slate-200 transition-all disabled:opacity-50"
                              >
                                {markingDone === cb.id ? <RefreshCw size={12} className="animate-spin" /> : <Check size={12} />}
                                Done
                              </button>
                            </>
                          )}

                          {!isAssignedToMe && isTakeoverEligible && (
                            <button
                              onClick={() => handleOpenTakeoverHandoff(cb)}
                              className="flex items-center gap-1.5 px-4 py-2 bg-gradient-to-r from-indigo-500 to-purple-600 text-white rounded-xl font-label text-[10px] font-bold hover:from-indigo-600 hover:to-purple-700 transition-all shadow-md hover:shadow-lg hover:scale-[1.02] active:scale-[0.98]"
                            >
                              <Zap size={12} className="fill-white text-white" /> Claim
                            </button>
                          )}

                          {actsAsCaller && !isAssignedToMe && !isTakeoverEligible && (
                            <div className="flex items-center gap-1 px-3 py-1.5 bg-slate-50 text-slate-400 rounded-xl font-label text-[10px] border border-slate-100">
                              <Shield size={11} />
                              Locked
                            </div>
                          )}

                          {role === "owner" && !actsAsCaller && (
                            <button
                              onClick={() => handleMarkDone(cb.id)}
                              disabled={markingDone === cb.id}
                              className="flex items-center gap-1.5 px-4 py-2 bg-slate-100 text-slate-600 rounded-xl font-label text-[10px] font-bold hover:bg-slate-200 transition-all disabled:opacity-50"
                            >
                              {markingDone === cb.id ? <RefreshCw size={12} className="animate-spin" /> : <Check size={12} />}
                              Done (Admin)
                            </button>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Context Handoff Modal */}
      {handoffCallback && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-fade-in">
          <div className="bg-white rounded-3xl p-6 shadow-2xl w-full max-w-4xl border border-slate-100 max-h-[90vh] flex flex-col animate-zoom-in">
            {/* Modal Header */}
            <div className="flex items-center justify-between pb-4 border-b border-slate-100 shrink-0">
              <div>
                <div className="flex items-center gap-2">
                  <span className="p-1.5 bg-indigo-50 rounded-lg text-indigo-600">
                    <Zap size={18} />
                  </span>
                  <h2 className="font-display text-xl font-bold text-slate-800">
                    Claim Callback
                  </h2>
                </div>
                <p className="font-body text-xs text-slate-500 mt-1">
                  Claim this overdue callback. Once claimed, the lead is assigned to you.
                </p>
              </div>
              <button
                onClick={() => setHandoffCallback(null)}
                className="p-1.5 rounded-lg hover:bg-slate-50 text-slate-400 hover:text-slate-600 transition-colors"
              >
                <X size={18} />
              </button>
            </div>

            {/* Modal Body */}
            <div className="flex-1 overflow-y-auto py-6 grid grid-cols-1 lg:grid-cols-2 gap-6 min-h-[300px]">
              {/* Left Column: Lead Info & Notes History */}
              <div className="space-y-4 flex flex-col min-w-0">
                <div className="bg-slate-50 rounded-2xl p-4 border border-slate-100 shrink-0">
                  <h3 className="font-display text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">
                    Lead Details
                  </h3>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <p className="text-[10px] text-slate-400 font-medium uppercase">Name</p>
                      <p className="text-sm font-bold text-slate-800 truncate">{handoffCallback.lead.name || "Unnamed"}</p>
                    </div>
                    <div>
                      <p className="text-[10px] text-slate-400 font-medium uppercase">Phone</p>
                      <p className="text-sm font-bold text-slate-800">{formatPhone(handoffCallback.lead.phone ?? "")}</p>
                    </div>
                    <div>
                      <p className="text-[10px] text-slate-400 font-medium uppercase">Segment</p>
                      <span className={`inline-block px-2 py-0.5 rounded font-label text-[9px] font-black uppercase mt-0.5 ${
                        handoffCallback.lead.segment === "A" ? "bg-emerald-50 text-emerald-700 border border-emerald-200" :
                        handoffCallback.lead.segment === "B" ? "bg-blue-50 text-blue-700 border border-blue-200" :
                        "bg-amber-50 text-amber-700 border border-amber-200"
                      }`}>SEG {handoffCallback.lead.segment || "D"}</span>
                    </div>
                    <div>
                      <p className="text-[10px] text-slate-400 font-medium uppercase">Lead Score</p>
                      <div className="flex items-center gap-1 mt-0.5">
                        <Award size={12} className="text-indigo-500" />
                        <span className="text-xs font-bold text-slate-800">{handoffCallback.lead.score ?? 0}</span>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="flex-1 flex flex-col min-h-[200px]">
                  <h3 className="font-display text-xs font-bold text-slate-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                    <FileText size={12} />
                    Touch Notes History
                  </h3>
                  <div className="flex-1 overflow-y-auto border border-slate-100 rounded-2xl p-4 space-y-3 bg-white max-h-[300px]">
                    {loadingHandoff ? (
                      <div className="flex items-center justify-center h-full py-8">
                        <RefreshCw size={20} className="animate-spin text-slate-400" />
                      </div>
                    ) : notes.length === 0 ? (
                      <div className="flex flex-col items-center justify-center py-8 text-slate-400">
                        <MessageSquare size={24} className="stroke-[1.5] mb-1.5" />
                        <p className="text-xs font-medium">No touch notes found for this lead.</p>
                      </div>
                    ) : (
                      notes.map((note) => (
                        <div key={note.id} className="p-3 bg-slate-50 border border-slate-100 rounded-xl relative hover:border-slate-200 transition-colors">
                          <div className="flex items-center justify-between gap-2 mb-1">
                            <span className="text-[9px] text-slate-400 font-semibold">{timeAgo(note.created_at)}</span>
                            {note.is_pinned && (
                              <span className="text-[9px] font-bold text-indigo-600 bg-indigo-50 px-1 rounded">Pinned</span>
                            )}
                          </div>
                          <p className="text-xs text-slate-700 whitespace-pre-wrap">{note.content}</p>
                          {note.structured && Object.keys(note.structured).length > 0 && (
                            <div className="mt-2 pt-2 border-t border-slate-200/50 flex flex-wrap gap-2">
                              {Object.entries(note.structured).map(([k, v]) => v && (
                                <span key={k} className="text-[8px] bg-slate-200/60 text-slate-600 px-1.5 py-0.5 rounded capitalize font-medium">
                                  {k.replace("_", " ")}: {v}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </div>

              {/* Right Column: Previous Call Logs & AI Evaluation */}
              <div className="space-y-4 flex flex-col min-w-0">
                <div className="flex-1 flex flex-col min-h-[350px]">
                  <h3 className="font-display text-xs font-bold text-slate-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                    <Activity size={12} />
                    Recent Calls &amp; AI Summaries
                  </h3>
                  <div className="flex-1 overflow-y-auto border border-slate-100 rounded-2xl p-4 space-y-3 bg-white max-h-[420px]">
                    {loadingHandoff ? (
                      <div className="flex items-center justify-center h-full py-8">
                        <RefreshCw size={20} className="animate-spin text-slate-400" />
                      </div>
                    ) : callLogs.length === 0 ? (
                      <div className="flex flex-col items-center justify-center py-12 text-slate-400">
                        <Phone size={24} className="stroke-[1.5] mb-1.5" />
                        <p className="text-xs font-medium">No previous call records available.</p>
                      </div>
                    ) : (
                      callLogs.map((log) => (
                        <div key={log.id} className="p-3 bg-slate-50 border border-slate-100 rounded-xl space-y-2 hover:border-slate-200 transition-colors">
                          <div className="flex items-center justify-between">
                            <span className={`px-2 py-0.5 rounded text-[8px] font-bold uppercase ${
                              log.outcome === "converted" ? "bg-emerald-50 text-emerald-700" :
                              log.outcome === "callback" ? "bg-amber-50 text-amber-700" :
                              log.outcome === "not_interested" ? "bg-rose-50 text-rose-700" :
                              "bg-slate-200 text-slate-600"
                            }`}>
                              {log.outcome || "No Outcome"}
                            </span>
                            <span className="text-[9px] text-slate-400">{timeAgo(log.created_at)}</span>
                          </div>

                          {log.duration_seconds && (
                            <p className="text-[10px] text-slate-500 font-medium">
                              Duration: {Math.floor(log.duration_seconds / 60)}m {log.duration_seconds % 60}s
                            </p>
                          )}

                          {log.ai_summary && (
                            <div className="mt-2 bg-white rounded-lg p-2.5 border border-slate-200/50 space-y-1.5">
                              <div className="flex items-center gap-1 mb-1 pb-1 border-b border-slate-100">
                                <span className="text-[9px] font-bold text-slate-600 flex items-center gap-1">
                                  <Sparkles size={10} className="text-indigo-500" />
                                  AI Evaluation
                                </span>
                              </div>
                              {(log.ai_summary.course || log.ai_summary.product) && (
                                <p className="text-[10px] text-slate-600"><span className="font-semibold text-slate-700">Course Interest:</span> {log.ai_summary.course || log.ai_summary.product}</p>
                              )}
                              {log.ai_summary.brief && (
                                <p className="text-[10px] text-slate-600"><span className="font-semibold text-slate-700">Brief:</span> {log.ai_summary.brief}</p>
                              )}
                              {log.ai_summary.budget && (
                                <p className="text-[10px] text-slate-600"><span className="font-semibold text-slate-700">Budget:</span> {log.ai_summary.budget}</p>
                              )}
                              {log.ai_summary.timeline && (
                                <p className="text-[10px] text-slate-600"><span className="font-semibold text-slate-700">Timeline:</span> {log.ai_summary.timeline}</p>
                              )}
                              {log.ai_summary.sentiment && (
                                <p className="text-[10px] text-slate-600"><span className="font-semibold text-slate-700">Sentiment:</span> {log.ai_summary.sentiment}</p>
                              )}
                              {log.ai_summary.next_action && (
                                <p className="text-[10px] text-slate-600"><span className="font-semibold text-slate-700">Next Action:</span> {log.ai_summary.next_action}</p>
                              )}
                            </div>
                          )}

                          {log.transcript && (
                            <div className="bg-slate-100/50 rounded p-2 mt-1.5">
                              <p className="text-[9px] font-bold text-slate-500 mb-0.5">Transcript Snippet</p>
                              <p className="text-[10px] text-slate-600 line-clamp-2 italic">&ldquo;{log.transcript}&rdquo;</p>
                            </div>
                          )}
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </div>
            </div>

            {/* Modal Footer */}
            <div className="flex items-center justify-end gap-3 pt-4 border-t border-slate-100 shrink-0">
              <button
                onClick={() => setHandoffCallback(null)}
                className="px-4 py-2 bg-slate-100 text-slate-600 hover:bg-slate-200 rounded-xl font-label text-[11px] font-bold transition-all"
              >
                Cancel
              </button>
              <button
                onClick={() => handleConfirmTakeover(handoffCallback)}
                disabled={takeoverLoading}
                className="flex items-center gap-1.5 px-5 py-2 bg-gradient-to-r from-indigo-500 to-purple-600 text-white hover:from-indigo-600 hover:to-purple-700 rounded-xl font-label text-[11px] font-bold transition-all shadow-md hover:shadow-lg disabled:opacity-50"
              >
                {takeoverLoading ? (
                  <RefreshCw size={12} className="animate-spin" />
                ) : (
                  <PhoneCall size={12} className="fill-white text-white" />
                )}
                Claim
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
