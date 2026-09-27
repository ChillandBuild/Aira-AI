/** The wrap-up form's state and rules, kept pure so they are unit-tested and mirror the server. */
import type { CallConnect, CallResult, OutcomeReason, PreferredLanguage, WrapupContext, WrapupPayload } from "@/lib/api";
import { resultOption } from "@/lib/call-wrapup";

export interface SaleLine {
  catalogItemId: string;
  name: string;
  qty: number;
  pricePaise: number | null;
}

export interface WrapupDraft {
  manualStatus: CallConnect | null;
  outcome: CallResult | null;
  notes: string;
  nextActionAt: string | null;
  reason: OutcomeReason | null;
  preferredLanguage: PreferredLanguage | null;
  stopMessages: boolean;
  saleMode: "products" | "amount";
  products: SaleLine[];
  amountRupees: string;
}

const PAST_TOLERANCE_MS = 5 * 60_000;

export function emptyDraft(): WrapupDraft {
  return {
    manualStatus: null, outcome: null, notes: "", nextActionAt: null, reason: null, preferredLanguage: null,
    stopMessages: false, saleMode: "products", products: [], amountRupees: "",
  };
}

export function selectConnect(draft: WrapupDraft, value: CallConnect, context: WrapupContext | null): WrapupDraft {
  if (value === "connected") return { ...draft, manualStatus: value, nextActionAt: null };
  return {
    ...draft, manualStatus: value, outcome: null, reason: null, preferredLanguage: null, stopMessages: false,
    nextActionAt: context?.retry_suggestions[value] ?? null,
  };
}

export function selectOutcome(draft: WrapupDraft, value: CallResult): WrapupDraft {
  return {
    ...draft, outcome: value, reason: null, preferredLanguage: null, stopMessages: false,
    nextActionAt: resultOption(value).time ? draft.nextActionAt : null,
  };
}

/** The cloud pre-fill and retry suggestion arrive after the form opens; never override a choice. */
export function applyContext(draft: WrapupDraft, context: WrapupContext): WrapupDraft {
  if (!draft.manualStatus) {
    return context.connect_prefill ? selectConnect(draft, context.connect_prefill, context) : draft;
  }
  if (draft.manualStatus !== "connected" && !draft.nextActionAt) {
    return { ...draft, nextActionAt: context.retry_suggestions[draft.manualStatus] };
  }
  return draft;
}

export function amountPaise(rupees: string): number | null {
  const value = Number(rupees.replace(/,/g, "").trim());
  return Number.isFinite(value) && value >= 1 ? Math.round(value * 100) : null;
}

function futureError(iso: string, now: Date): string | null {
  return new Date(iso).getTime() < now.getTime() - PAST_TOLERANCE_MS ? "Pick a time in the future." : null;
}

export function draftError(draft: WrapupDraft, now: Date): string | null {
  if (!draft.manualStatus) return "Pick whether the call connected.";
  if (draft.manualStatus !== "connected") {
    return draft.nextActionAt ? futureError(draft.nextActionAt, now) : "Pick when to try again.";
  }
  if (!draft.outcome) return "Pick what happened on the call.";
  const option = resultOption(draft.outcome);
  if (option.time === "required" && !draft.nextActionAt) return "Pick a date and time.";
  if (option.time && draft.nextActionAt) {
    const past = futureError(draft.nextActionAt, now);
    if (past) return past;
  }
  if (draft.outcome === "not_interested" && !draft.reason) return "Pick why they're not interested.";
  if (draft.outcome === "disqualified" && !draft.reason) return "Pick why the lead is disqualified.";
  if (draft.outcome === "language_barrier" && !draft.preferredLanguage) return "Pick the language the customer speaks.";
  if (draft.outcome === "converted") {
    if (draft.saleMode === "products" && draft.products.length === 0) return "Add the products sold.";
    if (draft.saleMode === "amount" && amountPaise(draft.amountRupees) === null) return "Enter the sale amount.";
  }
  if (option.notes && !draft.notes.trim()) return "Add a short note for this result.";
  return null;
}

export function draftToPayload(draft: WrapupDraft): WrapupPayload {
  const connected = draft.manualStatus === "connected";
  const sale = connected && draft.outcome === "converted";
  return {
    manual_status: draft.manualStatus as CallConnect,
    outcome: connected ? draft.outcome : null,
    notes: draft.notes.trim() || null,
    next_action_at: draft.nextActionAt,
    reason: draft.reason,
    preferred_language: draft.preferredLanguage,
    stop_messages: connected && draft.outcome === "do_not_call" && draft.stopMessages,
    products: sale && draft.saleMode === "products"
      ? draft.products.map((p) => ({ catalog_item_id: p.catalogItemId, qty: p.qty }))
      : [],
    amount_paise: sale && draft.saleMode === "amount" ? amountPaise(draft.amountRupees) : null,
  };
}
