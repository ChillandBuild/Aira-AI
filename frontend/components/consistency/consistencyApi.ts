import { API_URL, getAuthHeaders } from "@/lib/api";
import {
  MAX_BATCH_IDS,
  chunkIds,
  mergeDismissResults,
  mergeFixResults,
  parseDismissResult,
  parseFixResult,
  parseRestoreResult,
} from "./consistencyLogic";
import type { DismissBatchResult, FixBatchResult, Report, RestoreBatchResult } from "./types";

const BASE = `${API_URL}/api/v1/consistency`;
const STALE_STATUS = 409;

type BatchPartial = FixBatchResult | DismissBatchResult;

/** A bulk request failed. `partial` is what earlier chunks of the same click already did (empty for a single chunk). */
export class BatchError extends Error {
  readonly partial: BatchPartial | null;

  constructor(message: string, partial: BatchPartial | null = null) {
    super(message);
    this.name = "BatchError";
    this.partial = partial;
  }
}

/** The report changed under the user (another tab, or a re-check); the panel must reload. */
export class StaleReportError extends BatchError {
  constructor(partial: BatchPartial | null = null) {
    super("Issues changed since Aira checked. Reload to see the current list.", partial);
    this.name = "StaleReportError";
  }
}

async function detailOrDefault(res: Response, fallback: string): Promise<string> {
  const body = await res.json().catch(() => null);
  return typeof body?.detail === "string" ? body.detail : fallback;
}

function normalizeReport(raw: Partial<Report>): Report {
  return {
    issues: raw.issues ?? [],
    checked_at: raw.checked_at ?? null,
    stale: Boolean(raw.stale),
    suggestions_complete: raw.suggestions_complete,
    dismissed_issues: raw.dismissed_issues ?? [],
  };
}

export async function getReport(): Promise<Report> {
  const auth = await getAuthHeaders();
  const res = await fetch(BASE, { headers: auth });
  if (!res.ok) throw new Error("Couldn't load. Please try again.");
  return normalizeReport(await res.json());
}

/** Needs knowledge.manage; the panel never calls this without it. */
export async function checkNow(): Promise<Report> {
  const auth = await getAuthHeaders();
  const res = await fetch(`${BASE}/check`, { method: "POST", headers: auth });
  if (!res.ok) throw new Error("Couldn't check right now. Please try again.");
  return normalizeReport(await res.json());
}

export async function fixIssue(id: string, text?: string): Promise<void> {
  const auth = await getAuthHeaders();
  const res = await fetch(`${BASE}/issues/${id}/fix`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...auth },
    body: JSON.stringify({ text }),
  });
  if (!res.ok) throw new Error(await detailOrDefault(res, "Couldn't apply this fix. Please try again."));
}

export async function dismissIssue(id: string): Promise<void> {
  const auth = await getAuthHeaders();
  const res = await fetch(`${BASE}/issues/${id}/dismiss`, { method: "POST", headers: auth });
  if (!res.ok) throw new Error(await detailOrDefault(res, "Couldn't dismiss this. Please try again."));
}

async function postBatch(path: string, body: Record<string, unknown>, fallback: string): Promise<unknown> {
  const auth = await getAuthHeaders();
  const res = await fetch(`${BASE}/${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...auth },
    body: JSON.stringify(body),
  });
  if (res.status === STALE_STATUS) throw new StaleReportError();
  if (!res.ok) throw new Error(await detailOrDefault(res, fallback));
  return res.json();
}

/**
 * Runs the same batch over chunks of MAX_BATCH_IDS, in order, with the same
 * checked_at. A stale report part-way through keeps what earlier chunks did.
 */
async function runChunked<T>(
  ids: readonly string[],
  send: (chunk: string[]) => Promise<T>,
  merge: (a: T, b: T) => T,
  empty: T,
): Promise<T> {
  let total = empty;
  for (const chunk of chunkIds(ids, MAX_BATCH_IDS)) {
    try {
      total = merge(total, await send(chunk));
    } catch (e) {
      if (e instanceof StaleReportError) throw new StaleReportError(total as BatchPartial);
      if (e instanceof Error) throw new BatchError(e.message, total as BatchPartial);
      throw e;
    }
  }
  return total;
}

export function fixBatch(ids: readonly string[], checkedAt: string): Promise<FixBatchResult> {
  return runChunked(
    ids,
    async (chunk) =>
      parseFixResult(await postBatch("fix-batch", { issue_ids: chunk, checked_at: checkedAt }, "Couldn't apply these fixes. Please try again.")),
    mergeFixResults,
    { applied: [], skipped: [], failed: [] },
  );
}

export function dismissBatch(ids: readonly string[], checkedAt: string): Promise<DismissBatchResult> {
  return runChunked(
    ids,
    async (chunk) =>
      parseDismissResult(await postBatch("dismiss-batch", { issue_ids: chunk, checked_at: checkedAt }, "Couldn't dismiss these. Please try again.")),
    mergeDismissResults,
    { dismissed: [], skipped: [] },
  );
}

export async function restoreIssues(ids: readonly string[]): Promise<RestoreBatchResult> {
  return parseRestoreResult(await postBatch("restore", { issue_ids: ids }, "Couldn't restore this. Please try again."));
}
