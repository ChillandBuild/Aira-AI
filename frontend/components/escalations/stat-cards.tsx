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

/**
 * A figure is a count or a duration ("13", "7h 5m", "<1m", "—"). Everything
 * else is prose — a person's name, a trigger label — and prose set at display
 * size reads as a headline rather than a statistic, so it gets its own step
 * on the scale.
 */
function isFigure(value: string): boolean {
  return /^[<>~]?\d/.test(value) || value === "—";
}

/** Header KPI cards. Sized to be read at a glance without costing the table its
 *  fold: roughly half the height of a full dashboard card, but not the cramped
 *  single-line strip that replaced them briefly. */
export function StatCards({ items }: { items: StatItem[] }) {
  return (
    <div className="flex flex-1 flex-wrap gap-2.5">
      {items.map((item) => {
        const tone = TONE[item.tone ?? "neutral"];
        const figure = isFigure(item.value);
        return (
          <div
            key={item.label}
            className="min-w-[150px] flex-1 rounded-xl border border-border bg-surface px-4 py-3 shadow-sm"
          >
            <p className="flex items-center gap-1.5 font-heading text-[10px] font-semibold uppercase tracking-[0.09em] text-ink-muted">
              <span className={cn("h-1.5 w-1.5 flex-shrink-0 rounded-full", tone.dot)} aria-hidden />
              <span className="truncate">{item.label}</span>
            </p>
            {/* Fixed band so a 24px figure and a 15px name still leave their
                detail lines on the same baseline across the row. */}
            <div className="mt-2 flex h-[26px] items-center">
              <p
                className={cn(
                  "truncate font-heading font-semibold",
                  figure
                    ? "text-[24px] leading-none tracking-[-0.03em] tabular-nums"
                    : "text-[15px] leading-tight tracking-[-0.005em]",
                  tone.value
                )}
                title={item.value}
              >
                {item.value}
              </p>
            </div>
            {item.detail && (
              <p className="mt-1.5 truncate font-body text-[11px] font-medium text-ink-secondary" title={item.detail}>
                {item.detail}
              </p>
            )}
          </div>
        );
      })}
    </div>
  );
}
