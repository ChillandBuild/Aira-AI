"use client";
import { cn } from "@/lib/utils";

const SEGMENT_CONFIG = {
  A: {
    label: "Hot",
    bg: "bg-emerald-50",
    text: "text-emerald-700",
    border: "border-emerald-200/80",
    dot: "bg-emerald-500",
  },
  B: {
    label: "Warm",
    bg: "bg-amber-50",
    text: "text-amber-700",
    border: "border-amber-200/80",
    dot: "bg-amber-500",
  },
  C: {
    label: "Cold",
    bg: "bg-slate-50",
    text: "text-slate-600",
    border: "border-slate-200",
    dot: "bg-slate-400",
  },
  D: {
    label: "Disq.",
    bg: "bg-rose-50",
    text: "text-rose-700",
    border: "border-rose-200/80",
    dot: "bg-rose-500",
  },
};

export function SegmentBadge({ segment }: { segment: "A" | "B" | "C" | "D" }) {
  const cfg = SEGMENT_CONFIG[segment] ?? SEGMENT_CONFIG.C;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full font-mono text-[10.5px] font-semibold border leading-tight shrink-0 shadow-2xs transition-all",
        cfg.bg,
        cfg.text,
        cfg.border
      )}
    >
      <span className={cn("w-1.5 h-1.5 rounded-full shrink-0", cfg.dot)} />
      <span>{segment} · {cfg.label}</span>
    </span>
  );
}
