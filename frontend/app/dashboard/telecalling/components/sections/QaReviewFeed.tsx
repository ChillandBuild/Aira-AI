"use client";

import { useEffect, useState, useCallback } from "react";
import { Award, Eye, Loader2 } from "lucide-react";
import { api, type CallLog, type CallEvaluation } from "@/lib/api";
import { formatPhone, timeAgo } from "@/lib/utils";

interface QaReviewFeedProps {
  onViewLead: (leadId: string) => void;
}

const SCORE_CRITERIA: { key: keyof CallEvaluation; reasonKey: keyof CallEvaluation; label: string }[] = [
  { key: "greeting_quality", reasonKey: "greeting_quality_reason", label: "Greeting" },
  { key: "communication_clarity", reasonKey: "communication_clarity_reason", label: "Clarity" },
  { key: "product_knowledge", reasonKey: "product_knowledge_reason", label: "Product Knowledge" },
  { key: "requirement_understanding", reasonKey: "requirement_understanding_reason", label: "Understanding" },
  { key: "conversation_engagement", reasonKey: "conversation_engagement_reason", label: "Engagement" },
  { key: "objection_handling", reasonKey: "objection_handling_reason", label: "Objection Handling" },
  { key: "professionalism", reasonKey: "professionalism_reason", label: "Professionalism" },
];

const QUALITY_LABEL_STYLES: Record<string, string> = {
  Excellent: "bg-emerald-50 text-emerald-700 border-emerald-200",
  Good: "bg-blue-50 text-blue-700 border-blue-200",
  Average: "bg-amber-50 text-amber-700 border-amber-200",
  Bad: "bg-rose-50 text-rose-700 border-rose-200",
};

