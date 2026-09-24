"use client";

import { useState } from "react";
import { AlertTriangle, CheckCircle2, Flag, Loader2, RefreshCw, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { api, type CallLog, type ScoreCriterion, type TranscriptPreview } from "@/lib/api";

export const SCORE_CRITERIA: { key: ScoreCriterion; label: string; hint: string }[] = [
  { key: "greeting_quality", label: "Greeting", hint: "Introduced themselves and the company clearly" },
  { key: "communication_clarity", label: "Clarity", hint: "Speech was clear and easy to follow" },
  { key: "product_knowledge", label: "Product knowledge", hint: "Information matched your knowledge base" },
  { key: "requirement_understanding", label: "Requirement understanding", hint: "Asked good questions, understood the need" },
  { key: "conversation_engagement", label: "Engagement", hint: "Worked to engage the customer, listened and responded" },
  { key: "objection_handling", label: "Objection handling", hint: "Dealt with doubts and objections well" },
  { key: "professionalism", label: "Professionalism", hint: "Polite, no rudeness or arguing" },
  { key: "tone", label: "Tone", hint: "Sounded warm, confident and energetic (the AI listens to the audio)" },
];

const CRITERION_LABEL = Object.fromEntries(SCORE_CRITERIA.map((c) => [c.key, c.label])) as Record<ScoreCriterion, string>;

const OUTCOME_LABEL: Record<string, string> = {
  converted: "Converted",
  interested: "Interested",
  callback: "Callback",
  not_interested: "Not interested",
  no_answer: "No answer",
};

export function scoreColor(score: number): string {
  if (score >= 8) return "text-emerald-700 bg-emerald-50 border-emerald-200";
  if (score >= 6) return "text-cyan-700 bg-cyan-50 border-cyan-200";
  if (score >= 4) return "text-amber-700 bg-amber-50 border-amber-200";
  return "text-rose-700 bg-rose-50 border-rose-200";
}

function barColor(value: number): string {
  if (value >= 8) return "bg-emerald-500";
  if (value >= 6) return "bg-cyan-500";
  if (value >= 4) return "bg-amber-500";
  return "bg-rose-500";
}

function isProcessing(log: CallLog): boolean {
  return log.ai_status === "pending" || log.ai_status === "transcribing" || log.ai_status === "scoring";
}

export function anyProcessing(logs: CallLog[]): boolean {
  return logs.some(isProcessing);
}

const PILL = "shrink-0 inline-flex items-center gap-1 px-2 py-0.5 rounded-full border font-label text-[9px] font-bold";

/** Compact status for a call row: processing stage, score, or why it isn't scored. */
export function CallScorePill({ log }: { log: CallLog }) {
  if (log.provider !== "telecmi") return null;
  if (log.flag_status === "open") {
    return (
      <span className={`${PILL} bg-rose-50 text-rose-700 border-rose-200`}>
        <Flag size={9} /> Flagged
      </span>
    );
  }
  if (isProcessing(log)) {
    return (
      <span className={`${PILL} bg-[#faf8f5] text-[#78716c] border-[#e8e3db]`}>
        <Loader2 size={9} className="animate-spin" />
        {log.ai_status === "scoring" ? "Scoring…" : "Transcribing…"}
      </span>
    );
  }
  switch (log.score_status) {
    case "scored":
      return log.score != null ? <span className={`${PILL} ${scoreColor(log.score)}`}>{log.score.toFixed(1)}/10</span> : null;
    case "short_call":
      return <span className={`${PILL} bg-[#faf8f5] text-[#a8a29e] border-[#e8e3db]`}>Short call</span>;
    case "no_answer":
      return <span className={`${PILL} bg-[#faf8f5] text-[#a8a29e] border-[#e8e3db]`}>Not scored</span>;
    case "awaiting_outcome":
      return <span className={`${PILL} bg-amber-50 text-amber-700 border-amber-200`}>Mark outcome to score</span>;
    case "failed":
      return <span className={`${PILL} bg-rose-50 text-rose-700 border-rose-200`}>Processing failed</span>;
    default:
      return null;
  }
}

/** First and last line only; the middle is never sent to the browser. */
export function MaskedTranscript({ preview }: { preview?: TranscriptPreview | null }) {
  if (!preview) return null;
  return (
    <div className="rounded-xl border border-[#f0ece4] bg-[#faf8f5] px-3 py-2.5">
      <p className="font-label text-[9px] uppercase tracking-widest font-extrabold text-[#a8a29e] mb-1.5">Transcript</p>
      <p className="font-body text-[11px] leading-relaxed text-[#44403c]">{preview.first}</p>
      {preview.last && (
        <>
          <div className="my-1.5 flex items-center gap-2" aria-label={`${preview.hidden_lines} lines hidden`}>
            <span className="h-2 flex-1 rounded-full bg-[repeating-linear-gradient(90deg,#e8e3db_0_6px,transparent_6px_10px)]" />
            {preview.hidden_lines > 0 && (
              <span className="font-label text-[9px] font-bold text-[#a8a29e] whitespace-nowrap">
                {preview.hidden_lines} {preview.hidden_lines === 1 ? "line" : "lines"} hidden
              </span>
            )}
            <span className="h-2 flex-1 rounded-full bg-[repeating-linear-gradient(90deg,#e8e3db_0_6px,transparent_6px_10px)]" />
          </div>
          <p className="font-body text-[11px] leading-relaxed text-[#44403c]">{preview.last}</p>
        </>
      )}
    </div>
  );
}

function ProcessingBanner({ log, onRetried }: { log: CallLog; onRetried?: () => void }) {
  const [retrying, setRetrying] = useState(false);
  if (isProcessing(log)) {
    const scoring = log.ai_status === "scoring";
    return (
      <div className="flex items-center gap-2.5 rounded-xl border border-[#e8e3db] bg-[#faf8f5] px-3 py-2.5">
        <Loader2 size={14} className="animate-spin text-primary shrink-0" />
        <div>
          <p className="font-body text-[11px] font-bold text-[#292524]">{scoring ? "Scoring the call…" : "Transcribing the recording…"}</p>
          <p className="font-label text-[10px] text-[#a8a29e]">
            {scoring ? "The score and summary appear here in a moment." : "Long calls take a minute or two. The score and summary follow."}
          </p>
        </div>
      </div>
    );
  }
  if (log.ai_status !== "failed") return null;

  async function retry() {
    setRetrying(true);
    try {
      await api.calls.retryAi(log.id);
      toast.success("Processing restarted");
      onRetried?.();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not restart processing");
    } finally {
      setRetrying(false);
    }
  }

  return (
    <div className="flex items-center justify-between gap-3 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2.5">
      <div className="flex items-start gap-2 min-w-0">
        <AlertTriangle size={14} className="text-rose-600 shrink-0 mt-0.5" />
        <div className="min-w-0">
          <p className="font-body text-[11px] font-bold text-rose-800">Processing failed</p>
          <p className="font-label text-[10px] text-rose-700/80 truncate" title={log.ai_error ?? ""}>
            This call wasn&apos;t transcribed or scored after 3 attempts.
          </p>
        </div>
      </div>
      <button
        type="button"
        onClick={() => void retry()}
        disabled={retrying}
        className="shrink-0 inline-flex items-center gap-1.5 rounded-lg bg-white border border-rose-200 px-2.5 py-1.5 font-label text-[10px] font-extrabold text-rose-700 hover:bg-rose-100 disabled:opacity-60 transition-colors"
      >
        <RefreshCw size={11} className={retrying ? "animate-spin" : ""} /> Retry
      </button>
    </div>
  );
}

export function FlagNotice({ log }: { log: CallLog }) {
  if (!log.flag_status) return null;
  const tone =
    log.flag_status === "open"
      ? "border-rose-200 bg-rose-50 text-rose-800"
      : log.flag_status === "confirmed"
        ? "border-amber-200 bg-amber-50 text-amber-800"
        : "border-[#e8e3db] bg-[#faf8f5] text-[#57534e]";
  const verdict =
    log.flag_status === "open"
      ? "Waiting for admin review. The outcome can't be changed."
      : log.flag_status === "confirmed"
        ? "Admin confirmed: scored with 0/3 for the outcome."
        : "Admin dismissed: counts as No answer, not scored.";
  return (
    <div className={`flex items-start gap-2 rounded-xl border px-3 py-2.5 ${tone}`}>
      <Flag size={13} className="shrink-0 mt-0.5" />
      <div>
        <p className="font-body text-[11px] font-bold">{log.flag_reason || "Marked No answer, but the customer spoke."}</p>
        <p className="font-label text-[10px] opacity-80 mt-0.5">{verdict}</p>
      </div>
    </div>
  );
}

function ScoreBreakdown({ log }: { log: CallLog }) {
  const breakdown = log.score_breakdown;
  const evaluation = log.evaluation;
  if (log.score_status !== "scored" || log.score == null || !breakdown || !evaluation) return null;
  const outcome = OUTCOME_LABEL[breakdown.marked_outcome] ?? breakdown.marked_outcome;
  return (
    <div className="rounded-xl border border-[#e8e3db] bg-white px-3 py-3 space-y-3">
      <div className="flex items-center gap-3">
        <div className={`flex h-12 w-12 shrink-0 flex-col items-center justify-center rounded-xl border ${scoreColor(log.score)}`}>
          <span className="font-display text-base font-extrabold leading-none">{log.score.toFixed(1)}</span>
          <span className="font-label text-[8px] font-bold opacity-70">/ 10</span>
        </div>
        <div className="grid flex-1 grid-cols-2 gap-2">
          <div className="rounded-lg bg-[#faf8f5] px-2.5 py-1.5">
            <p className="font-label text-[9px] uppercase tracking-wider font-extrabold text-[#a8a29e]">AI review</p>
            <p className="font-body text-xs font-bold text-[#292524]">{breakdown.ai_points.toFixed(1)} <span className="text-[#a8a29e] font-semibold">/ 7</span></p>
          </div>
          <div className="rounded-lg bg-[#faf8f5] px-2.5 py-1.5">
            <p className="font-label text-[9px] uppercase tracking-wider font-extrabold text-[#a8a29e]">Outcome</p>
            <p className="font-body text-xs font-bold text-[#292524]">{breakdown.outcome_points.toFixed(1)} <span className="text-[#a8a29e] font-semibold">/ 3</span></p>
          </div>
        </div>
      </div>

      <div className="space-y-1.5">
        {breakdown.criteria.map((key) => {
          const value = evaluation[key];
          if (typeof value !== "number") return null;
          const reason = evaluation[`${key}_reason` as keyof typeof evaluation];
          return (
            <div key={key} title={typeof reason === "string" ? reason : undefined} className="grid grid-cols-[minmax(0,9rem)_1fr_2rem] items-center gap-2 cursor-help">
              <span className="font-label text-[10px] font-semibold text-[#57534e] truncate">{CRITERION_LABEL[key] ?? key}</span>
              <span className="h-1.5 rounded-full bg-[#f0ece4] overflow-hidden">
                <span className={`block h-full rounded-full ${barColor(value)}`} style={{ width: `${value * 10}%` }} />
              </span>
              <span className="font-label text-[10px] font-bold text-[#292524] text-right">{value}</span>
            </div>
          );
        })}
        {evaluation.criteria_skipped?.includes("tone") && (
          <p className="font-label text-[10px] text-[#a8a29e]">Tone wasn&apos;t scored: the recording was too large to attach.</p>
        )}
      </div>

      {breakdown.marked_outcome === "no_answer" ? (
        <p className="flex items-start gap-1.5 border-t border-[#f0ece4] pt-2.5 font-body text-[11px] text-[#57534e]">
          <AlertTriangle size={12} className="text-rose-600 shrink-0 mt-0.5" />
          <span>Marked <span className="font-bold text-[#292524]">No answer</span> on a real conversation, so the outcome part is 0/3.</span>
        </p>
      ) : (
      <div className="space-y-1 border-t border-[#f0ece4] pt-2.5">
        <p className="flex items-start gap-1.5 font-body text-[11px] text-[#57534e]">
          {breakdown.accuracy_point > 0 ? (
            <CheckCircle2 size={12} className="text-emerald-600 shrink-0 mt-0.5" />
          ) : (
            <AlertTriangle size={12} className="text-amber-600 shrink-0 mt-0.5" />
          )}
          <span>
            Marked <span className="font-bold text-[#292524]">{outcome}</span>
            {breakdown.accuracy_point > 0 ? ": matches the call (+1)." : ": doesn't match what happened on the call (+0)."}
          </span>
        </p>
        {evaluation.closing_move_reason && (
          <p className="font-body text-[11px] text-[#57534e]">
            <span className="font-bold text-[#292524]">Closing move {breakdown.closing_points.toFixed(1)}/2:</span> {evaluation.closing_move_reason}
          </p>
        )}
      </div>
      )}
    </div>
  );
}

/** Everything the AI produced for a recorded call, in the order people read it. */
export function CallAiDetail({ log, onChanged }: { log: CallLog; onChanged?: () => void }) {
  if (log.provider !== "telecmi") return null;
  const brief = log.ai_summary?.brief;
  return (
    <div className="space-y-2.5">
      <ProcessingBanner log={log} onRetried={onChanged} />
      <FlagNotice log={log} />
      {log.score_status === "short_call" && (
        <p className="font-label text-[10px] text-[#a8a29e]">Under 30 seconds of talk time: counted, but not scored.</p>
      )}
      {log.score_status === "awaiting_outcome" && (
        <p className="font-label text-[10px] text-amber-700">The AI review is ready. Mark the outcome to get the score.</p>
      )}
      <ScoreBreakdown log={log} />
      {brief && (
        <div className="rounded-xl border border-[#f0ece4] bg-white px-3 py-2.5">
          <p className="font-label text-[9px] uppercase tracking-widest font-extrabold text-primary mb-1 flex items-center gap-1">
            <Sparkles size={10} /> Summary
          </p>
          <p className="font-body text-[11px] leading-relaxed text-[#44403c]">{brief}</p>
        </div>
      )}
      <MaskedTranscript preview={log.transcript_preview} />
      {log.evaluation?.coaching_tip && (
        <p className="font-body text-[11px] leading-relaxed text-amber-800 bg-amber-50 border border-amber-200 rounded-xl px-2.5 py-2">
          <span className="font-bold">Coaching: </span>
          {log.evaluation.coaching_tip}
        </p>
      )}
    </div>
  );
}
