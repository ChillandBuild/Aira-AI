// Pure logic behind the Aira Brain hub and its sidebar badge. No React, no fetch,
// so every rule here is covered by brainLogic.test.ts.

import type { BrainCount, BrainHandover, BrainHeadline, BrainWaiting } from "./types";

// ─── Sidebar poll: what a poll result does to the badge ──────────────────────

export interface CountState {
  /** Sequence number of the newest request whose result was applied. */
  appliedSeq: number;
  /** null = show no badge (before the first success, or after a 403/404). */
  value: BrainCount | null;
}

export type PollResult =
  | { seq: number; ok: true; data: unknown }
  | { seq: number; ok: false; status?: number };

export const INITIAL_COUNT_STATE: CountState = { appliedSeq: 0, value: null };

/** Statuses that mean "you may not, or cannot, see this": the badge goes away. */
const CLEARING_STATUSES: ReadonlySet<number> = new Set([403, 404]);

/** Accepts only a well-formed count body; anything else is treated as a failed poll. */
export function parseBrainCount(raw: unknown): BrainCount | null {
  if (typeof raw !== "object" || raw === null) return null;
  const body = raw as Record<string, unknown>;
  const { count, sort_count, consistency_count } = body;
  if (typeof count !== "number" || !Number.isFinite(count) || count < 0) return null;
  return {
    count,
    sort_count: typeof sort_count === "number" ? sort_count : 0,
    consistency_count: typeof consistency_count === "number" ? consistency_count : 0,
  };
}

/**
 * The poll rule (blueprint section 12): keep the last value when a poll fails,
 * clear it on a 403 or 404, and show nothing before the first success. A result
 * from an older request never overwrites a newer one.
 */
export function nextCountState(prev: CountState, result: PollResult): CountState {
  if (result.seq < prev.appliedSeq) return prev;
  if (result.ok) {
    const value = parseBrainCount(result.data);
    return value ? { appliedSeq: result.seq, value } : prev;
  }
  if (result.status !== undefined && CLEARING_STATUSES.has(result.status)) {
    return { appliedSeq: result.seq, value: null };
  }
  return prev;
}

/** The number to draw on a badge, or null for no badge. */
export function badgeCount(state: CountState): number | null {
  const count = state.value?.count ?? 0;
  return count > 0 ? count : null;
}

// ─── Hub page: latest response wins ──────────────────────────────────────────

export interface LatestState<T> {
  appliedSeq: number;
  data: T | null;
  /** Set only while there is no data to show. */
  error: string | null;
}

export type LatestAction<T> =
  | { type: "success"; seq: number; data: T }
  | { type: "failure"; seq: number; message: string };

export function initialLatestState<T>(): LatestState<T> {
  return { appliedSeq: 0, data: null, error: null };
}

/**
 * The hub loads /brain right after an approval and again ~8 seconds later. Requests
 * are numbered in the order they start; a response is applied unless a newer
 * request has already been applied, so the later answer decides the empty state.
 * A failed refresh never wipes good data: it only surfaces when there is none.
 */
export function reduceLatest<T>(state: LatestState<T>, action: LatestAction<T>): LatestState<T> {
  if (action.type === "success") {
    if (action.seq < state.appliedSeq) return state;
    return { appliedSeq: action.seq, data: action.data, error: null };
  }
  if (action.seq < state.appliedSeq || state.data !== null) return state;
  return { ...state, error: action.message };
}

// ─── Conflicts panel: who may trigger its automatic check ────────────────────

/**
 * The conflicts panel checks itself on load (POST /consistency/check), which the
 * server allows only with knowledge.manage. So the hub mounts it for managers
 * only; everyone else gets the read-only count line.
 */
export function canAutoCheckPanel(role: string | null, permissions: readonly string[]): boolean {
  return role === "owner" || permissions.includes("knowledge.manage");
}

// ─── Copy ────────────────────────────────────────────────────────────────────

