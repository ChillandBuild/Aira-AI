"use client";
import { useEffect, useState } from "react";
import { Sparkles, TrendingDown, ChevronLeft, ChevronRight, RefreshCw } from "lucide-react";
import { api } from "@/lib/api";
import type { DigestEntry } from "@/lib/api";
import { cn } from "@/lib/utils";

interface CoachingDigestProps {
  callerId: string | null;
}

export function CoachingDigest({ callerId }: CoachingDigestProps) {
  const [digests, setDigests] = useState<DigestEntry[]>([]);
  const [idx, setIdx] = useState(0);
  const [loading, setLoading] = useState(true);
  const [tip, setTip] = useState<string | null>(null);
  const [tipLoading, setTipLoading] = useState(false);

  useEffect(() => {
    if (!callerId) return;
    setLoading(true);
    api.callers
      .digest(callerId, 7)
      .then((data) => {
        setDigests(data);
        setIdx(0);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [callerId]);

  const current = digests[idx] ?? null;
  const hasPrev = idx < digests.length - 1;
  const hasNext = idx > 0;

  async function loadTip() {
    if (!callerId) return;
    setTipLoading(true);
    try {
      const res = await api.callers.coaching(callerId);
      setTip(res.tip);
    } catch {
      setTip("Could not fetch tip right now.");
    } finally {
      setTipLoading(false);
    }
  }

  if (loading) {
    return (
      <div className="bg-gradient-to-br from-[#f5f3ff] via-white to-[#ede9fe] rounded-card p-6 shadow-card ring-1 ring-primary/10 mb-8">
        <div className="flex items-center gap-3">
          <RefreshCw size={16} className="animate-spin text-primary" />
          <span className="font-body text-sm text-on-surface-muted">Loading coaching digest...</span>
        </div>
      </div>
    );
  }

  if (!current) {
    return (
      <div className="bg-gradient-to-br from-[#f5f3ff] via-white to-[#ede9fe] rounded-card p-6 shadow-card ring-1 ring-primary/10 mb-8">
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-display text-base font-bold text-tertiary flex items-center gap-2">
            <div className="p-1.5 rounded-lg bg-primary/10">
              <Sparkles size={14} className="text-primary" />
            </div>
            AI Coaching
          </h2>
          <button
            onClick={loadTip}
            disabled={tipLoading}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-primary/10 rounded-lg font-label text-xs font-semibold text-primary hover:bg-primary/15 transition-colors disabled:opacity-40"
          >
            <RefreshCw size={12} className={tipLoading ? "animate-spin" : ""} />
            {tip ? "New Tip" : "Get Tip"}
          </button>
        </div>
        <div className="p-4 bg-white/60 rounded-xl border border-primary/5">
          <p className="font-body text-sm text-on-surface leading-relaxed">
            {tipLoading
              ? "Generating your personalized coaching tip..."
              : tip
                ? tip
                : "No coaching digest available yet. Start calling and your daily coaching report will appear here tomorrow."}
          </p>
        </div>
      </div>
    );
  }

  const dateLabel = new Date(current.digest_date + "T00:00:00").toLocaleDateString("en-IN", {
    weekday: "short",
    day: "numeric",
    month: "short",
  });

  const sections = parseCoachingReport(current.coaching_report);
  const weakest = current.stats.weakest_criterion;
  const weakestScore = weakest ? current.stats.criteria_avg[weakest] : null;

  return (
    <div className="bg-gradient-to-br from-[#f5f3ff] via-white to-[#ede9fe] rounded-card p-6 shadow-card ring-1 ring-primary/10 mb-8 relative overflow-hidden">
      <div className="absolute top-0 right-0 w-40 h-40 bg-gradient-to-bl from-primary/5 to-transparent rounded-full -translate-y-1/2 translate-x-1/3" />

      {/* Header */}
      <div className="relative flex items-center justify-between mb-4">
        <h2 className="font-display text-base font-bold text-tertiary flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-primary/10">
            <Sparkles size={14} className="text-primary" />
          </div>
          Daily Coaching Digest
        </h2>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setIdx((i) => i + 1)}
            disabled={!hasPrev}
            className="p-1 rounded-lg hover:bg-primary/10 transition-colors disabled:opacity-30"
          >
            <ChevronLeft size={16} className="text-[#78716c]" />
          </button>
          <span className="font-label text-xs text-[#78716c] px-1 min-w-[80px] text-center">{dateLabel}</span>
          <button
            onClick={() => setIdx((i) => i - 1)}
            disabled={!hasNext}
            className="p-1 rounded-lg hover:bg-primary/10 transition-colors disabled:opacity-30"
          >
            <ChevronRight size={16} className="text-[#78716c]" />
          </button>
        </div>
      </div>

      {/* Quick Stats Bar */}
      <div className="flex items-center gap-3 mb-4 flex-wrap">
        <StatChip label="Calls" value={current.stats.total_calls} />
        <StatChip label="Converted" value={current.stats.converted} variant="success" />
        <StatChip label="Callbacks" value={current.stats.callbacks} variant="warning" />
        <StatChip label="Not Interested" value={current.stats.not_interested} variant="danger" />
        {weakest && weakestScore !== null && (
          <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-amber-50 border border-amber-100">
            <TrendingDown size={12} className="text-amber-600" />
            <span className="font-label text-[11px] font-semibold text-amber-700">
              {weakest.replace(/_/g, " ")} {weakestScore}/10
            </span>
          </span>
        )}
      </div>

      {/* Coaching Report Sections */}
      {current.coaching_report ? (
        <div className="space-y-3">
          {sections.well && (
            <ReportSection
              title="What went well"
              content={sections.well}
              accent="emerald"
            />
          )}
          {sections.weakness && (
            <ReportSection
              title="Focus area"
              content={sections.weakness}
              accent="amber"
            />
          )}
          {sections.phrase && (
            <div className="p-3.5 bg-primary/5 rounded-xl border border-primary/10">
              <p className="font-label text-[10px] uppercase tracking-wider text-primary/60 mb-1">
                Try this phrase today
              </p>
              <p className="font-body text-sm font-semibold text-primary leading-relaxed">
                &ldquo;{sections.phrase}&rdquo;
              </p>
            </div>
          )}
        </div>
      ) : (
        <div className="p-4 bg-white/60 rounded-xl border border-primary/5">
          <p className="font-body text-sm text-on-surface-muted">
            Stats recorded but no coaching report generated for this day.
          </p>
        </div>
      )}
    </div>
  );
}

function StatChip({
  label,
  value,
  variant = "default",
}: {
  label: string;
  value: number;
  variant?: "default" | "success" | "warning" | "danger";
}) {
  const styles = {
    default: "bg-white/70 border-[#e8e3db] text-[#1c1917]",
    success: "bg-emerald-50 border-emerald-100 text-emerald-700",
    warning: "bg-amber-50 border-amber-100 text-amber-700",
    danger: "bg-red-50 border-red-100 text-red-600",
  };
  return (
    <span className={cn("flex items-center gap-1.5 px-2.5 py-1 rounded-lg border font-label text-[11px] font-semibold", styles[variant])}>
      <span className="font-display text-sm font-bold">{value}</span>
      {label}
    </span>
  );
}

function ReportSection({
  title,
  content,
  accent,
}: {
  title: string;
  content: string;
  accent: "emerald" | "amber";
}) {
  const bg = accent === "emerald" ? "bg-emerald-50/60" : "bg-amber-50/60";
  const border = accent === "emerald" ? "border-emerald-100" : "border-amber-100";
  const dot = accent === "emerald" ? "bg-emerald-500" : "bg-amber-500";
  const titleColor = accent === "emerald" ? "text-emerald-700" : "text-amber-700";

  return (
    <div className={cn("p-3.5 rounded-xl border", bg, border)}>
      <div className="flex items-center gap-2 mb-1">
        <span className={cn("w-1.5 h-1.5 rounded-full", dot)} />
        <span className={cn("font-label text-[11px] font-bold uppercase tracking-wider", titleColor)}>
          {title}
        </span>
      </div>
      <p className="font-body text-sm text-on-surface leading-relaxed">{content}</p>
    </div>
  );
}

function parseCoachingReport(report: string | null): {
  well: string | null;
  weakness: string | null;
  phrase: string | null;
} {
  if (!report) return { well: null, weakness: null, phrase: null };

  const lines = report.split("\n").filter((l) => l.trim());
  let well: string | null = null;
  let weakness: string | null = null;
  let phrase: string | null = null;

  let current: "well" | "weakness" | "phrase" | null = null;
  const buckets: Record<string, string[]> = { well: [], weakness: [], phrase: [] };

  for (const line of lines) {
    const lower = line.toLowerCase();
    if (lower.includes("did well") || lower.includes("went well") || lower.includes("strength")) {
      current = "well";
      continue;
    }
    if (lower.includes("weakness") || lower.includes("improve") || lower.includes("focus")) {
      current = "weakness";
      continue;
    }
    if (lower.includes("phrase") || lower.includes("script") || lower.includes("say") || lower.includes("use tomorrow")) {
      current = "phrase";
      continue;
    }
    if (current) {
      buckets[current].push(line.replace(/^[-\d.*)\s]+/, "").trim());
    }
  }

  well = buckets.well.join(" ").trim() || null;
  weakness = buckets.weakness.join(" ").trim() || null;
  phrase = buckets.phrase.join(" ").trim().replace(/^["'“]+|["'”]+$/g, "") || null;

  return { well, weakness, phrase };
}

export function CoachingOneLiner({ callerId }: { callerId: string | null }) {
  const [phrase, setPhrase] = useState<string | null>(null);

  useEffect(() => {
    if (!callerId) return;
    api.callers
      .digest(callerId, 1)
      .then((data) => {
        if (data.length > 0 && data[0].coaching_report) {
          const parsed = parseCoachingReport(data[0].coaching_report);
          setPhrase(parsed.phrase);
        }
      })
      .catch(() => {});
  }, [callerId]);

  if (!phrase) return null;

  return (
    <div className="flex items-center gap-2.5 px-4 py-2.5 bg-gradient-to-r from-[#f5f3ff] to-[#ede9fe] rounded-xl border border-primary/10 mb-4">
      <Sparkles size={14} className="text-primary shrink-0" />
      <p className="font-body text-sm text-primary truncate">
        <span className="font-semibold">Try today:</span> &ldquo;{phrase}&rdquo;
      </p>
    </div>
  );
}
