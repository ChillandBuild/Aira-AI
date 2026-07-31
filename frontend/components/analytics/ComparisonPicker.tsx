"use client";

import { ComparisonSelection } from "./periodSelection";
import { RangePicker } from "./RangePicker";

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
    <div className="flex flex-col gap-3">
      <p className="font-label text-xs font-semibold uppercase tracking-wider text-on-surface-muted">
        Compare with
      </p>
      <div className="flex w-max gap-1 rounded-xl bg-surface-low p-1 ring-1 ring-[#c4c7c7]/15">
        {([
          ["off", "Off"],
          ["previous", "Previous period"],
          ["custom", "Custom"],
        ] as const).map(([mode, label]) => (
          <button
            key={mode}
            type="button"
            aria-pressed={value.mode === mode}
            onClick={() => selectMode(mode)}
            className={`rounded-lg px-3 py-2 font-label text-xs font-semibold transition-colors sm:px-4 ${
              value.mode === mode
                ? "bg-surface text-primary shadow-card"
                : "text-on-surface-muted hover:text-on-surface"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {value.mode === "custom" && (
        <RangePicker
          value={{ preset: "custom", start: value.start, end: value.end }}
          onChange={({ start, end }) => onChange({ mode: "custom", start, end })}
          idPrefix="comparison-range"
        />
      )}
    </div>
  );
}
