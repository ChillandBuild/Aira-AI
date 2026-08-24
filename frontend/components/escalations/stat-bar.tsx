"use client";
import { cn } from "@/lib/utils";

export type StatTone = "neutral" | "positive" | "warning" | "critical";

const TONE: Record<StatTone, { dot: string; value: string }> = {
  neutral: { dot: "bg-ink-muted", value: "text-ink" },
  positive: { dot: "bg-success", value: "text-success" },
  warning: { dot: "bg-warning", value: "text-warning" },
  critical: { dot: "bg-danger", value: "text-danger" },
};

export type StatItem = {
  label: string;
  value: string;
  tone?: StatTone;
  /** Shown on hover — the detail that used to sit under the figure. */
  hint?: string;
};

/** Compact header strip. Replaces the full-width KPI cards, which cost ~200px
 *  of vertical space above the table for four numbers; this reads the same at
 *  roughly a third of the height and sits beside the page title. */
export function StatBar({ items }: { items: StatItem[] }) {
  return (
    <div className="flex flex-wrap items-stretch divide-x divide-border overflow-hidden rounded-xl border border-border bg-surface shadow-sm">
      {items.map((item) => {
        const tone = TONE[item.tone ?? "neutral"];
        return (
          <div key={item.label} className="min-w-[104px] px-4 py-2" title={item.hint}>
            <p className="flex items-center gap-1.5 font-heading text-[9px] font-semibold uppercase tracking-[0.1em] text-ink-muted">
              <span className={cn("h-1.5 w-1.5 flex-shrink-0 rounded-full", tone.dot)} aria-hidden />
              <span className="truncate">{item.label}</span>
            </p>
            <p
              className={cn(
                "mt-1 truncate font-heading text-[17px] font-bold leading-none tracking-[-0.03em] tabular-nums",
                tone.value
              )}
            >
              {item.value}
            </p>
          </div>
        );
      })}
    </div>
  );
}
