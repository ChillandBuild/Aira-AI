"use client";
import { cn } from "@/lib/utils";

const SEGMENT_CONFIG = {
  A: { label: "Hot", bg: "bg-segment-a-bg", text: "text-segment-a-text", border: "border-segment-a-border", dot: "bg-segment-a-text" },
  B: { label: "Warm", bg: "bg-segment-b-bg", text: "text-segment-b-text", border: "border-segment-b-border", dot: "bg-segment-b-text" },
  C: { label: "Cold", bg: "bg-segment-c-bg", text: "text-segment-c-text", border: "border-segment-c-border", dot: "bg-segment-c-text" },
  D: { label: "Disq.", bg: "bg-segment-d-bg", text: "text-segment-d-text", border: "border-segment-d-border", dot: "bg-segment-d-text" },
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
