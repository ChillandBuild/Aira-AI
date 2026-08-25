/** Mirrors _parse_delays in backend/app/services/silence_nudge.py: up to three
 *  whole minutes, 1-1440, strictly increasing. Returns null when invalid so the
 *  UI can reject on save rather than let the backend silently fall back. */
export function parseSilenceDelays(raw: string): number[] | null {
  const MAX_RUNGS = 3;
  const parts = raw.split(",").map(s => s.trim()).filter(Boolean);
  if (parts.length === 0 || parts.length > MAX_RUNGS) return null;
  const nums: number[] = [];
  for (const part of parts) {
    if (!/^\d+$/.test(part)) return null;
    const n = parseInt(part, 10);
    if (n < 1 || n > 1440) return null;
    if (nums.length > 0 && n <= nums[nums.length - 1]) return null;
    nums.push(n);
  }
  return nums;
}
