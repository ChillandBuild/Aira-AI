"use client";

import { cn } from "@/lib/utils";
import { ComparisonSelection } from "./periodSelection";

export function comparisonLabel(selection: ComparisonSelection): string {
  if (selection.mode === "off") return "No comparison";
  if (selection.mode === "previous") return "Previous period";
  if (selection.start && selection.end) return `${selection.start} → ${selection.end}`;
  return "Custom comparison";
}

const COMPARISON_OPTIONS: { id: ComparisonSelection["mode"]; label: string }[] = [
  { id: "off", label: "No Comparison" },
  { id: "previous", label: "Previous Period" },
  { id: "custom", label: "Custom Range" },
];

export function ComparisonPicker({
  value,
  onChange,
}: {
  value: ComparisonSelection;
  onChange: (value: ComparisonSelection) => void;
}) {
  const selectMode = (mode: ComparisonSelection["mode"]) => {
    onChange({ ...value, mode });
  };

  return (
    <div className="flex flex-wrap items-center gap-3">
      {/* Pills rendered outside */}
      <div className="flex flex-wrap items-center gap-1 rounded-xl bg-surface-mid/40 p-1">
        {COMPARISON_OPTIONS.map((option) => {
          const isSelected = value.mode === option.id;
          return (
            <button
              key={option.id}
              type="button"
              onClick={() => selectMode(option.id)}
              className={cn(
                "rounded-lg px-2.5 py-1.5 font-label text-xs font-semibold transition-all",
                isSelected
                  ? "bg-white text-primary shadow-xs"
                  : "text-on-surface-muted hover:text-on-surface hover:bg-white/50"
              )}
            >
              {option.label}
            </button>
          );
        })}
      </div>

      {value.mode === "custom" && (
        <div className="flex flex-wrap items-center gap-2 animate-in fade-in duration-200">
          <div className="flex items-center gap-1.5">
            <label
              htmlFor="comparison-range-from"
              className="font-label text-[11px] font-semibold text-on-surface-muted"
            >
              From
            </label>
            <input
              id="comparison-range-from"
              type="date"
              value={value.start}
              max={value.end || undefined}
              onChange={(e) => onChange({ ...value, mode: "custom", start: e.target.value })}
              className="h-8.5 rounded-lg border border-surface-mid bg-white px-2.5 font-body text-xs font-semibold text-on-surface focus:outline-none focus:ring-2 focus:ring-violet-200"
            />
          </div>
          <div className="flex items-center gap-1.5">
            <label
              htmlFor="comparison-range-to"
              className="font-label text-[11px] font-semibold text-on-surface-muted"
            >
              To
            </label>
            <input
              id="comparison-range-to"
              type="date"
              value={value.end}
              min={value.start || undefined}
              onChange={(e) => onChange({ ...value, mode: "custom", end: e.target.value })}
              className="h-8.5 rounded-lg border border-surface-mid bg-white px-2.5 font-body text-xs font-semibold text-on-surface focus:outline-none focus:ring-2 focus:ring-violet-200"
            />
          </div>
        </div>
      )}
    </div>
  );
}
