"use client";
import { AlertCircle, Check, Copy, Phone, RefreshCw, Send, Star, X } from "lucide-react";
import { QRCodeSVG } from "qrcode.react";
import { toast } from "sonner";
import { formatPhone } from "@/lib/utils";
import { QUICK_NOTE_TAGS } from "./LeadDetailPanel";
import type { CallingCockpit } from "../lib/useCallingCockpit";

const TELECMI_OUTCOMES: { value: string; label: string; danger?: boolean }[] = [
  { value: "converted", label: "Converted" },
  { value: "in_progress", label: "In Progress" },
  { value: "interested", label: "Interested" },
  { value: "not_interested", label: "Not Interested (Nurture)" },
  { value: "no_answer", label: "No Answer" },
  { value: "do_not_call", label: "Do Not Call", danger: true },
  { value: "do_not_contact", label: "Do Not Contact at All", danger: true },
];

const SIM_MANUAL_STATUSES: { value: string; label: string; danger?: boolean }[] = [
  { value: "connected", label: "Connected" },
  { value: "not_picked", label: "Not picked" },
  { value: "busy", label: "Busy" },
  { value: "wrong_number", label: "Wrong number", danger: true },
  { value: "interested", label: "Interested" },
  { value: "not_interested", label: "Not interested" },
  { value: "callback", label: "Callback" },
];

/**
 * Shared overlays for the calling cockpit: accidental-dial guard, the mandatory
 * wrap-up form, and the blocking pending-wrap-ups list. All state comes from
 * useCallingCockpit; the blocking list only renders when `blockingWrapups` is on.
 */
