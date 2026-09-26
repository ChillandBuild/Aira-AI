"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle, Check, Loader2, Pencil, X } from "lucide-react";
import { API_URL, getAuthHeaders } from "@/lib/api";
import { timeAgo } from "@/lib/utils";

type IssueKind = "price" | "required_detail" | "handover" | "other";
type IssueWhere = "description" | "knowledge" | "handover_line";

interface Issue {
  id: string;
  kind: IssueKind;
  where: IssueWhere;
  document_name: string | null;
  editable: boolean;
  quote: string;
  topic: string;
  truth: string;
  proposed: string | null;
}

interface Report {
  issues: Issue[];
  checked_at: string | null;
  stale: boolean;
}

const BASE = `${API_URL}/api/v1/consistency`;

async function getReport(): Promise<Report> {
  const auth = await getAuthHeaders();
  const res = await fetch(BASE, { headers: auth });
  if (!res.ok) throw new Error("Couldn't load. Please try again.");
  return res.json();
}

async function checkNow(): Promise<Report> {
  const auth = await getAuthHeaders();
  const res = await fetch(`${BASE}/check`, { method: "POST", headers: auth });
  if (!res.ok) throw new Error("Couldn't check right now. Please try again.");
  return res.json();
}

async function detailOrDefault(res: Response, fallback: string): Promise<string> {
  const body = await res.json().catch(() => null);
  return typeof body?.detail === "string" ? body.detail : fallback;
}

async function fixIssue(id: string, text?: string): Promise<void> {
  const auth = await getAuthHeaders();
  const res = await fetch(`${BASE}/issues/${id}/fix`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...auth },
    body: JSON.stringify({ text }),
  });
  if (!res.ok) throw new Error(await detailOrDefault(res, "Couldn't apply this fix. Please try again."));
}

async function dismissIssue(id: string): Promise<void> {
  const auth = await getAuthHeaders();
  const res = await fetch(`${BASE}/issues/${id}/dismiss`, { method: "POST", headers: auth });
  if (!res.ok) throw new Error(await detailOrDefault(res, "Couldn't dismiss this. Please try again."));
}

const WHERE_LABEL: Record<IssueWhere, string> = {
  description: "Description",
  knowledge: "Knowledge",
  handover_line: "Handover line",
};

function locationLabel(issue: Issue): string {
  if (issue.where === "knowledge") return `Knowledge: ${issue.document_name ?? "a document"}`;
  return WHERE_LABEL[issue.where];
}

