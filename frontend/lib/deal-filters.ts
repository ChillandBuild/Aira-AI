import { DealFilters, DealSort, DealSource, DealAttention, PaymentMethod } from "@/lib/api";

export const SOURCE_LABEL: Record<DealSource, string> = {
  whatsapp: "WhatsApp",
  form: "Form",
  call: "Call",
  walk_in: "Walk-in",
  manual: "Manual",
  indiamart: "IndiaMART",
  justdial: "JustDial",
};

export const PAYMENT_LABEL: Record<PaymentMethod, string> = {
  razorpay: "Razorpay",
  cash: "Cash",
  upi: "UPI",
  card: "Card",
  bank_transfer: "Bank transfer",
  other: "Other",
};

export const ATTENTION_LABEL: Record<DealAttention, string> = {
  unpaid_3d: "Unpaid 3+ days",
  link_expiring: "Payment link expiring",
  refund: "Refund needed",
};

/** Format paise as ₹1.2k / ₹4.5L / ₹1.1Cr style. */
export function shortRupees(paise: number): string {
  const rupees = Math.round(paise / 100);
  if (rupees >= 10000000) {
    return `₹${(rupees / 10000000).toFixed(1).replace(/\.0$/, "")}Cr`;
  }
  if (rupees >= 100000) {
    return `₹${(rupees / 100000).toFixed(1).replace(/\.0$/, "")}L`;
  }
  if (rupees >= 1000) {
    return `₹${(rupees / 1000).toFixed(1).replace(/\.0$/, "")}k`;
  }
  return `₹${rupees}`;
}

/** A non-negative whole number from the URL, or undefined for anything else ("abc", "-5"). */
function wholeNumber(raw: string | null): number | undefined {
  const n = raw ? Number(raw) : NaN;
  return Number.isInteger(n) && n >= 0 ? n : undefined;
}

export function filtersFromParams(params: URLSearchParams): DealFilters & {
  sort?: DealSort;
  dir?: "asc" | "desc";
  page?: number;
  view?: "table" | "board";
} {
  const stage = params.get("stage");
  const q = params.get("q");
  const source = params.get("source");
  const from = params.get("from");
  const to = params.get("to");
  const min = params.get("min");
  const max = params.get("max");
  const pay = params.get("pay");
  const product = params.get("product");
  const attention = params.get("attention");
  const sort = params.get("sort");
  const dir = params.get("dir");
  const page = params.get("page");
  const view = params.get("view");

  return {
    stage: (stage as "" | "quoted" | "awaiting_payment" | "won" | "lost") || undefined,
    q: q || undefined,
    source: source ? (source.split(",") as DealSource[]) : undefined,
    created_from: from || undefined,
    created_to: to || undefined,
    min_rupees: wholeNumber(min),
    max_rupees: wholeNumber(max),
    payment_method: pay ? (pay.split(",") as PaymentMethod[]) : undefined,
    product: product ? product.split(",") : undefined,
    attention: attention ? (attention.split(",") as DealAttention[]) : undefined,
    sort: (sort as DealSort) || undefined,
    dir: (dir as "asc" | "desc") || undefined,
    page: wholeNumber(page),
    view: (view as "table" | "board") || undefined,
  };
}

export function filtersToParams(
  filters: DealFilters & { sort?: DealSort; dir?: "asc" | "desc"; page?: number; view?: "table" | "board" },
  base: URLSearchParams = new URLSearchParams()
): URLSearchParams {
  const params = new URLSearchParams(base);

  if (filters.stage) params.set("stage", filters.stage);
  else params.delete("stage");

  if (filters.q) params.set("q", filters.q);
  else params.delete("q");

  if (filters.source && filters.source.length > 0) params.set("source", filters.source.join(","));
  else params.delete("source");

  if (filters.created_from) params.set("from", filters.created_from);
  else params.delete("from");

  if (filters.created_to) params.set("to", filters.created_to);
  else params.delete("to");

  if (filters.min_rupees != null) params.set("min", String(filters.min_rupees));
  else params.delete("min");

  if (filters.max_rupees != null) params.set("max", String(filters.max_rupees));
  else params.delete("max");

  if (filters.payment_method && filters.payment_method.length > 0) params.set("pay", filters.payment_method.join(","));
  else params.delete("pay");

  if (filters.product && filters.product.length > 0) params.set("product", filters.product.join(","));
  else params.delete("product");

  if (filters.attention && filters.attention.length > 0) params.set("attention", filters.attention.join(","));
  else params.delete("attention");

  if (filters.sort) params.set("sort", filters.sort);
  else params.delete("sort");

  if (filters.dir) params.set("dir", filters.dir);
  else params.delete("dir");

  if (filters.page) params.set("page", String(filters.page));
  else params.delete("page");

  if (filters.view) params.set("view", filters.view);
  else params.delete("view");

  return params;
}
