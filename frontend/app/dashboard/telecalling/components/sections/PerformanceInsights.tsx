"use client";

import type { TelecallingAnalyticsExtended } from "@/lib/api";

interface PerformanceInsightsProps {
  stats: TelecallingAnalyticsExtended | null;
  // The 7-day comparison callout is only valid when the view covers today.
  showComparison: boolean;
}

interface Insight {
  key: string;
  icon: string;
  text: string;
  tone: "good" | "warn" | "info";
}

const TONE_CLASS: Record<Insight["tone"], string> = {
  good: "bg-emerald-50 border-emerald-200 text-emerald-800",
  warn: "bg-rose-50 border-rose-200 text-rose-800",
  info: "bg-primary-light border-primary-muted text-primary-dark",
};

function buildInsights(stats: TelecallingAnalyticsExtended, showComparison: boolean): Insight[] {
  const out: Insight[] = [];
  const callers = (stats.per_caller || []).filter((c) => (c.calls_today || 0) > 0);

  // Top connect rate (★)
  const byConnect = [...callers].sort((a, b) => (b.connect_rate || 0) - (a.connect_rate || 0));
  if (byConnect.length > 0 && (byConnect[0].connect_rate || 0) > 0) {
    const top = byConnect[0];
    out.push({
      key: "top-connect",
      icon: "★",
      tone: "good",
      text: `${top.name} leads on connect rate at ${Math.round((top.connect_rate || 0) * 100)}%.`,
    });
  }

  // Bunking flag or highest idle (⚠)
  const bunking = callers.find((c) => c.bunking_flag);
  if (bunking) {
    out.push({
      key: "bunking",
      icon: "⚠",
      tone: "warn",
      text: `${bunking.name} has a long idle gap (bunking alert).`,
    });
  } else {
    const byIdle = [...callers].sort((a, b) => (b.idle_minutes_today || 0) - (a.idle_minutes_today || 0));
    if (byIdle.length > 0 && (byIdle[0].idle_minutes_today || 0) >= 15) {
      const top = byIdle[0];
      out.push({
        key: "idle",
        icon: "⚠",
        tone: "warn",
        text: `${top.name} has the most idle time (${Math.round(top.idle_minutes_today || 0)} min).`,
      });
    }
  }

  // Biggest drop: team connect rate vs 7-day avg
  const comp = showComparison ? stats.comparison : undefined;
  if (comp && typeof stats.connect_rate === "number") {
    const dropPts = Math.round((comp.avg_7d.connect_rate - stats.connect_rate) * 100);
    if (dropPts >= 5) {
      out.push({
        key: "team-drop",
        icon: "▼",
        tone: "warn",
        text: `Team connect rate is ${dropPts} pts below the 7-day average.`,
      });
    } else if (dropPts <= -5) {
      out.push({
        key: "team-up",
        icon: "▲",
        tone: "good",
        text: `Team connect rate is ${Math.abs(dropPts)} pts above the 7-day average.`,
      });
    }
  }

  return out.slice(0, 4);
}

export default function PerformanceInsights({ stats, showComparison }: PerformanceInsightsProps) {
  if (!stats) return null;
  const insights = buildInsights(stats, showComparison);
  if (insights.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-3">
      {insights.map((ins) => (
        <div
          key={ins.key}
          className={`flex items-center gap-2 px-3.5 py-2 rounded-xl border text-xs font-semibold ${TONE_CLASS[ins.tone]}`}
        >
          <span className="text-sm leading-none">{ins.icon}</span>
          <span>{ins.text}</span>
        </div>
      ))}
    </div>
  );
}