function IssueCard({
  issue,
  onFix,
  onDismiss,
}: {
  issue: Issue;
  onFix: (id: string, text?: string) => Promise<void>;
  onDismiss: (id: string) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(issue.proposed ?? issue.quote);
  const [busy, setBusy] = useState<"fix" | "dismiss" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run(action: "fix" | "dismiss", fn: () => Promise<void>) {
    setBusy(action);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong. Please try again.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="rounded-2xl border border-amber-200 bg-white p-4 space-y-2.5">
      <div className="flex items-center justify-between gap-2">
        <span className="font-label text-[10px] font-bold uppercase tracking-wider text-amber-700">
          {locationLabel(issue)}
        </span>
      </div>

      <p className="font-label text-sm font-semibold text-ink">{issue.topic}</p>

      <p className="font-body text-xs italic text-ink-muted">&ldquo;{issue.quote}&rdquo;</p>

      {issue.proposed !== null && (
        <p className="font-body text-xs text-ink-secondary">
          <span className="font-semibold text-ink">Suggested: </span>
          {issue.proposed === "" ? "remove this line" : issue.proposed}
        </p>
      )}

      {editing && (
        <div className="space-y-2 pt-1">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={2}
            className="w-full rounded-lg border border-border bg-white px-3 py-2 font-body text-sm text-ink outline-none focus:border-primary focus:ring-2 focus:ring-primary/15"
            aria-label={`Edit wording for ${issue.topic}`}
          />
          <div className="flex gap-2">
            <button
              type="button"
              disabled={busy !== null}
              onClick={() => run("fix", () => onFix(issue.id, draft))}
              className="inline-flex items-center gap-1.5 rounded-lg bg-ink px-3 py-1.5 font-label text-xs font-semibold text-white disabled:opacity-50"
            >
              {busy === "fix" ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}
              Apply
            </button>
            <button
              type="button"
              disabled={busy !== null}
              onClick={() => setEditing(false)}
              className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 font-label text-xs font-semibold text-ink-secondary disabled:opacity-50"
            >
              <X size={12} /> Cancel
            </button>
          </div>
        </div>
      )}

      {!editing && (
        <div className="flex flex-wrap items-center gap-2 pt-1">
          {issue.editable && issue.proposed !== null && (
            <button
              type="button"
              disabled={busy !== null}
              onClick={() => run("fix", () => onFix(issue.id, undefined))}
              className="inline-flex items-center gap-1.5 rounded-lg bg-ink px-3 py-1.5 font-label text-xs font-semibold text-white transition hover:bg-ink/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 disabled:opacity-50"
            >
              {busy === "fix" ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}
              Use suggestion
            </button>
          )}
          {issue.editable && (
            <button
              type="button"
              disabled={busy !== null}
              onClick={() => { setDraft(issue.proposed ?? issue.quote); setEditing(true); }}
              className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 font-label text-xs font-semibold text-ink-secondary transition hover:border-primary/40 hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 disabled:opacity-50"
            >
              <Pencil size={12} /> Edit & apply
            </button>
          )}
          <button
            type="button"
            disabled={busy !== null}
            onClick={() => run("dismiss", () => onDismiss(issue.id))}
            className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 font-label text-xs font-semibold text-ink-muted transition hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 disabled:opacity-50"
          >
            {busy === "dismiss" ? <Loader2 size={12} className="animate-spin" /> : <X size={12} />}
            Keep as is
          </button>
        </div>
      )}

      {!issue.editable && (
        <p className="font-body text-[11px] text-ink-muted">
          This file was uploaded before auto-sort. Re-sort it on the Knowledge page to fix it here.
        </p>
      )}

      {error && <p className="font-body text-xs text-red-600">{error}</p>}
    </div>
  );
}

export function ConsistencyPanel() {
  const [report, setReport] = useState<Report | null>(null);
  const [loading, setLoading] = useState(true);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setReport(await getReport());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't load. Please try again.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // Never checked, or the setup changed since: check once on its own instead of asking.
  const autoChecked = useRef(false);
  useEffect(() => {
    if (!report || autoChecked.current || (report.checked_at && !report.stale)) return;
    autoChecked.current = true;
    runCheck();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [report]);

  async function runCheck() {
    setChecking(true);
    setError(null);
    try {
      setReport(await checkNow());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't check right now. Please try again.");
    } finally {
      setChecking(false);
    }
  }

  async function handleFix(id: string, text?: string) {
    await fixIssue(id, text);
    await load();
  }

  async function handleDismiss(id: string) {
    await dismissIssue(id);
    await load();
  }

  if (loading) {
    return (
      <div className="h-11 animate-pulse rounded-xl bg-border-subtle" aria-hidden />
    );
  }

  const issues = report?.issues ?? [];
  const needsCheck = !report?.checked_at || report?.stale;

  if (issues.length === 0) {
    return (
      <div aria-live="polite" className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-border-subtle bg-surface-low px-3.5 py-2.5">
        <span className="font-body text-xs text-ink-muted">
          {checking ? (
            "Aira is checking that your description and knowledge agree with your Services page…"
          ) : needsCheck ? (
            error ?? (report?.checked_at ? "Your setup changed since Aira last checked." : "Aira hasn't checked your setup yet.")
          ) : (
            <>Everything Aira knows agrees with your Services page{report?.checked_at ? ` · Checked ${timeAgo(report.checked_at)}` : ""}</>
          )}
        </span>
        <button
          type="button"
          disabled={checking}
          onClick={runCheck}
          className="inline-flex items-center gap-1.5 font-label text-xs font-semibold text-primary hover:text-primary/80 disabled:opacity-50"
        >
          {checking && <Loader2 size={12} className="animate-spin" />}
          {checking ? "Checking…" : "Check again"}
        </button>
      </div>
    );
  }

  return (
    <div aria-live="polite" className="space-y-3 rounded-2xl border border-amber-200 bg-amber-50/60 p-4 sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-2.5">
          <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-amber-100 text-amber-700">
            <AlertTriangle size={14} />
          </span>
          <div>
            <p className="font-display text-sm font-bold text-ink">
              Aira found {issues.length} thing{issues.length === 1 ? "" : "s"} that disagree{issues.length === 1 ? "s" : ""} with your Services page
            </p>
            <p className="mt-0.5 max-w-xl font-body text-xs leading-relaxed text-ink-secondary">
              Aira always follows your Services page when they disagree, but fixing these keeps every answer consistent.
            </p>
          </div>
        </div>
        <button
          type="button"
          disabled={checking}
          onClick={runCheck}
          className="shrink-0 inline-flex items-center gap-1.5 font-label text-xs font-semibold text-primary hover:text-primary/80 disabled:opacity-50"
        >
          {checking && <Loader2 size={12} className="animate-spin" />}
          {checking ? "Checking…" : "Check again"}
        </button>
      </div>

      {error && <p className="font-body text-xs text-red-600">{error}</p>}

      <div className="space-y-2.5">
        {issues.map((issue) => (
          <IssueCard key={issue.id} issue={issue} onFix={handleFix} onDismiss={handleDismiss} />
        ))}
      </div>
    </div>
  );
}