function plural(n: number, one: string, many: string): string {
  return n === 1 ? one : many;
}

function windowPhrase(days: number): string {
  if (days === 7) return "This week";
  return `In the last ${days} ${plural(days, "day", "days")}`;
}

/** "This week: Aira handled 71 of 84 chats. 6 reached a human: 5 asked for a person, 1 was a gap in what Aira knows." */
export function headlineSentence(h: BrainHeadline): string {
  const lead = windowPhrase(h.window_days);
  if (h.chats === 0) return `${lead}: no chats yet.`;
  const handled = `Aira handled ${h.handled_by_aira} of ${h.chats} ${plural(h.chats, "chat", "chats")}.`;
  if (h.handed_over === 0) return `${lead}: ${handled} Nobody needed a human.`;

  const parts: string[] = [];
  if (h.asked_for_human > 0) parts.push(`${h.asked_for_human} asked for a person`);
  if (h.knowledge_gaps > 0) {
    parts.push(`${h.knowledge_gaps} ${plural(h.knowledge_gaps, "was a gap", "were gaps")} in what Aira knows`);
  }
  const other = h.handed_over - h.asked_for_human - h.knowledge_gaps;
  if (other > 0) parts.push(`${other} for other reasons`);

  const reached = `${h.handed_over} reached a human${parts.length > 0 ? `: ${parts.join(", ")}` : ""}.`;
  return `${lead}: ${handled} ${reached}`;
}

/** "1 thing disagrees with Aira's setup, " / "3 things disagree with Aira's setup, ", followed by the link text. */
export function conflictsLinkText(count: number): string {
  return `${count} ${plural(count, "thing disagrees", "things disagree")} with Aira's setup —`;
}

export function topLineText(waitingCount: number): string {
  if (waitingCount <= 0) return "Aira is ready";
  return `${waitingCount} ${plural(waitingCount, "thing needs", "things need")} you`;
}

// ─── Top line: the one main action ───────────────────────────────────────────

export type MainAction =
  | { kind: "review"; label: string; reviewId: string }
  | { kind: "anchor"; label: string; anchor: string }
  | { kind: "link"; label: string; href: string };

export const ANCHOR_CONFLICTS = "brain-conflicts";
export const ANCHOR_FAILED = "brain-failed-files";
export const ANCHOR_TEMPLATES = "brain-templates";

/** Picks what the top line's button does: the first thing waiting, in priority order. */
export function pickMainAction(waiting: BrainWaiting): MainAction {
  const firstReview = waiting.sort_reviews[0];
  if (firstReview) {
    const n = waiting.sort_reviews.length;
    return { kind: "review", label: n === 1 ? "Review 1 sorted file" : `Review ${n} sorted files`, reviewId: firstReview.id };
  }
  if (waiting.consistency_count > 0) {
    return { kind: "anchor", label: "See what disagrees", anchor: ANCHOR_CONFLICTS };
  }
  if (waiting.failed_files.length > 0) {
    return { kind: "anchor", label: "Fix failed files", anchor: ANCHOR_FAILED };
  }
  if (waiting.rejected_templates.length > 0) {
    return { kind: "link", label: "Open templates", href: "/dashboard/templates" };
  }
  return { kind: "link", label: "Add to what Aira knows", href: "/dashboard/knowledge" };
}

// ─── Handover feed: which action a row offers ────────────────────────────────

export type HandoverAction =
  | { kind: "none" }
  | { kind: "add_answer" }
  | { kind: "open_chat"; leadId: string }
  | { kind: "no_inbox_access" };

/** Knowledge gaps always offer "Add an answer"; other rows link to the chat only when lead_id is present. */
export function handoverAction(handover: BrainHandover, readOnly: boolean): HandoverAction {
  if (readOnly) return { kind: "none" };
  if (handover.kind === "knowledge_gap") return { kind: "add_answer" };
  if (!handover.lead_id) return { kind: "no_inbox_access" };
  return { kind: "open_chat", leadId: handover.lead_id };
}
