"use client";
import { cn } from "@/lib/utils";

const SEGMENT_CONFIG = {
  A: { label: "Hot", bg: "bg-[#ecfdf5]", text: "text-[#059669]", border: "border-[#bbf7d0]", dot: "bg-[#059669]" },
  B: { label: "Warm", bg: "bg-[#fffbeb]", text: "text-[#d97706]", border: "border-[#fde68a]", dot: "bg-[#d97706]" },
  C: { label: "Cold", bg: "bg-[#f8fafc]", text: "text-[#64748b]", border: "border-[#e2e8f0]", dot: "bg-[#64748b]" },
  D: { label: "Disq.", bg: "bg-[#fff1f2]", text: "text-[#e11d48]", border: "border-[#fecdd3]", dot: "bg-[#e11d48]" },
};

export function SegmentBadge({ segment }: { segment: "A" | "B" | "C" | "D" }) {
  const cfg = SEGMENT_CONFIG[segment];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full font-mono text-[10px] font-semibold border",
        cfg.bg,
        cfg.text,
        cfg.border
      )}
    >
      <span className={cn("w-[5px] h-[5px] rounded-full opacity-80", cfg.dot)} />
      {segment} · {cfg.label}
    </span>
  );
}
