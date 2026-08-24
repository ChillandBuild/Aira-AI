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
  /** The line under the figure — what the number is made of, not a restatement. */
  detail?: string;
};

/** Header KPI cards. Sized to be read at a glance without costing the table its
 *  fold: roughly half the height of a full dashboard card, but not the cramped
 *  single-line strip that replaced them briefly. */
export function StatCards({ items }: { items: StatItem[] }) {
  return (
    <div className="flex flex-wrap gap-2.5">
      {items.map((item) => {
        const tone = TONE[item.tone ?? "neutral"];
        return (
          <div
            key={item.label}
            className="min-w-[162px] rounded-xl border border-border bg-surface px-5 py-3.5 shadow-sm"
          >
            <p className="flex items-center gap-1.5 font-heading text-[10px] font-semibold uppercase tracking-[0.1em] text-ink-muted">
              <span className={cn("h-1.5 w-1.5 flex-shrink-0 rounded-full", tone.dot)} aria-hidden />
              <span className="truncate">{item.label}</span>
            </p>
            <p
              className={cn(
                "mt-2.5 truncate font-heading text-[29px] font-bold leading-none tracking-[-0.035em] tabular-nums",
                tone.value
              )}
              title={item.value}
            >
              {item.value}
            </p>
            {item.detail && (
              <p className="mt-2 truncate font-body text-[11.5px] font-medium text-ink-secondary" title={item.detail}>
                {item.detail}
              </p>
            )}
          </div>
        );
      })}
    </div>
  );
}
