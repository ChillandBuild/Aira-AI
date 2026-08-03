"use client";

import { ChevronDown } from "lucide-react";

export type Preset =
  | "today" | "yesterday"
  | "last_7d" | "last_14d" | "last_30d"
  | "custom";

export type RangeValue = { preset: Preset; start: string; end: string };

const PRESET_OPTIONS: { id: Preset; label: string }[] = [
  { id: "today", label: "Today" },
  { id: "yesterday", label: "Yesterday" },
  { id: "last_7d", label: "7 days" },
  { id: "last_14d", label: "14 days" },
  { id: "last_30d", label: "30 days" },
  { id: "custom", label: "Custom" },
];

export function RangePicker({
  value,
  onChange,
  idPrefix = "range",
}: {
  value: RangeValue;
  onChange: (v: RangeValue) => void;
  idPrefix?: string;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="relative w-[132px] shrink-0">
        <select
          value={value.preset}
          onChange={(e) => onChange({ ...value, preset: e.target.value as Preset })}
          className="h-9 w-full cursor-pointer appearance-none rounded-xl border border-surface-mid bg-white px-3 pr-8 font-body text-xs font-semibold text-on-surface shadow-[inset_0_1px_0_rgba(255,255,255,0.8)] transition-colors hover:border-violet-200 focus:outline-none focus:ring-2 focus:ring-violet-200"
        >
          {PRESET_OPTIONS.map((option) => (
            <option key={option.id} value={option.id}>
              {option.label}
            </option>
          ))}
        </select>
        <ChevronDown size={14} className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-on-surface-muted" />
      </div>

      {value.preset === "custom" && (
        <>
          <input
            id={`${idPrefix}-from`}
            type="date"
            aria-label="From"
            value={value.start}
            max={value.end || undefined}
            onChange={(e) => onChange({ ...value, start: e.target.value })}
            className="h-9 w-[122px] shrink-0 rounded-xl border border-surface-mid bg-white px-2.5 font-body text-xs font-semibold text-on-surface focus:outline-none focus:ring-2 focus:ring-violet-200"
          />
          <span className="font-label text-xs text-on-surface-muted">→</span>
          <input
            id={`${idPrefix}-to`}
            type="date"
            aria-label="To"
            value={value.end}
            min={value.start || undefined}
            onChange={(e) => onChange({ ...value, end: e.target.value })}
            className="h-9 w-[122px] shrink-0 rounded-xl border border-surface-mid bg-white px-2.5 font-body text-xs font-semibold text-on-surface focus:outline-none focus:ring-2 focus:ring-violet-200"
          />
        </>
      )}
    </div>
  );
}
