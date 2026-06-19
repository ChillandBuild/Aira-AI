// Shared formatting + delta helpers for the Telecalling Performance view.

export function formatTalk(seconds: number | null | undefined): string {
  if (!seconds) return "0s";
  const total = Math.round(seconds);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

export function formatPct(rate: number | null | undefined): string {
  if (!rate) return "0%";
  return `${Math.round(rate * 100)}%`;
}

export function formatMinutes(min: number | null | undefined): string {
  if (!min) return "0 min";
  return `${Math.round(min)} min`;
}

export interface Delta {
  diff: number; // current − baseline (raw units)
  pct: number | null; // percentage change, null when baseline is 0
  direction: "up" | "down" | "flat";
  isGood: boolean; // colour hint, respects lowerIsBetter
}

// Compute a delta between a current value and a baseline.
// lowerIsBetter flips the good/bad colouring (e.g. idle minutes).
export function computeDelta(
  current: number,
  baseline: number | null | undefined,
  lowerIsBetter = false,
): Delta | null {
  if (baseline === null || baseline === undefined) return null;
  const diff = current - baseline;
  const direction: Delta["direction"] = diff > 0.0001 ? "up" : diff < -0.0001 ? "down" : "flat";
  const pct = baseline !== 0 ? (diff / Math.abs(baseline)) * 100 : null;
  const rising = direction === "up";
  const isGood = direction === "flat" ? true : lowerIsBetter ? !rising : rising;
  return { diff, pct, direction, isGood };
}

export function deltaColor(d: Delta | null): string {
  if (!d || d.direction === "flat") return "text-[#a8a29e]";
  return d.isGood ? "text-emerald-600" : "text-rose-600";
}

// A compact label like "+12% vs yesterday" / "−4 min".
export function deltaLabel(
  d: Delta | null,
  opts: { unit?: string; asPct?: boolean } = {},
): string {
  if (!d) return "";
  if (d.direction === "flat") return "no change";
  const arrow = d.direction === "up" ? "↑" : "↓";
  if (opts.asPct && d.pct !== null) {
    return `${arrow} ${Math.abs(Math.round(d.pct))}%`;
  }
  const mag = Math.abs(d.diff);
  const rounded = mag >= 10 ? Math.round(mag) : Math.round(mag * 10) / 10;
  return `${arrow} ${rounded}${opts.unit ? ` ${opts.unit}` : ""}`;
}
