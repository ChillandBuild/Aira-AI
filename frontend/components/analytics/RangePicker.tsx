"use client";

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
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap gap-1.5" role="group" aria-label="Reporting period">
        {PRESET_OPTIONS.map((option) => (
          <button
            key={option.id}
            type="button"
            onClick={() => onChange({ ...value, preset: option.id })}
            aria-pressed={value.preset === option.id}
            className={`rounded-full border px-3 py-1.5 font-label text-xs font-semibold transition-colors ${
              value.preset === option.id
                ? "border-violet-200 bg-violet-50 text-violet-700 shadow-sm"
                : "border-[#e8e3db] bg-white text-on-surface-muted hover:border-violet-200 hover:text-violet-700"
            }`}
          >
            {option.label}
          </button>
        ))}
      </div>

      {value.preset === "custom" && (
        <div className="flex flex-wrap items-end gap-2.5">
          <div className="w-[150px]">
            <label
              htmlFor={`${idPrefix}-from`}
              className="mb-1 block font-label text-[9px] font-bold uppercase tracking-wider text-on-surface-muted"
            >
              From
            </label>
            <input
              id={`${idPrefix}-from`}
              type="date"
              value={value.start}
              max={value.end || undefined}
              onChange={(e) => onChange({ ...value, start: e.target.value })}
              className="h-9 w-full rounded-xl border border-surface-mid bg-white px-3 font-body text-xs font-semibold text-on-surface focus:outline-none focus:ring-2 focus:ring-violet-200"
            />
          </div>
          <div className="w-[150px]">
            <label
              htmlFor={`${idPrefix}-to`}
              className="mb-1 block font-label text-[9px] font-bold uppercase tracking-wider text-on-surface-muted"
            >
              To
            </label>
            <input
              id={`${idPrefix}-to`}
              type="date"
              value={value.end}
              min={value.start || undefined}
              onChange={(e) => onChange({ ...value, end: e.target.value })}
              className="h-9 w-full rounded-xl border border-surface-mid bg-white px-3 font-body text-xs font-semibold text-on-surface focus:outline-none focus:ring-2 focus:ring-violet-200"
            />
          </div>
        </div>
      )}
    </div>
  );
}
