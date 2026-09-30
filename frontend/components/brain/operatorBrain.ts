// Types and pure helpers for the operator console's Aira Brain tab and the clients-list
// "Waiting approvals" column. Mirrors backend/app/services/operator_brain*.py.
import type { BrainResponse } from "./types";

/** Keep in step with STUCK_APPROVAL_DAYS in services/operator_brain_fleet.py. */
export const STUCK_APPROVAL_DAYS = 7;

const DAY_MS = 24 * 60 * 60 * 1000;

export type OperatorRowState = "ok" | "missing" | "off" | "attention";

export interface OperatorRow {
  key: string;
  label: string;
  state: OperatorRowState;
  detail: string;
  /** The existing page that edits it. */
  href: string;
  /** "config" when that page is the client console's Config view (switched in place). */
  section: string | null;
}

export interface HistoryEntry {
  id: string;
  at: string;
  label: string;
  target: string | null;
  kind: "description" | "facts";
  by_user_id: string | null;
}

export interface OperatorHistory {
  entries: HistoryEntry[];
  dismissed_conflicts: number;
}

export interface FallbackSignals {
  count: number;
  window_days: number;
  escalation_enabled: boolean;
  triggers: Record<string, boolean>;
  /** "Counts only when inbox escalation is on" (or the partial-coverage variant); null when fully on. */
  note: string | null;
}

export interface OperatorBrainResponse extends BrainResponse {
  tenant: { id: string; name: string | null };
  operator_rows: OperatorRow[];
  history: OperatorHistory;
  fallback_signals: FallbackSignals;
}

export interface FleetWaitingRow {
  tenant_id: string;
  waiting_count: number;
  pending_reviews: number;
  oldest_review_days: number | null;
  oldest_review_at: string | null;
}

export interface FleetAlert {
  id: string;
  severity: "critical" | "warning" | "info";
  title: string;
  detail: string;
  tenant_id: string | null;
  tenant_name: string | null;
  source: string;
  created_at: string;
  href: string | null;
}

export interface FleetWaitingResponse {
  data: FleetWaitingRow[];
  alerts: FleetAlert[];
  stuck_after_days: number;
}

/** Whole days since iso (never negative). Unparseable input counts as 0. */
export function daysWaited(iso: string, nowMs: number = Date.now()): number {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return 0;
  return Math.max(Math.floor((nowMs - then) / DAY_MS), 0);
}

/** "today", "1 day", "9 days". */
export function waitedLabel(days: number): string {
  if (days <= 0) return "today";
  return days === 1 ? "1 day" : `${days} days`;
}

/** Stuck means waiting longer than STUCK_APPROVAL_DAYS: exactly 7 days is not stuck yet. */
export function isStuckApproval(iso: string, nowMs: number = Date.now()): boolean {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return false;
  return nowMs - then > STUCK_APPROVAL_DAYS * DAY_MS;
}

/** tenant_id -> row. A tenant missing from the map has nothing waiting. */
export function fleetWaitingByTenant(rows: readonly FleetWaitingRow[]): Map<string, FleetWaitingRow> {
  return new Map(rows.map((row) => [row.tenant_id, row]));
}

/** Text for the clients-list column: "None", "3", or "3 (oldest 9 days)". */
export function waitingColumnText(row: FleetWaitingRow | undefined): string {
  if (!row || row.waiting_count === 0) return "None";
  if (row.oldest_review_days === null) return String(row.waiting_count);
  return `${row.waiting_count} (oldest ${waitedLabel(row.oldest_review_days)})`;
}

export function isOperatorBrainResponse(body: unknown): body is OperatorBrainResponse {
  if (typeof body !== "object" || body === null) return false;
  const b = body as Record<string, unknown>;
  return (
    typeof b.headline === "object" && b.headline !== null &&
    typeof b.waiting === "object" && b.waiting !== null &&
    Array.isArray(b.inputs) &&
    Array.isArray(b.handovers) &&
    typeof b.status === "object" && b.status !== null &&
    Array.isArray(b.operator_rows) &&
    typeof b.history === "object" && b.history !== null &&
    typeof b.fallback_signals === "object" && b.fallback_signals !== null
  );
}
