"use client";

import { ChevronDown } from "lucide-react";
import { ComparisonSelection } from "./periodSelection";

export function comparisonLabel(selection: ComparisonSelection): string {
  if (selection.mode === "off") return "No comparison";
  if (selection.mode === "previous") return "Previous period";
  if (selection.start && selection.end) return `${selection.start} → ${selection.end}`;
  return "Custom comparison";
}

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
    <div className="flex flex-wrap items-center gap-2">
      <div className="relative w-[132px] shrink-0">
        <select
          value={value.mode}
          onChange={(e) => selectMode(e.target.value as ComparisonSelection["mode"])}
          className="h-9 w-full cursor-pointer appearance-none rounded-xl border border-surface-mid bg-white px-3 pr-8 font-body text-xs font-semibold text-on-surface shadow-[inset_0_1px_0_rgba(255,255,255,0.8)] transition-colors hover:border-violet-200 focus:outline-none focus:ring-2 focus:ring-violet-200"
        >
          {([
            ["off", "Off"],
            ["previous", "Previous period"],
            ["custom", "Custom"],
          ] as const).map(([mode, label]) => (
            <option key={mode} value={mode}>
              {label}
            </option>
          ))}
        </select>
        <ChevronDown size={14} className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-on-surface-muted" />
      </div>

      {value.mode === "custom" && (
        <>
          <input
            id="comparison-range-from"
            type="date"
            aria-label="From"
            value={value.start}
            max={value.end || undefined}
            onChange={(e) => onChange({ mode: "custom", start: e.target.value, end: value.end })}
            className="h-9 w-[122px] shrink-0 rounded-xl border border-surface-mid bg-white px-2.5 font-body text-xs font-semibold text-on-surface focus:outline-none focus:ring-2 focus:ring-violet-200"
          />
          <span className="font-label text-xs text-on-surface-muted">→</span>
          <input
            id="comparison-range-to"
            type="date"
            aria-label="To"
            value={value.end}
            min={value.start || undefined}
            onChange={(e) => onChange({ mode: "custom", start: value.start, end: e.target.value })}
            className="h-9 w-[122px] shrink-0 rounded-xl border border-surface-mid bg-white px-2.5 font-body text-xs font-semibold text-on-surface focus:outline-none focus:ring-2 focus:ring-violet-200"
          />
        </>
      )}
    </div>
  );
}
