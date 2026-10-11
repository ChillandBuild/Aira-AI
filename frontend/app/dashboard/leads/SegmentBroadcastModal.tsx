"use client";
import { useEffect, useState } from "react";
import { X, Send, Save, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { api, BroadcastResult, SegmentTemplate, type BroadcastFilters, type BroadcastPreview } from "@/lib/api";

const SEGMENT_LABELS: Record<string, string> = {
  A: "Hot",
  B: "Warm",
  C: "Cold",
  D: "Not interested",
};

interface SegmentBroadcastModalProps {
  segment: string;
  /** The table's current filters; the broadcast goes to exactly these leads. */
  filters: BroadcastFilters;
  /** Human labels for the active filters, e.g. "Assigned: Karthik". */
  filterLabels: string[];
  templates: Record<string, SegmentTemplate>;
  canManageLeads: boolean;
  onClose: () => void;
  onAfterBroadcast?: () => void;
}

export function SegmentBroadcastModal({
  segment,
  filters,
  filterLabels,
  templates,
  canManageLeads,
  onClose,
  onAfterBroadcast,
}: SegmentBroadcastModalProps) {
  const label = SEGMENT_LABELS[segment] ?? segment;
  const [draft, setDraft] = useState("");
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  const [savingTpl, setSavingTpl] = useState(false);
  const [broadcasting, setBroadcasting] = useState(false);
  const [lastResult, setLastResult] = useState<BroadcastResult | null>(null);
  const [preview, setPreview] = useState<BroadcastPreview | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);

  // Start from the saved message for this segment.
  useEffect(() => {
    setDraft(templates[segment]?.message ?? "");
    setHasUnsavedChanges(false);
  }, [segment, templates]);

  const filtersKey = JSON.stringify({ ...filters, segment });
  useEffect(() => {
    let stopped = false;
    setPreview(null);
    setPreviewError(null);
    api.leads
      .broadcastPreview(JSON.parse(filtersKey) as BroadcastFilters)
      .then((p) => !stopped && setPreview(p))
      .catch((err) => !stopped && setPreviewError(err instanceof Error ? err.message : "Couldn't count the leads"));
    return () => {
      stopped = true;
    };
  }, [filtersKey]);

  async function saveTemplate() {
    if (!canManageLeads) return;
    setSavingTpl(true);
    try {
      await api.segments.saveTemplate(segment, draft);
      setHasUnsavedChanges(false);
      toast.success("Message saved");
    } catch {
      toast.error("Failed to save message");
    } finally {
      setSavingTpl(false);
    }
  }

  async function broadcast() {
    if (!canManageLeads || !draft.trim() || !preview?.reachable) return;
    if (!confirm(`Send this message to ${preview.reachable} ${label} ${preview.reachable === 1 ? "lead" : "leads"}?`)) return;
    setBroadcasting(true);
    setLastResult(null);
    try {
      const result = await api.leads.broadcast({ ...filters, segment, message: draft });
      setLastResult(result);
      toast.success(`Sent ${result.sent}${result.failed ? ` · ${result.failed} failed` : ""}`);
      onAfterBroadcast?.();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Broadcast failed");
    } finally {
      setBroadcasting(false);
    }
  }

  const reachable = preview?.reachable ?? 0;

  return (
    <div className="fixed inset-0 z-dialog flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div
        className="bg-white rounded-2xl shadow-lg w-full max-w-2xl p-6 max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4 mb-4">
          <div className="min-w-0">
            <h3 className="font-display text-lg font-bold text-[#0A1528]">Message {label} leads</h3>
            <p className="mt-1 font-body text-xs text-[#64748b]">
              {preview ? (
                <>
                  Goes to <b className="text-[#0A1528]">{preview.matching}</b> {label}{" "}
                  {preview.matching === 1 ? "lead" : "leads"}
                  {filterLabels.length > 0 ? " matching your filters" : ""}
                </>
              ) : previewError ? (
                previewError
              ) : (
                <span className="inline-flex items-center gap-1.5">
                  <Loader2 size={11} className="animate-spin" /> Counting leads…
                </span>
              )}
            </p>
            {filterLabels.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {filterLabels.map((f) => (
                  <span key={f} className="rounded-full border border-[#e2e8f0] bg-[#f8fafc] px-2 py-0.5 font-label text-[10px] font-semibold text-[#334155]">
                    {f}
                  </span>
                ))}
              </div>
            )}
          </div>
          <button onClick={onClose} aria-label="Close" className="shrink-0 text-[#64748b] hover:text-[#0A1528]">
            <X size={20} />
          </button>
        </div>

        {preview && preview.matching > 0 && (
          <div className="mb-4 grid grid-cols-1 gap-2 sm:grid-cols-3">
            <div className="rounded-xl border border-primary/20 bg-primary-light px-3 py-2">
              <p className="font-display text-lg font-bold text-primary">{preview.reachable}</p>
              <p className="font-label text-[11px] text-[#334155]">will get it now</p>
            </div>
            <div className="rounded-xl border border-[#e2e8f0] bg-[#f8fafc] px-3 py-2">
              <p className="font-display text-lg font-bold text-[#0A1528]">{preview.outside_window}</p>
              <p className="font-label text-[11px] text-[#64748b]">skipped, last message over 24h ago</p>
            </div>
            <div className="rounded-xl border border-[#e2e8f0] bg-[#f8fafc] px-3 py-2">
              <p className="font-display text-lg font-bold text-[#0A1528]">{preview.no_opt_in}</p>
              <p className="font-label text-[11px] text-[#64748b]">skipped, no opt-in on record</p>
            </div>
          </div>
        )}

        {preview && preview.matching > 0 && preview.reachable === 0 && (
          <p className="mb-4 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2.5 font-label text-xs text-amber-800">
            None of these leads can get a free message right now. Select them in the table and use{" "}
            <b>Send message → Template</b> instead.
          </p>
        )}

        <div className="space-y-4">
          <textarea
            value={draft}
            onChange={(e) => {
              setDraft(e.target.value);
              setHasUnsavedChanges(true);
            }}
            rows={5}
            placeholder={`Message to ${label} leads…`}
            className="w-full px-4 py-3 bg-[#f8fafc] rounded-xl font-body text-sm text-[#0A1528] border border-[#e2e8f0] focus:outline-none focus:ring-2 focus:ring-primary resize-none"
          />

          {lastResult && (
            <div className="p-3 rounded-xl bg-[#f0fdf4] border border-[#dcfce7]">
              <p className="font-label text-xs text-[#166534]">
                Sent {lastResult.sent} · Failed {lastResult.failed} · Outside 24h window {lastResult.skipped_window}
              </p>
            </div>
          )}

          <div className="flex flex-wrap gap-2">
            <button
              onClick={saveTemplate}
              disabled={savingTpl || !hasUnsavedChanges || !draft.trim() || !canManageLeads}
              title={`Keep this as the saved message for ${label} leads`}
              className="flex items-center gap-2 px-4 py-2 bg-[#f1f5f9] text-[#0A1528] rounded-xl font-label text-xs font-semibold hover:bg-[#e2e8f0] transition-colors disabled:opacity-50"
            >
              <Save size={14} />
              {savingTpl ? "Saving…" : "Save"}
            </button>
            <button
              onClick={broadcast}
              disabled={broadcasting || !draft.trim() || !canManageLeads || reachable === 0}
              className="flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-xl font-label text-xs font-semibold hover:bg-primary/90 transition-colors disabled:opacity-50"
            >
              {broadcasting ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
              {broadcasting ? "Sending…" : `Send to ${reachable} ${reachable === 1 ? "lead" : "leads"}`}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
