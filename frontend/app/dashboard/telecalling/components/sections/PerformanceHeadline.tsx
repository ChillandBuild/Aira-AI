"use client";

import { Sparkles, Loader2 } from "lucide-react";
import type { TelecallingAnalyticsExtended } from "@/lib/api";

interface PerformanceHeadlineProps {
  stats: TelecallingAnalyticsExtended | null;
  loading: boolean;
  flaggedCount: number;
  isTodayView: boolean;
}

export default function PerformanceHeadline({ stats, loading, flaggedCount, isTodayView }: PerformanceHeadlineProps) {
  const calls = stats?.calls_today ?? 0;
  const connectPct = stats?.connect_rate ? Math.round(stats.connect_rate * 100) : 0;
  const conversions = stats?.conversions_today ?? stats?.outcome_breakdown?.converted ?? 0;
  const lead = isTodayView ? "Today" : "Selected range";

  return (
    <div className="bg-gradient-to-r from-[#2e1065] to-primary rounded-card p-5 shadow-card text-white">
      <div className="flex items-center gap-2 mb-1">
        <Sparkles size={15} className="text-primary-muted" />
        <span className="font-label text-[10px] uppercase font-bold tracking-widest text-primary-muted">
          Today&apos;s Telecalling Report
        </span>
      </div>
      {loading ? (
        <span className="flex items-center gap-2 text-sm font-medium text-primary-light">
          <Loader2 className="animate-spin" size={16} /> Building today&apos;s summary…
        </span>
      ) : (
        <p className="font-display text-lg md:text-xl font-bold leading-snug">
          {lead}: <span className="text-white">{calls}</span> calls
          {" · "}
          <span className="text-white">{connectPct}%</span> connected
          {" · "}
          <span className="text-white">{conversions}</span> conversion{conversions === 1 ? "" : "s"}
          {" · "}
          <span className="text-white">{flaggedCount}</span> agent{flaggedCount === 1 ? "" : "s"} flagged
          {"."}
        </p>
      )}
    </div>
  );
}
