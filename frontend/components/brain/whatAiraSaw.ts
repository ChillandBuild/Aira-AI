// Types and pure helpers for the operator "What Aira saw" drawer.
// Mirrors backend/app/services/brain/lead_context.py. It is a RECONSTRUCTION, never a record.

export interface SawMessage {
  direction: string | null;
  text: string;
  at: string | null;
  is_ai: boolean;
}

export interface SawGate {
  key: string;
  label: string;
  active: boolean;
  /** false: shown for context (opted out, escalated) but does not stop a reply. */
  blocks_reply: boolean;
  detail: string;
}

export interface SawOrder {
  deal_number: string | number | null;
  stage: string | null;
  total_paise: number | null;
  items: { name?: string; qty?: number }[];
}

export interface SawCall {
  at: string | null;
  outcome: string | null;
  manual_status: string | null;
  summary: string | null;
}

export interface WhatAiraSaw {
  reconstructed: true;
  generated_at: string;
  lead: { id: string; name: string | null; segment: string | null; score: number | null; channel: string };
  message_used: { text: string; note: string | null };
  recent_messages: SawMessage[];
  conversation_summary: string | null;
  campaign: { id: string | null; name: string } | null;
  deal_state: { selling_enabled: boolean; session: { status: string | null; collected_data: Record<string, unknown>; created_at: string | null } | null };
  orders: SawOrder[];
  call_summaries: SawCall[];
  gates: SawGate[];
  would_reply: boolean;
  knowledge: { text: string | null; note: string | null };
  system_prompt: string | null;
  reply_language_mode: string | null;
  intake_active: boolean | null;
  prompt_error: string | null;
}

export const RECONSTRUCTION_BANNER =
  "Reconstruction: what Anril would see if this lead messaged now — not a record of past replies";

export const RETRIEVAL_COST_NOTE = "Runs one knowledge search, which costs one embedding call.";

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null;
}

/** Cheap shape check on the fields the drawer reads without a guard. */
export function isWhatAiraSaw(v: unknown): v is WhatAiraSaw {
  if (!isRecord(v)) return false;
  return (
    v.reconstructed === true &&
    typeof v.generated_at === "string" &&
    isRecord(v.lead) &&
    isRecord(v.message_used) &&
    isRecord(v.knowledge) &&
    isRecord(v.deal_state) &&
    typeof v.would_reply === "boolean" &&
    Array.isArray(v.recent_messages) &&
    Array.isArray(v.gates) &&
    Array.isArray(v.orders) &&
    Array.isArray(v.call_summaries)
  );
}

/** Gates that are on right now and would stop a reply. */
export function blockingGates(gates: readonly SawGate[]): SawGate[] {
  return gates.filter((g) => g.active && g.blocks_reply);
}

/** Active gates that do not stop a reply but change it (opted out, escalated). */
export function noticeGates(gates: readonly SawGate[]): SawGate[] {
  return gates.filter((g) => g.active && !g.blocks_reply);
}

/** One line for the verdict: what would happen to a new message. */
export function verdictLine(saw: Pick<WhatAiraSaw, "would_reply" | "gates">): string {
  if (saw.would_reply) return "Anril would reply to a new message.";
  const reasons = blockingGates(saw.gates).map((g) => g.label.toLowerCase());
  return reasons.length ? `Anril would not reply: ${reasons.join("; ")}.` : "Anril would not reply.";
}

/** Rupees with grouping from paise; "—" when unknown. */
export function paiseToRupees(paise: number | null): string {
  if (paise === null || !Number.isFinite(paise)) return "—";
  return `₹${(paise / 100).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
}
