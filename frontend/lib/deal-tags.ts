import type { DealStage } from "@/lib/api";

const DAY_MS = 24 * 60 * 60 * 1000;
const MIN_IDLE_DAYS_TO_SHOW = 2;
const OPEN_STAGES: ReadonlySet<DealStage> = new Set<DealStage>(["quoted", "awaiting_payment"]);

/** The board row fields the tags read. Every field but stage is optional: if the API
 *  doesn't send one, the tag that needs it simply doesn't show. */
export interface DealTagInput {
  stage: DealStage;
  payment_link?: string | null;
  link_expires_at?: string | null;
  last_activity_at?: string | null;
  refund_needed?: boolean | null;
}

export type DealTagTone = "muted" | "warning" | "danger";

export interface DealTag {
  key: "refund_needed" | "link_expired" | "idle";
  label: string;
  tone: DealTagTone;
}

function toTime(value: string | null | undefined): number | null {
  if (!value) return null;
  const time = new Date(value).getTime();
  return Number.isNaN(time) ? null : time;
}

/** Whole days since the timestamp (floored, never negative); null if missing or unparseable. */
export function idleDays(lastActivityAt: string | null | undefined, now: Date = new Date()): number | null {
  const time = toTime(lastActivityAt);
  if (time === null) return null;
  return Math.max(0, Math.floor((now.getTime() - time) / DAY_MS));
}

/** An awaiting_payment deal whose link is gone (null/empty) or whose expiry is strictly in the past. */
export function isLinkExpired(deal: DealTagInput, now: Date = new Date()): boolean {
  if (deal.stage !== "awaiting_payment") return false;
  if (deal.payment_link === null || deal.payment_link === "") return true;
  const expiresAt = toTime(deal.link_expires_at);
  return expiresAt !== null && expiresAt < now.getTime();
}

export function getDealTags(deal: DealTagInput, now: Date = new Date()): DealTag[] {
  const tags: DealTag[] = [];
  if (deal.refund_needed === true) {
    tags.push({ key: "refund_needed", label: "Refund needed", tone: "danger" });
  }
  if (isLinkExpired(deal, now)) {
    tags.push({ key: "link_expired", label: "Link expired", tone: "warning" });
  }
  const days = OPEN_STAGES.has(deal.stage) ? idleDays(deal.last_activity_at, now) : null;
  if (days !== null && days >= MIN_IDLE_DAYS_TO_SHOW) {
    tags.push({ key: "idle", label: `Idle ${days} days`, tone: "muted" });
  }
  return tags;
}
