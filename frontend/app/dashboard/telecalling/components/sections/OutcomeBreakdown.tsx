"use client";

import type { TelecallingAnalyticsExtended } from "@/lib/api";

const OUTCOMES: { key: keyof TelecallingAnalyticsExtended["outcome_breakdown"]; label: string; bar: string }[] = [
  { key: "converted", label: "Converted", bar: "bg-emerald-500" },
  { key: "callback", label: "Callback", bar: "bg-blue-500" },
  { key: "not_interested", label: "Not Interested", bar: "bg-rose-500" },
  { key: "no_answer", label: "No Answer", bar: "bg-amber-400" },
];

export default function OutcomeBreakdown({ stats }: { stats: TelecallingAnalyticsExtended | null }) {
  const ob = stats?.outcome_breakdown;
  const total = ob ? OUTCOMES.reduce((sum, o) => sum + (ob[o.key] ?? 0), 0) : 0;

  return (
    <div className="bg-surface rounded-card p-6 shadow-card ring-1 ring-[#c4c7c7]/15">
      <h2 className="font-display text-base font-bold text-primary mb-1">Outcome Breakdown</h2>
      <p className="font-label text-xs text-on-surface-muted mb-5">How the calls in this window resolved.</p>

      {total === 0 ? (
        <p className="font-body text-sm text-on-surface-muted text-center py-6">No call outcomes in this window.</p>
      ) : (
        <div className="space-y-3">
          {OUTCOMES.map(({ key, label, bar }) => {
            const count = ob?.[key] ?? 0;
            const pct = total === 0 ? 0 : Math.round((count / total) * 100);
            return (
              <div key={key} className="flex items-center gap-3">
                <span className="font-label text-xs text-on-surface-muted w-28 shrink-0">{label}</span>
                <div className="flex-1 bg-surface-mid rounded-full h-4 overflow-hidden">
                  <div className={`h-4 rounded-full ${bar} transition-all`} style={{ width: `${pct}%` }} />
                </div>
                <span className="font-label text-xs text-on-surface w-8 text-right shrink-0">{count}</span>
                <span className="font-label text-xs text-on-surface-muted w-8 shrink-0">{pct}%</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
