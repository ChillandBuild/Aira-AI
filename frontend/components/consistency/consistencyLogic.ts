// Pure rules behind the conflicts panel: who may do what and why not, the source
// label on each row, selection, batching, parsing the bulk responses and the
// sentences that report them. No React, no fetch; covered by consistencyLogic.test.ts.

import type {
  Access,
  BatchNote,
  BulkAction,
  DismissBatchResult,
  DismissedIssue,
  FixBatchResult,
  Issue,
  RestoreBatchResult,
} from "./types";

export const NEEDS_MANAGE = "Needs manage access";
export const OWNER_ONLY = "Owner only";

/** The server accepts 1..100 ids per bulk request. */
export const MAX_BATCH_IDS = 100;

// ─── Source label and role rules ─────────────────────────────────────────────

function descriptionLabel(sectionLabel: string | null | undefined): string {
  return sectionLabel ? `Description > ${sectionLabel}` : "Description";
}

/** "Description > <section>", plain "Description" without a section, or "Knowledge > <file>". */
export function sourceLabel(issue: Pick<Issue, "where" | "document_name" | "section_label">): string {
  if (issue.where === "knowledge") return `Knowledge > ${issue.document_name ?? "a document"}`;
  return descriptionLabel(issue.section_label);
}

export function dismissedSourceLabel(issue: Pick<DismissedIssue, "where" | "document_name" | "section_label">): string {
  return sourceLabel(issue);
}

/** Why Fix is unavailable, or null. "Needs manage access" wins over "Owner only". */
export function fixBlockedReason(issue: Pick<Issue, "where">, access: Access): string | null {
  if (!access.canManage) return NEEDS_MANAGE;
  if (issue.where === "description" && !access.isOwner) return OWNER_ONLY;
  return null;
}

/** Dismiss, Restore and both bulk buttons need only manage access. */
export function manageBlockedReason(access: Access): string | null {
  return access.canManage ? null : NEEDS_MANAGE;
}

export function bulkBlockedReason(access: Access): string | null {
  return manageBlockedReason(access);
}

/** For the confirm sheet: what the server will skip for this item, so the user is told up front. */
export function predictedSkip(issue: Issue, action: BulkAction, access: Access): string | null {
  if (action === "dismiss") return null;
  if (issue.where === "description" && !access.isOwner) return "Owner only, will be skipped";
  if (issue.where === "knowledge" && !issue.editable) return "File not sorted yet, will be skipped";
  if (issue.proposed === null) return "No suggested wording, will be skipped";
  return null;
}

// ─── Selection ───────────────────────────────────────────────────────────────

export function toggleId(selected: ReadonlySet<string>, id: string): Set<string> {
  const next = new Set(selected);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  return next;
}

/** What a bulk button acts on: the ticked rows, or every row when none are ticked. */
export function bulkTargets(issues: readonly Issue[], selected: ReadonlySet<string>): Issue[] {
  if (selected.size === 0) return [...issues];
  return issues.filter((issue) => selected.has(issue.id));
}

export function bulkLabel(action: BulkAction, total: number, selectedCount: number): string {
  const verb = action === "fix" ? "Fix" : "Dismiss";
  return selectedCount > 0 ? `${verb} selected (${selectedCount})` : `${verb} all (${total})`;
}

export function chunkIds(ids: readonly string[], size: number = MAX_BATCH_IDS): string[][] {
  const chunks: string[][] = [];
  for (let start = 0; start < ids.length; start += size) chunks.push(ids.slice(start, start + size));
  return chunks;
}

// ─── Parsing the bulk responses ──────────────────────────────────────────────

function asRecord(raw: unknown): Record<string, unknown> {
  return typeof raw === "object" && raw !== null ? (raw as Record<string, unknown>) : {};
}

function stringList(raw: unknown): string[] {
  return Array.isArray(raw) ? raw.filter((v): v is string => typeof v === "string") : [];
}

