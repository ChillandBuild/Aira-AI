"use client";
import { cn } from "@/lib/utils";

export type StatTone = "neutral" | "positive" | "warning" | "critical";

const TONE: Record<StatTone, { dot: string; ring: string; value: string; bg: string; border: string }> = {
  neutral: {
    dot: "bg-gray-400",
    ring: "ring-gray-200/60",
    value: "text-gray-900",
    bg: "bg-white",
    border: "border-gray-200/80",
  },
  positive: {
    dot: "bg-emerald-500",
    ring: "ring-emerald-100",
    value: "text-emerald-600",
    bg: "bg-gradient-to-br from-white via-white to-emerald-50/25",
    border: "border-emerald-100/90",
  },
  warning: {
    dot: "bg-amber-500",
    ring: "ring-amber-100",
    value: "text-amber-600",
    bg: "bg-gradient-to-br from-white via-white to-amber-50/25",
    border: "border-amber-100/90",
  },
  critical: {
    dot: "bg-rose-500",
    ring: "ring-rose-100",
    value: "text-rose-600",
    bg: "bg-gradient-to-br from-white via-white to-rose-50/30",
    border: "border-rose-100/90",
  },
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
 * else is prose — a person's name, a trigger label.
 */
function isFigure(value: string): boolean {
  return /^[<>~]?\d/.test(value) || value === "—";
}

/** Header KPI cards. Sized to be read at a glance without costing the table its fold */
export function StatCards({ items }: { items: StatItem[] }) {
  return (
    <div className="flex flex-1 flex-wrap gap-2.5">
      {items.map((item) => {
        const tone = TONE[item.tone ?? "neutral"];
        const figure = isFigure(item.value);
        return (
          <div
            key={item.label}
            className={cn(
              "min-w-[145px] flex-1 rounded-2xl border p-3 shadow-xs hover:shadow-sm transition-all",
              tone.bg,
              tone.border
            )}
          >
            <div className="flex items-center justify-between gap-1.5">
              <span className="truncate font-label text-[11px] font-bold uppercase tracking-wider text-gray-500">
                {item.label}
              </span>
              <span className={cn("h-1.5 w-1.5 flex-shrink-0 rounded-full ring-4", tone.ring, tone.dot)} aria-hidden />
            </div>

            <div className="mt-1.5 flex h-[26px] items-center">
              <p
                className={cn(
                  "truncate font-display font-bold tracking-tight",
                  figure
                    ? "text-[22px] leading-none tabular-nums"
                    : "text-sm leading-tight",
                  tone.value
                )}
                title={item.value}
              >
                {item.value}
              </p>
            </div>

            {item.detail && (
              <p className="mt-1 truncate font-body text-[11px] font-medium text-gray-400" title={item.detail}>
                {item.detail}
              </p>
            )}
          </div>
        );
      })}
    </div>
  );
}