export default function CockpitModals({ cockpit }: { cockpit: CallingCockpit }) {
  const {
    dialCountdown,
    dialTarget,
    cancelDial,
    showWrapupModal,
    activeCallCtx,
    wrapupOutcome,
    setWrapupOutcome,
    wrapupNotes,
    setWrapupNotes,
    wrapupTags,
    toggleWrapupTag,
    wrapupQualityRating,
    setWrapupQualityRating,
    wrapupSaving,
    handleWrapupSubmit,
    pendingWrapups,
    openWrapupFromLog,
    blockingWrapups,
    simHandoffLead,
    setSimHandoffLead,
    simHandoffSending,
    sendSimHandoffToMobile,
    activeCallProvider,
    wrapupStartedAt,
    setWrapupStartedAt,
    wrapupEndedAt,
    setWrapupEndedAt,
  } = cockpit;

  const simDurationSeconds = (() => {
    if (!wrapupStartedAt || !wrapupEndedAt) return null;
    const seconds = Math.round((new Date(wrapupEndedAt).getTime() - new Date(wrapupStartedAt).getTime()) / 1000);
    return Number.isFinite(seconds) ? Math.max(0, seconds) : null;
  })();
  const simHandoffUrl = simHandoffLead && typeof window !== "undefined"
    ? `${window.location.origin}/dashboard/telecalling?lead_id=${simHandoffLead.id}`
    : "";

  const copySimNumber = async () => {
    if (!simHandoffLead?.phone) return;
    try {
      await navigator.clipboard.writeText(simHandoffLead.phone);
      toast.success("Phone number copied");
    } catch {
      toast.error("Could not copy phone number");
    }
  };

  return (
    <>
      {/* Accidental-dial guard countdown */}
      {dialCountdown !== null && dialTarget && (
        <div className="fixed inset-0 bg-[#1c1917]/70 backdrop-blur-sm flex items-center justify-center z-50">
          <div className="bg-white rounded-3xl p-8 max-w-sm w-full mx-4 shadow-2xl border border-[#e8e3db] text-center animate-in fade-in zoom-in-95">
            <div className="w-16 h-16 bg-[#f5f3ff] text-[#5b21b6] rounded-full flex items-center justify-center mx-auto mb-4 animate-bounce">
              <Phone size={24} />
            </div>
            <h3 className="font-display text-lg font-bold text-[#292524]">Calling in {dialCountdown}s...</h3>
            <p className="font-body text-sm text-[#78716c] mt-1.5">
              Target: {"lead" in dialTarget ? dialTarget.lead?.name || dialTarget.lead?.phone : dialTarget.phone}
            </p>
            <button
              onClick={cancelDial}
              className="mt-6 w-full py-3 bg-red-50 hover:bg-red-100 text-red-600 font-label text-sm font-bold rounded-2xl transition-all border border-red-200"
            >
              Cancel Dial
            </button>
          </div>
        </div>
      )}

      {/* SIM Basic desktop handoff */}
      {simHandoffLead && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#1c1917]/75 p-4 backdrop-blur-sm">
          <div className="w-full max-w-md overflow-hidden rounded-3xl border border-[#e8e3db] bg-white shadow-2xl animate-in fade-in zoom-in-95">
            <div className="flex items-start justify-between gap-4 border-b border-[#f0ece4] px-6 py-5">
              <div>
                <span className="rounded-full bg-primary-light px-3 py-1 font-label text-[10px] font-black uppercase tracking-wider text-primary">
                  SIM Basic
                </span>
                <h3 className="mt-3 font-display text-xl font-extrabold text-[#1c1917]">Open this lead on mobile</h3>
                <p className="mt-1 font-body text-sm leading-relaxed text-[#78716c]">
                  This tenant uses SIM calling. Open this lead on your phone to call using your SIM.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setSimHandoffLead(null)}
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-[#78716c] hover:bg-[#f0ece4] hover:text-[#292524]"
                aria-label="Close"
              >
                <X size={18} />
              </button>
            </div>

            <div className="space-y-5 px-6 py-5">
              <div className="rounded-2xl border border-[#e8e3db] bg-[#faf8f5] p-4">
                <p className="font-label text-[10px] font-black uppercase tracking-wider text-[#a8a29e]">Lead</p>
                <p className="mt-1 font-display text-base font-bold text-[#1c1917]">{simHandoffLead.name || "Unnamed Lead"}</p>
                <div className="mt-3 flex items-center justify-between gap-3 rounded-xl bg-white px-3 py-2">
                  <span className="font-mono text-sm font-bold text-[#292524]">{formatPhone(simHandoffLead.phone)}</span>
                  <button
                    type="button"
                    onClick={copySimNumber}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-[#e8e3db] px-2.5 py-1.5 font-label text-[11px] font-bold text-[#57534e] hover:border-primary-muted hover:text-primary"
                  >
                    <Copy size={12} />
                    Copy
                  </button>
                </div>
              </div>

              <div className="flex items-center justify-center rounded-3xl border border-primary-muted bg-primary-light/40 p-5">
                {simHandoffUrl && (
                  <QRCodeSVG
                    value={simHandoffUrl}
                    size={168}
                    bgColor="#ffffff"
                    fgColor="#1c1917"
                    level="M"
                    includeMargin
                    className="rounded-2xl bg-white p-2 shadow-sm"
                  />
                )}
              </div>

              <button
                type="button"
                onClick={sendSimHandoffToMobile}
                disabled={simHandoffSending}
                className="flex w-full items-center justify-center gap-2 rounded-2xl bg-primary px-4 py-3 font-label text-sm font-black text-white shadow-md transition-all hover:bg-primary-dark disabled:opacity-50"
              >
                {simHandoffSending ? <RefreshCw size={15} className="animate-spin" /> : <Send size={15} />}
                Send to my mobile
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Mandatory wrap-up form */}
      {showWrapupModal && activeCallCtx && (
        <div className="fixed inset-0 bg-[#1c1917]/80 backdrop-blur-sm flex items-end sm:items-center justify-center z-[60] p-0 sm:p-4">
          <div className="bg-white sm:rounded-3xl rounded-t-3xl p-5 sm:p-7 max-w-lg w-full shadow-2xl border border-[#e8e3db] animate-in fade-in slide-in-from-bottom-4 sm:zoom-in-95 max-h-[85vh] sm:max-h-[90vh] overflow-y-auto pb-[calc(1.25rem+env(safe-area-inset-bottom,0px))] sm:pb-7">
            <div className="text-center mb-6">
              <span className="px-3 py-1 bg-amber-50 text-amber-700 border border-amber-200 rounded-full font-label text-[10px] font-black uppercase tracking-wider">
                {activeCallProvider === "sim_basic" ? "SIM Call Feedback" : "Call Completed"}
              </span>
              <h3 className="font-display text-xl font-bold text-[#1c1917] mt-2">Mandatory Call Wrap-up</h3>
              <p className="font-body text-xs text-[#a8a29e] mt-1">
                Please log feedback for the call with{" "}
                <span className="font-semibold text-[#44403c]">{activeCallCtx.name || activeCallCtx.phone}</span>.
              </p>
            </div>

            <div className="space-y-4">
              {activeCallProvider === "sim_basic" && (
                <div className="rounded-2xl border border-primary-muted bg-primary-light/40 p-4">
                  <div className="mb-3 flex items-center justify-between gap-3">
                    <div>
                      <p className="font-label text-[10px] font-black uppercase tracking-wider text-primary">
                        Manual Call Timing
                      </p>
                      <p className="mt-0.5 font-body text-[11px] text-[#78716c]">
                        Aira cannot read SIM call duration, so confirm the time before saving.
                      </p>
                    </div>
                    <span className="rounded-xl bg-white px-3 py-1.5 font-mono text-xs font-bold text-[#292524]">
                      {simDurationSeconds !== null
                        ? `${Math.floor(simDurationSeconds / 60)}m ${simDurationSeconds % 60}s`
                        : "0m"}
                    </span>
                  </div>
                  <div className="grid gap-2 sm:grid-cols-2">
                    <label className="block">
                      <span className="mb-1 block font-label text-[9px] font-black uppercase tracking-wider text-[#a8a29e]">Started</span>
                      <input
                        type="datetime-local"
                        value={wrapupStartedAt}
                        onChange={(e) => setWrapupStartedAt(e.target.value)}
                        className="w-full rounded-xl border border-[#e8e3db] bg-white px-3 py-2 font-body text-xs focus:outline-none focus:ring-2 focus:ring-primary"
                      />
                    </label>
                    <label className="block">
                      <span className="mb-1 block font-label text-[9px] font-black uppercase tracking-wider text-[#a8a29e]">Ended</span>
                      <input
                        type="datetime-local"
                        value={wrapupEndedAt}
                        onChange={(e) => setWrapupEndedAt(e.target.value)}
                        className="w-full rounded-xl border border-[#e8e3db] bg-white px-3 py-2 font-body text-xs focus:outline-none focus:ring-2 focus:ring-primary"
                      />
                    </label>
                  </div>
                </div>
              )}

              <div>
                <label className="font-label text-[10px] text-[#a8a29e] uppercase tracking-wider font-extrabold block mb-2">
                  Call Outcome / Disposition *
                </label>
                <div className="grid grid-cols-2 gap-2">
                  {(activeCallProvider === "sim_basic" ? SIM_MANUAL_STATUSES : TELECMI_OUTCOMES).map((o) => {
                    const selected = wrapupOutcome === o.value;
                    const base = "px-3 py-2.5 rounded-xl font-label text-xs font-bold border transition-all text-center";
                    const cls = selected
                      ? o.danger
                        ? "bg-red-600 border-red-600 text-white"
                        : "bg-primary border-primary text-white"
                      : o.danger
                        ? "bg-[#faf8f5] hover:bg-red-50 text-red-700 border-red-200"
                        : "bg-[#faf8f5] hover:bg-[#f0ece4] text-[#44403c] border-[#e8e3db]";
                    return (
                      <button key={o.value} type="button" onClick={() => setWrapupOutcome(o.value)} className={`${base} ${cls}`}>
                        {o.label}
                      </button>
                    );
                  })}
                </div>
              </div>

              <div>
                <label className="font-label text-[10px] text-[#a8a29e] uppercase tracking-wider font-extrabold block mb-1.5">
                  {activeCallProvider === "sim_basic" ? "Call Summary / Notes" : "Interaction Note / Comments"}
                </label>
                <textarea
                  value={wrapupNotes}
                  onChange={(e) => setWrapupNotes(e.target.value)}
                  placeholder={activeCallProvider === "sim_basic" ? "Brief the call in 1-2 lines, e.g. asked price, wants callback tomorrow..." : "Summarize customer feedback and key discussion points..."}
                  rows={4}
                  className="w-full px-4 py-3 rounded-2xl bg-[#faf8f5] border border-[#e8e3db] font-body text-xs focus:outline-none focus:ring-2 focus:ring-primary resize-none shadow-inner"
                />
              </div>

              <div>
                <label className="font-label text-[10px] text-[#a8a29e] uppercase tracking-wider font-extrabold block mb-1.5">
                  Tags
                </label>
                <div className="flex flex-wrap gap-1.5">
                  {QUICK_NOTE_TAGS.map((tag) => {
                    const selected = wrapupTags.includes(tag);
                    return (
                      <button
                        key={tag}
                        type="button"
                        onClick={() => toggleWrapupTag(tag)}
                        className={`px-2.5 py-1 rounded-full text-[10px] font-bold border transition-all ${
                          selected
                            ? "bg-primary border-primary text-white"
                            : "bg-[#faf8f5] border-[#e8e3db] text-[#57534e] hover:border-primary-muted hover:text-primary"
                        }`}
                      >
                        {tag}
                      </button>
                    );
                  })}
                </div>
              </div>

              <div>
                <label className="font-label text-[10px] text-[#a8a29e] uppercase tracking-wider font-extrabold block mb-1.5">
                  How did this call go?
                </label>
                <div className="flex gap-1">
                  {[1, 2, 3, 4, 5].map((n) => (
                    <button
                      key={n}
                      type="button"
                      onClick={() => setWrapupQualityRating(wrapupQualityRating === n ? 0 : n)}
                      className="p-1 transition-transform hover:scale-110"
                    >
                      <Star size={20} className={n <= wrapupQualityRating ? "fill-amber-400 text-amber-400" : "text-[#d6cfc9]"} />
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <div className="mt-6 flex gap-3">
              <button
                type="button"
                onClick={handleWrapupSubmit}
                disabled={wrapupSaving || !wrapupOutcome}
                className="flex-1 py-3 bg-primary hover:bg-primary-dark text-white rounded-2xl font-label text-xs font-black shadow-md hover:scale-[1.01] active:scale-[0.99] disabled:opacity-50 transition-all flex items-center justify-center gap-1.5"
              >
                {wrapupSaving ? <RefreshCw size={14} className="animate-spin" /> : <Check size={14} />}
                <span>Complete Wrap-up</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Blocking pending-wrap-ups list (telecaller discipline gate only) */}
      {blockingWrapups && pendingWrapups.length > 0 && !showWrapupModal && (
        <div className="fixed inset-0 bg-[#1c1917]/85 backdrop-blur-md flex items-center justify-center z-50 p-4 animate-in fade-in">
          <div className="bg-white rounded-3xl p-8 max-w-2xl w-full max-h-[80vh] shadow-2xl flex flex-col border border-[#e8e3db]">
            <div className="text-center mb-6 shrink-0">
              <div className="w-12 h-12 bg-amber-50 border border-amber-200 text-amber-600 rounded-full flex items-center justify-center mx-auto mb-3">
                <AlertCircle size={24} />
              </div>
              <h2 className="font-display text-xl font-extrabold text-[#1c1917]">Action Required: Pending Call Wrap-ups</h2>
              <p className="font-body text-xs text-[#a8a29e] mt-1.5">
                You have {pendingWrapups.length} completed call(s) that require outcome feedback. Please submit feedback to unlock the dashboard.
              </p>
            </div>

            <div className="flex-1 overflow-y-auto space-y-3 mb-2 pr-1">
              {pendingWrapups.map((log) => (
                <div key={log.id} className="border border-[#f0ece4] rounded-2xl p-4 bg-[#faf8f5]/50 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                  <div className="min-w-0">
                    <p className="font-body text-sm font-bold text-[#292524] truncate">
                      {log.leads?.name || "Unnamed Lead"} ({formatPhone(log.leads?.phone || "")})
                    </p>
                    <p className="font-label text-xs text-[#78716c] mt-1">
                      Duration: {log.duration_seconds || 0}s · Completed {new Date(log.created_at).toLocaleString()}
                    </p>
                  </div>
                  <button
                    onClick={() => openWrapupFromLog(log)}
                    className="px-4 py-2 bg-primary hover:bg-primary-dark text-white rounded-xl font-label text-xs font-bold transition-all shadow-sm shrink-0"
                  >
                    Wrap Up
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