function noteList(raw: unknown): BatchNote[] {
  if (!Array.isArray(raw)) return [];
  return raw.flatMap((entry): BatchNote[] => {
    const note = asRecord(entry);
    if (typeof note.id !== "string" || typeof note.reason !== "string") return [];
    return [typeof note.code === "string" ? { id: note.id, reason: note.reason, code: note.code } : { id: note.id, reason: note.reason }];
  });
}

export function parseFixResult(raw: unknown): FixBatchResult {
  const body = asRecord(raw);
  return { applied: stringList(body.applied), skipped: noteList(body.skipped), failed: noteList(body.failed) };
}

export function parseDismissResult(raw: unknown): DismissBatchResult {
  const body = asRecord(raw);
  return { dismissed: stringList(body.dismissed), skipped: noteList(body.skipped) };
}

export function parseRestoreResult(raw: unknown): RestoreBatchResult {
  const body = asRecord(raw);
  return { restored: stringList(body.restored), skipped: noteList(body.skipped) };
}

export function mergeFixResults(a: FixBatchResult, b: FixBatchResult): FixBatchResult {
  return { applied: [...a.applied, ...b.applied], skipped: [...a.skipped, ...b.skipped], failed: [...a.failed, ...b.failed] };
}

export function mergeDismissResults(a: DismissBatchResult, b: DismissBatchResult): DismissBatchResult {
  return { dismissed: [...a.dismissed, ...b.dismissed], skipped: [...a.skipped, ...b.skipped] };
}

// ─── Result sentences: nothing is silent ─────────────────────────────────────

const SKIP_CODE_LABEL: Record<string, string> = {
  owner_only: "owner only",
  no_proposal: "no suggested wording",
  not_editable: "file not sorted yet",
  not_found: "no longer listed",
  not_dismissed: "not dismissed",
};

const MAX_FAILURE_REASONS = 3;

/** "The quoted text changed." -> "the quoted text changed". */
function plainReason(reason: string): string {
  const trimmed = reason.trim().replace(/\.+$/, "");
  // Only a plain leading word ("The", "Owner"): "Rs 49", "UPI" and "WhatsApp" stay as written.
  if (/^[A-Z][a-z]{2,}(\s|$)/.test(trimmed)) return trimmed.charAt(0).toLowerCase() + trimmed.slice(1);
  return trimmed;
}

function skipLabel(note: BatchNote): string {
  return (note.code && SKIP_CODE_LABEL[note.code]) || plainReason(note.reason);
}

function skippedSentence(skipped: readonly BatchNote[]): string {
  if (skipped.length === 0) return "";
  const counts = new Map<string, number>();
  for (const note of skipped) {
    const label = skipLabel(note);
    counts.set(label, (counts.get(label) ?? 0) + 1);
  }
  const groups = Array.from(counts.entries());
  const inner = groups.length === 1 ? groups[0][0] : groups.map(([label, n]) => `${n} ${label}`).join(", ");
  return ` Skipped ${skipped.length} (${inner}).`;
}

function failedSentence(failed: readonly BatchNote[]): string {
  if (failed.length === 0) return "";
  const distinct = Array.from(new Set(failed.map((note) => plainReason(note.reason))));
  const shown = distinct.slice(0, MAX_FAILURE_REASONS).join("; ");
  const more = distinct.length - MAX_FAILURE_REASONS;
  return ` ${failed.length} failed: ${shown}${more > 0 ? ` and ${more} more` : ""}.`;
}

export function summarizeFix(result: FixBatchResult): string {
  const head = result.applied.length > 0 ? `Fixed ${result.applied.length}.` : "Nothing was fixed.";
  return `${head}${skippedSentence(result.skipped)}${failedSentence(result.failed)}`;
}

export function summarizeDismiss(result: DismissBatchResult): string {
  const head = result.dismissed.length > 0 ? `Dismissed ${result.dismissed.length}.` : "Nothing was dismissed.";
  return `${head}${skippedSentence(result.skipped)}`;
}

export function summarizeRestore(result: RestoreBatchResult): string {
  const head = result.restored.length > 0 ? `Restored ${result.restored.length}.` : "Nothing was restored.";
  return `${head}${skippedSentence(result.skipped)}`;
}
