/** All deal money is stored in paise (int). Round to whole rupees for display. */
export function formatRupees(paise: number | null | undefined): string {
  const value = Math.round((paise ?? 0) / 100);
  return `₹${value.toLocaleString("en-IN")}`;
}
