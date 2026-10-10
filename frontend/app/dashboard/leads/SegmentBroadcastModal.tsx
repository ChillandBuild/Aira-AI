"use client";
import { useEffect, useState } from "react";
import { X, Send, Save, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { api, BroadcastResult, SegmentTemplate, BroadcastHistoryItem } from "@/lib/api";

const SEGMENT_LABELS: Record<string, string> = {
  A: "Hot",
  B: "Warm",
  C: "Cold",
  D: "Not Interested",
};

const SOURCE_LABELS: Record<string, string> = {
  INBOUND: "inbound leads",
  ORGANIC: "organic leads",
  META_ADS: "Meta Ads leads",
  BROADCAST: "broadcast leads",
};

interface SegmentBroadcastModalProps {
  segment: string;
  sourceFilter: string;
  selectedCampaignId?: string;
  selectedBroadcastId?: string;
  selectedCampaignName?: string;
  broadcastHistory?: BroadcastHistoryItem[];
  templates: Record<string, SegmentTemplate>;
  canManageLeads: boolean;
  onClose: () => void;
  onAfterBroadcast?: () => void;
}

export function SegmentBroadcastModal({
  segment,
  sourceFilter,
  selectedCampaignId,
  selectedBroadcastId,
  selectedCampaignName,
  broadcastHistory,
  templates,
  canManageLeads,
  onClose,
  onAfterBroadcast,
}: SegmentBroadcastModalProps) {
  const [draft, setDraft] = useState("");
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  const [savingTpl, setSavingTpl] = useState(false);
  const [broadcasting, setBroadcasting] = useState(false);
  const [lastResult, setLastResult] = useState<BroadcastResult | null>(null);

  // Initialize draft from template and track changes
  useEffect(() => {
    const template = templates[segment]?.message ?? "";
    setDraft(template);
    setHasUnsavedChanges(false);
  }, [segment, templates]);

  async function saveTemplate() {
    if (!canManageLeads) return;
    setSavingTpl(true);
    try {
      await api.segments.saveTemplate(segment, draft);
      toast.success("Template saved");
    } catch {
      toast.error("Failed to save template");
    } finally {
      setSavingTpl(false);
    }
  }

  async function broadcast() {
    if (!canManageLeads) return;
    if (!draft.trim()) return;

    const targetLabel = sourceFilter !== "ALL" ? "filtered" : `${SEGMENT_LABELS[segment]}`;
    if (!confirm(`Send this message to all ${targetLabel} leads?`)) return;

    setBroadcasting(true);
    setLastResult(null);
    try {
      if (sourceFilter !== "ALL") {
        const payload: Parameters<typeof api.leads.broadcast>[0] = {
          message: draft,
          segment,
          source_filter: sourceFilter.toLowerCase(),
        };
        if (sourceFilter === "META_ADS" && selectedCampaignId) {
          payload.ad_campaign_id = selectedCampaignId;
        } else if (sourceFilter === "BROADCAST" && selectedBroadcastId) {
          payload.broadcast_id = selectedBroadcastId;
        }
        const result = await api.leads.broadcast(payload);
        setLastResult(result);
        toast.success("Broadcast sent");
      } else {
        if (draft !== templates[segment]?.message) await saveTemplate();
        const result = await api.segments.broadcast(segment);
        setLastResult(result);
        toast.success("Broadcast sent");
      }
      onAfterBroadcast?.();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Broadcast failed");
    } finally {
      setBroadcasting(false);
    }
  }

  const getSubtitle = () => {
    const label = SEGMENT_LABELS[segment];
    if (sourceFilter === "ALL") {
      return `Goes to every ${label} lead (other filters don't apply)`;
    }
    let desc = `Goes to ${label} leads from ${SOURCE_LABELS[sourceFilter] || sourceFilter}`;
    if (sourceFilter === "META_ADS" && selectedCampaignName) {
      desc += ` · ${selectedCampaignName}`;
    } else if (sourceFilter === "BROADCAST" && selectedBroadcastId && broadcastHistory) {
      const broadcast = broadcastHistory.find((b) => b.broadcast_id === selectedBroadcastId);
      if (broadcast) {
        desc += ` · ${broadcast.template_name}`;
      }
    }
    return desc;
  };

  return (
    <div className="fixed inset-0 z-dialog flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div
        className="bg-white rounded-2xl shadow-lg w-full max-w-2xl p-6 max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-5">
          <div>
            <h3 className="font-display text-lg font-bold text-[#0A1528]">
              Message {SEGMENT_LABELS[segment]} leads
            </h3>
            <p className="font-body text-xs text-[#64748b] mt-1">{getSubtitle()}</p>
          </div>
          <button onClick={onClose} className="text-[#64748b] hover:text-[#0A1528]">
            <X size={20} />
          </button>
        </div>

        <div className="space-y-4">
          <textarea
            value={draft}
            onChange={(e) => {
              setDraft(e.target.value);
              setHasUnsavedChanges(true);
            }}
            rows={5}
            placeholder={sourceFilter !== "ALL" ? "Message to broadcast to filtered leads…" : `Message to broadcast to ${SEGMENT_LABELS[segment]} leads…`}
            className="w-full px-4 py-3 bg-[#f8fafc] rounded-xl font-body text-sm text-[#0A1528] border border-[#e2e8f0] focus:outline-none focus:ring-2 focus:ring-primary resize-none"
          />

          {lastResult && (
            <div className="p-3 rounded-xl bg-[#f0fdf4] border border-[#dcfce7]">
              <p className="font-label text-xs text-[#166534]">
                Sent {lastResult.sent} · Failed {lastResult.failed} · Outside 24h window {lastResult.skipped_window}
              </p>
            </div>
          )}

          {draft.trim() && (
            <div className="flex flex-wrap gap-2">
              {sourceFilter === "ALL" && (
                <button
                  onClick={saveTemplate}
                  disabled={savingTpl || !hasUnsavedChanges || !canManageLeads}
                  className="flex items-center gap-2 px-4 py-2 bg-[#f1f5f9] text-[#0A1528] rounded-xl font-label text-xs font-semibold hover:bg-[#e2e8f0] transition-colors disabled:opacity-50"
                >
                  <Save size={14} />
                  {savingTpl ? "Saving…" : "Save"}
                </button>
              )}
              <button
                onClick={broadcast}
                disabled={broadcasting || !draft.trim() || !canManageLeads}
                className="flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-xl font-label text-xs font-semibold hover:bg-primary/90 transition-colors disabled:opacity-50"
              >
                {broadcasting ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
                {broadcasting ? "Sending…" : sourceFilter !== "ALL" ? "Send to Filtered Leads" : `Send to ${SEGMENT_LABELS[segment]}`}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
