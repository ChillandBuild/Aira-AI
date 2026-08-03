import { Preset, RangeValue } from "./RangePicker";

const VALID_PRESETS: Preset[] = ["today", "yesterday", "last_7d", "last_14d", "last_30d", "custom"];
const DEFAULT_PRESET: Preset = "last_7d";

export function rangeFromSearchParams(searchParams: URLSearchParams): RangeValue {
  const rawPreset = searchParams.get("period");
  const preset = VALID_PRESETS.includes(rawPreset as Preset) ? (rawPreset as Preset) : DEFAULT_PRESET;
  return {
    preset,
    start: searchParams.get("period_start") ?? "",
    end: searchParams.get("period_end") ?? "",
  };
}

export function rangeToSearchParams(current: URLSearchParams, next: RangeValue): URLSearchParams {
  const params = new URLSearchParams(current.toString());
  if (next.preset === DEFAULT_PRESET) params.delete("period");
  else params.set("period", next.preset);

  if (next.preset === "custom") {
    if (next.start) params.set("period_start", next.start);
    else params.delete("period_start");
    if (next.end) params.set("period_end", next.end);
    else params.delete("period_end");
  } else {
    params.delete("period_start");
    params.delete("period_end");
  }
  return params;
}
