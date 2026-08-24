"use client";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

export type StatTone = "neutral" | "positive" | "warning" | "critical";

const TONE: Record<StatTone, { chip: string; rule: string; figure: string; meter: string }> = {
  neutral: {
    chip: "bg-surface-mid text-ink-secondary",
    rule: "bg-border",
    figure: "text-ink",
    meter: "bg-ink-muted",
  },
  positive: {
    chip: "bg-emerald-50 text-success",
    rule: "bg-success/50",
    figure: "text-success",
    meter: "bg-success",
  },
  warning: {
    chip: "bg-amber-50 text-warning",
    rule: "bg-warning/50",
    figure: "text-warning",
    meter: "bg-warning",
  },
  critical: {
    chip: "bg-rose-50 text-danger",
    rule: "bg-danger/60",
    figure: "text-danger",
    meter: "bg-danger",
  },
};

interface StatCardProps {
  icon: LucideIcon;
  label: string;
  /** Rendered as-is. Numbers get mono tabular figures; short words get the
   *  display face at a smaller size so a name doesn't overflow the card. */
  value: string;
  /** Context under the figure — what the number is made of, not a repeat of it. */
  detail?: string;
  tone?: StatTone;
  /** Optional proportion bar. Encodes the share in form as well as number,
   *  so "5 of 6 breaching" reads at a glance without parsing the sentence. */
  meter?: { value: number; max: number };
  /** Set for values that are words rather than figures (a person's name). */
  compact?: boolean;
}

export function StatCard({ icon: Icon, label, value, detail, tone = "neutral", meter, compact }: StatCardProps) {
  const t = TONE[tone];
  const pct = meter && meter.max > 0 ? Math.min(100, Math.round((meter.value / meter.max) * 100)) : null;

  return (
    <div className="relative overflow-hidden rounded-2xl border border-border bg-surface shadow-card transition-shadow duration-200 hover:shadow-card-hover">
      <span className={cn("absolute inset-x-0 top-0 h-[3px]", t.rule)} aria-hidden />
      <div className="p-4 pt-[18px]">
        <div className="flex items-center gap-2.5">
          <span className={cn("flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-lg", t.chip)}>
            <Icon size={14} strokeWidth={2.4} />
          </span>
          <span className="font-heading text-[10px] font-semibold uppercase tracking-[0.09em] text-ink-muted">
            {label}
          </span>
        </div>

        <p
          className={cn(
            "mt-3 leading-none tracking-[-0.04em]",
            compact
              ? "font-heading text-[19px] font-bold truncate"
              : "font-mono text-[28px] font-bold tabular-nums",
            t.figure
          )}
          title={compact ? value : undefined}
        >
          {value}
        </p>

        {pct !== null && (
          <div className="mt-3 h-1 w-full overflow-hidden rounded-full bg-surface-mid">
            <span className={cn("block h-full rounded-full transition-[width] duration-500", t.meter)} style={{ width: `${pct}%` }} />
          </div>
        )}

        {detail && <p className="mt-2.5 font-body text-[11.5px] font-medium leading-snug text-ink-secondary">{detail}</p>}
      </div>
    </div>
  );
}