export default function QaReviewFeed({ onViewLead }: QaReviewFeedProps) {
  const [qaQueue, setQaQueue] = useState<CallLog[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.analytics.qaQueue(10);
      setQaQueue(Array.isArray(res.data) ? res.data : []);
    } catch (err) {
      console.error("Failed to load QA queue:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="bg-surface rounded-card p-6 shadow-card ring-1 ring-[#c4c7c7]/15">
      <h2 className="font-display text-base font-bold text-tertiary mb-1 flex items-center gap-2">
        <Award size={16} className="text-purple-600" /> QA Quality Review Feed
      </h2>
      <p className="font-label text-xs text-on-surface-muted mb-4">Listen to call logs, view AI sentiment tags, and evaluate caller scores.</p>

      <div className="space-y-4 max-h-[500px] overflow-y-auto pr-1">
        {loading ? (
          <div className="py-12 flex flex-col items-center justify-center">
            <Loader2 className="animate-spin text-slate-400 mb-2" size={24} />
            <p className="text-xs text-slate-400">Loading call recordings...</p>
          </div>
        ) : qaQueue.length === 0 ? (
          <p className="text-xs text-slate-400 text-center py-12">No calls pending QA review.</p>
        ) : (
          qaQueue.map((item) => (
            <div key={item.id} className="p-4 bg-slate-50 border border-slate-100 rounded-2xl space-y-3 shadow-sm hover:shadow-md transition-shadow">
              <div className="flex items-center justify-between">
                <div>
                  <button
                    onClick={() => item.lead_id && onViewLead(item.lead_id)}
                    className="font-bold text-slate-800 hover:text-indigo-600 text-xs flex items-center gap-1"
                  >
                    {item.leads?.name || formatPhone(item.leads?.phone)} <Eye size={12} className="text-slate-400" />
                  </button>
                  <span className="text-[10px] text-slate-450 block font-medium mt-0.5">{timeAgo(item.created_at)}</span>
                </div>
                <span className={`px-2 py-0.5 rounded-full font-bold text-[9px] uppercase border ${
                  item.outcome === "converted" ? "bg-emerald-50 text-emerald-700 border-emerald-200" :
                  item.outcome === "callback" ? "bg-amber-50 text-amber-700 border-amber-200" :
                  "bg-slate-150 text-slate-600 border-slate-200"
                }`}>
                  {item.outcome || item.disposition || "Completed"}
                </span>
              </div>

              {item.ai_summary && (
                <div className="bg-white/80 p-3 rounded-xl border border-slate-200/50 text-[11px] leading-relaxed text-slate-600 space-y-1">
                  {item.ai_summary.brief && <p><span className="font-bold text-slate-800">Brief:</span> {item.ai_summary.brief}</p>}
                  {(item.ai_summary.course || item.ai_summary.product) && (
                    <p><span className="font-bold text-slate-800">Course Interest:</span> {item.ai_summary.course || item.ai_summary.product}</p>
                  )}
                  <p><span className="font-bold text-slate-800">Summary:</span> Next Action: {item.ai_summary.next_action || "—"}</p>
                  {item.ai_summary.budget && <p><span className="font-bold text-slate-800">Budget:</span> {item.ai_summary.budget}</p>}
                  {item.ai_summary.sentiment && <p><span className="font-bold text-slate-800">Sentiment:</span> {item.ai_summary.sentiment}</p>}
                </div>
              )}

              {item.evaluation?.evaluation_version === 2 && (
                <div className="bg-white/80 p-3 rounded-xl border border-slate-200/50 text-[11px] leading-relaxed text-slate-600 space-y-2">
                  <div className="flex items-center justify-between flex-wrap gap-1.5">
                    <div className="flex items-center gap-1 flex-wrap">
                      {SCORE_CRITERIA.map(({ key, reasonKey, label }) => {
                        const value = item.evaluation?.[key];
                        if (value == null) return null;
                        const reason = item.evaluation?.[reasonKey];
                        return (
                          <span
                            key={key}
                            title={typeof reason === "string" ? reason : ""}
                            className="px-1.5 py-0.5 rounded bg-slate-100 border border-slate-200 font-bold text-[9px] text-slate-700 cursor-help"
                          >
                            {label} {String(value)}/10
                          </span>
                        );
                      })}
                      {item.evaluation?.talk_ratio != null && (
                        <span className="px-1.5 py-0.5 rounded bg-slate-100 border border-slate-200 font-bold text-[9px] text-slate-700">
                          Talk {item.evaluation.talk_ratio}%
                        </span>
                      )}
                    </div>
                    {item.evaluation?.quality_label && (
                      <span className={`px-2 py-0.5 rounded-full font-bold text-[9px] uppercase border ${QUALITY_LABEL_STYLES[item.evaluation.quality_label] || ""}`}>
                        {item.evaluation.quality_label} · {item.evaluation.overall_score}/10
                      </span>
                    )}
                  </div>

                  {item.evaluation?.outcome_match === false && (
                    <p className="text-rose-600 font-bold" title={item.evaluation.outcome_match_reason || ""}>
                      ⚠ Outcome Mismatch
                    </p>
                  )}

                  {item.evaluation?.next_step_summary && (
                    <p><span className="font-bold text-slate-800">Next Step:</span> {item.evaluation.next_step_summary}</p>
                  )}

                  {item.evaluation?.purchase_intent && (
                    <p><span className="font-bold text-slate-800">Purchase Intent:</span> {item.evaluation.purchase_intent}</p>
                  )}

                  {item.evaluation?.missed_opportunity && item.evaluation?.missed_opportunity_note && (
                    <p className="text-amber-700"><span className="font-bold">Missed Opportunity:</span> {item.evaluation.missed_opportunity_note}</p>
                  )}

                  {item.evaluation?.coaching_tip && (
                    <p><span className="font-bold text-slate-800">Coaching Tip:</span> {item.evaluation.coaching_tip}</p>
                  )}
                </div>
              )}

              {item.recording_url ? (
                <div className="pt-1">
                  <audio src={item.recording_url} controls className="w-full h-8 text-xs focus:outline-none" />
                </div>
              ) : (
                <p className="text-[10px] text-slate-400 font-medium italic">Audio recording processing or not available</p>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
