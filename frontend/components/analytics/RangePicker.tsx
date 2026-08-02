"use client";

import { cn } from "@/lib/utils";

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
    <div className="flex flex-wrap items-center gap-3">
      {/* Preset pills rendered directly outside */}
      <div className="flex flex-wrap items-center gap-1 rounded-xl bg-surface-mid/40 p-1">
        {PRESET_OPTIONS.map((option) => {
          const isSelected = value.preset === option.id;
          return (
            <button
              key={option.id}
              type="button"
              onClick={() => onChange({ ...value, preset: option.id })}
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

      {value.preset === "custom" && (
        <div className="flex flex-wrap items-center gap-2 animate-in fade-in duration-200">
          <div className="flex items-center gap-1.5">
            <label
              htmlFor={`${idPrefix}-from`}
              className="font-label text-[11px] font-semibold text-on-surface-muted"
            >
              From
            </label>
            <input
              id={`${idPrefix}-from`}
              type="date"
              value={value.start}
              max={value.end || undefined}
              onChange={(e) => onChange({ ...value, start: e.target.value })}
              className="h-8.5 rounded-lg border border-surface-mid bg-white px-2.5 font-body text-xs font-semibold text-on-surface focus:outline-none focus:ring-2 focus:ring-violet-200"
            />
          </div>
          <div className="flex items-center gap-1.5">
            <label
              htmlFor={`${idPrefix}-to`}
              className="font-label text-[11px] font-semibold text-on-surface-muted"
            >
              To
            </label>
            <input
              id={`${idPrefix}-to`}
              type="date"
              value={value.end}
              min={value.start || undefined}
              onChange={(e) => onChange({ ...value, end: e.target.value })}
              className="h-8.5 rounded-lg border border-surface-mid bg-white px-2.5 font-body text-xs font-semibold text-on-surface focus:outline-none focus:ring-2 focus:ring-violet-200"
            />
          </div>
        </div>
      )}
    </div>
  );
}
