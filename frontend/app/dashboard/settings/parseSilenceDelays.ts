/** Mirrors _parse_delays in backend/app/services/silence_nudge.py: up to three
 *  whole minutes, 1-1440. Each value is the gap after the previous message sent
 *  (the AI reply, then each earlier reminder), so order is free. A blank entry
 *  is invalid. Returns null when invalid so the UI can reject on save rather
 *  than let the backend silently fall back. */
export function parseSilenceDelays(raw: string): number[] | null {
  const MAX_RUNGS = 3;
  const parts = raw.split(",").map(s => s.trim());
  if (parts.length > MAX_RUNGS) return null;
  const nums: number[] = [];
  for (const part of parts) {
    if (!/^\d+$/.test(part)) return null;
    const n = parseInt(part, 10);
    if (n < 1 || n > 1440) return null;
    nums.push(n);
  }
  return nums;
}
