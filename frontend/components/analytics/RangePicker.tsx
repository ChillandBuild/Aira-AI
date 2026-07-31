"use client";

export type Preset =
  | "this_month" | "last_month" | "this_week" | "last_week"
  | "last_7d" | "last_14d" | "last_30d" | "custom";

export type RangeValue = { preset: Preset; start: string; end: string };

const PRESET_OPTIONS: { id: Preset; label: string }[] = [
  { id: "this_month", label: "This Month" },
  { id: "last_month", label: "Last Month" },
  { id: "this_week", label: "This Week" },
  { id: "last_week", label: "Last Week" },
  { id: "last_7d", label: "7 Days" },
  { id: "last_14d", label: "14 Days" },
  { id: "last_30d", label: "30 Days" },
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
      <div className="-mx-1 overflow-x-auto px-1 pb-1">
        <div className="flex w-max gap-1 rounded-xl bg-surface-low p-1 ring-1 ring-[#c4c7c7]/15">
          {PRESET_OPTIONS.map((option) => (
            <button
              key={option.id}
              onClick={() => onChange({ ...value, preset: option.id })}
              className={`shrink-0 rounded-lg px-3 py-2 font-label text-xs font-semibold transition-colors sm:px-4 ${
                value.preset === option.id
                  ? "bg-surface text-primary shadow-card"
                  : "text-on-surface-muted hover:text-on-surface"
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
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
