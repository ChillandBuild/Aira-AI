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
];

function istDate(): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}`;
}

function shiftDate(iso: string, days: number): string {
  const date = new Date(`${iso}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

function displayedRange(value: RangeValue): Pick<RangeValue, "start" | "end"> {
  if (value.preset === "custom") return value;
  const end = value.preset === "yesterday" ? shiftDate(istDate(), -1) : istDate();
  const days = value.preset === "last_30d" ? 30 : value.preset === "last_14d" ? 14 : value.preset === "last_7d" ? 7 : 1;
  return { start: shiftDate(end, -(days - 1)), end };
}

export function RangePicker({
  value,
  onChange,
  idPrefix = "range",
  compact = false,
}: {
  value: RangeValue;
  onChange: (v: RangeValue) => void;
  idPrefix?: string;
  compact?: boolean;
}) {
  const range = displayedRange(value);

  return (
    <div className="flex min-w-max items-center gap-2" role="group" aria-label="Reporting period">
      <div className="flex items-center gap-1">
        {PRESET_OPTIONS.map((option) => (
          <button
            key={option.id}
            type="button"
            onClick={() => onChange({ ...value, preset: option.id })}
            aria-pressed={value.preset === option.id}
            className={`h-10 rounded-xl border px-3 font-label text-xs font-semibold transition-all duration-150 focus:outline-none focus:ring-2 focus:ring-violet-200 ${
              value.preset === option.id
                ? "border-violet-600 bg-violet-600 text-white shadow-[0_4px_10px_rgba(109,40,217,0.2)]"
                : "border-[#e8e3db] bg-[#fcfbf9] text-[#78716c] hover:border-violet-200 hover:bg-violet-50/50 hover:text-violet-700"
            }`}
          >
            {option.label}
          </button>
        ))}
      </div>
      <span className="mx-1 h-6 w-px bg-[#e8e3db]" aria-hidden="true" />
      {!compact && <span className="font-label text-[10px] font-bold uppercase tracking-wider text-on-surface-muted">Date range</span>}
      <input
        id={`${idPrefix}-from`}
        type="date"
        aria-label="From date"
        value={range.start}
        max={range.end || undefined}
        onChange={(e) => onChange({ preset: "custom", start: e.target.value, end: range.end })}
        className={`h-10 rounded-xl border border-surface-mid bg-[#fcfbf9] px-2.5 font-body text-xs font-semibold text-on-surface transition-colors hover:border-violet-200 focus:outline-none focus:ring-2 focus:ring-violet-200 ${compact ? "w-[116px]" : "w-[142px]"}`}
      />
      <span className="font-label text-xs text-on-surface-muted">to</span>
      <input
        id={`${idPrefix}-to`}
        type="date"
        aria-label="To date"
        value={range.end}
        min={range.start || undefined}
        onChange={(e) => onChange({ preset: "custom", start: range.start, end: e.target.value })}
        className={`h-10 rounded-xl border border-surface-mid bg-[#fcfbf9] px-2.5 font-body text-xs font-semibold text-on-surface transition-colors hover:border-violet-200 focus:outline-none focus:ring-2 focus:ring-violet-200 ${compact ? "w-[116px]" : "w-[142px]"}`}
      />
    </div>
  );
}
