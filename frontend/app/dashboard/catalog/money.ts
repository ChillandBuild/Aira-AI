import type { StockMovement } from "@/lib/api";

/** Formats paise as a whole-rupee string with the ₹ sign, e.g. 320000 -> "₹3,200". */
export function formatPaise(paise: number): string {
  return `₹${Math.round(paise / 100).toLocaleString("en-IN")}`;
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("en-IN", {
    day: "numeric",
    month: "short",
    hour: "numeric",
    minute: "2-digit",
  });
}

export const STOCK_REASON_LABEL: Record<StockMovement["reason"], string> = {
  sale: "Sold",
  restock: "Restocked",
  adjustment: "Corrected",
  return: "Returned",
};

export const GST_RATE_OPTIONS = [0, 5, 12, 18, 28] as const;

/** Available stock = tracked quantity minus what's held by open awaiting-payment deals. */
export function availableQuantity(stockQuantity: number, heldQuantity: number): number {
  return stockQuantity - heldQuantity;
}
