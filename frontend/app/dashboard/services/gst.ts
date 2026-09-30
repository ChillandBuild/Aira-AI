export const GST_MIN = 0;
export const GST_MAX = 40;

/** GST in paise for a list price: round(amount * pct / 100). */
export function gstPaise(amountPaise: number, pct: number): number {
  if (!(amountPaise > 0) || !(pct > 0)) return 0;
  return Math.round((amountPaise * pct) / 100);
}

/** Total the customer is charged: list price plus GST. */
export function chargePaise(amountPaise: number, pct: number): number {
  return amountPaise + gstPaise(amountPaise, pct);
}

/** Parse the text box. Empty means 0 (no GST). Error text is set when out of range or not a number. */
export function parseGstPercent(text: string): { value: number; error: string | null } {
  const trimmed = text.trim();
  if (trimmed === "") return { value: 0, error: null };
  const value = Number(trimmed);
  if (!Number.isFinite(value) || value < GST_MIN || value > GST_MAX) {
    return { value: 0, error: `GST must be a number from ${GST_MIN} to ${GST_MAX}.` };
  }
  return { value, error: null };
}
