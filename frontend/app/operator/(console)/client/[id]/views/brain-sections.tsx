"use client";
import Link from "next/link";
import { SectionCard } from "@/components/brain/SectionCard";
import { WaitingRow } from "@/components/brain/WaitingRow";
import {
  daysWaited,
  isStuckApproval,
  waitedLabel,
  type FallbackSignals,
  type OperatorHistory,
  type OperatorRow,
  type OperatorRowState,
} from "@/components/brain/operatorBrain";
import type { BrainStatus, BrainWaiting } from "@/components/brain/types";
import { relTime } from "@/lib/operator";

const STATE_LABEL: Record<OperatorRowState, string> = { ok: "OK", missing: "Missing", off: "Not needed", attention: "Check" };
const STATE_CLASS: Record<OperatorRowState, string> = {
  ok: "bg-emerald-50 text-success",
  missing: "bg-rose-50 text-danger",
  off: "bg-surface-mid text-ink-secondary",
  attention: "bg-amber-50 text-warning",
};
const LINK_CLASS = "font-label text-xs font-bold text-primary hover:text-primary-dark focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40";
const CONNECTION_LABEL: Record<string, string> = {
  ok: "Connected",
  token_problem: "Token problem in the last 48 hours",
  quiet: "Connected, but no inbound messages for a week",
  unknown: "No inbound messages seen yet",
};

function Empty({ children }: { children: string }) {
  return <p className="font-body text-sm text-ink-secondary">{children}</p>;
}

export function WaitingReadOnly({ waiting }: { waiting: BrainWaiting }) {
  return (
    <SectionCard title="Waiting on the client" subtitle="Read-only. The client acts on these from their own dashboard.">
      {waiting.count === 0 && <Empty>Nothing is waiting.</Empty>}
      <div className="flex flex-col gap-2">
        {waiting.sort_reviews.map((review) => {
          const stuck = isStuckApproval(review.created_at);
          return (
            <WaitingRow key={review.id} title={review.title} meta={`Sorted ${relTime(review.created_at)}`}>
              <span
                className={`rounded-full px-2 py-0.5 font-label text-[10px] font-bold ${stuck ? "bg-amber-50 text-warning" : "bg-surface-mid text-ink-secondary"}`}
              >
                Waiting {waitedLabel(daysWaited(review.created_at))}{stuck ? " (stuck)" : ""}
              </span>
            </WaitingRow>
          );
        })}
        {waiting.consistency_count > 0 && (
          <WaitingRow title={`${waiting.consistency_count} conflict${waiting.consistency_count === 1 ? "" : "s"} between the client's inputs`} meta="From the stored consistency report">
            <span />
          </WaitingRow>
        )}
        {waiting.failed_files.map((file) => (
          <WaitingRow key={file.id} title={file.name || "A file"} meta="Failed to sort"><span /></WaitingRow>
        ))}
        {waiting.rejected_templates.map((template, index) => (
          <WaitingRow key={template.id ?? index} title={template.name ?? "A message template"} meta="Rejected by WhatsApp"><span /></WaitingRow>
        ))}
      </div>
    </SectionCard>
  );
}

export function StatusDetail({ status }: { status: BrainStatus }) {
  const connection = status.connection;
  return (
    <SectionCard title="Aira can reply" subtitle="Auto-reply switch and channel connection (a token problem means an incident in the last 48 hours).">
      <ul className="flex flex-col gap-2 font-body text-sm text-ink">
        <li>Auto-reply: <span className="font-semibold">{status.auto_reply === "on" ? "On" : "Off"}</span></li>
        {connection && (
          <li>
            Connection: <span className="font-semibold">{CONNECTION_LABEL[connection.state] ?? connection.state}</span>
            <ul className="mt-1 flex flex-col gap-0.5 text-xs text-ink-secondary">
              {connection.channels.map((channel) => (
                <li key={channel.channel}>
                  <span className="capitalize">{channel.channel}</span>: last inbound {relTime(channel.last_event)}
                  {channel.token_problem ? " (token problem)" : ""}
                </li>
              ))}
            </ul>
          </li>
        )}
        {status.quota && (
          <li>
            Quota caps:{" "}
            {status.quota.metrics.map((m) => `${m.metric} ${m.used}/${m.hard_cap}`).join(", ")}
          </li>
        )}
      </ul>
    </SectionCard>
  );
}

function OperatorRowItem({ row, onOpenSection }: { row: OperatorRow; onOpenSection?: (section: string) => void }) {
  const openInPlace = row.section !== null && onOpenSection !== undefined;
  return (
    <li className="flex min-w-0 flex-wrap items-center justify-between gap-x-3 gap-y-1.5 rounded-xl border border-border-subtle bg-surface-low px-3 py-2.5">
      <div className="min-w-0 flex-1 basis-40">
        <p className="break-words font-body text-sm font-semibold text-ink">{row.label}</p>
        <p className="break-words font-body text-xs text-ink-secondary">{row.detail}</p>
      </div>
      <div className="flex shrink-0 items-center gap-3">
        <span className={`rounded-full px-2 py-0.5 font-label text-[10px] font-bold ${STATE_CLASS[row.state]}`}>{STATE_LABEL[row.state]}</span>
        {openInPlace ? (
          <button type="button" className={LINK_CLASS} onClick={() => onOpenSection(row.section as string)}>Open in Config</button>
        ) : (
          <Link href={row.href} className={LINK_CLASS}>Open</Link>
        )}
      </div>
    </li>
  );
}

export function OperatorOnlyRows({ rows, onOpenSection }: { rows: OperatorRow[]; onOpenSection?: (section: string) => void }) {
  return (
    <SectionCard title="Operator only" subtitle="Platform and provider settings the client never sees. Key values are never shown, only present or missing.">
      <ul className="flex flex-col gap-2">
        {rows.map((row) => <OperatorRowItem key={row.key} row={row} onOpenSection={onOpenSection} />)}
      </ul>
    </SectionCard>
  );
}

export function HistorySection({ history }: { history: OperatorHistory }) {
  return (
    <SectionCard title="History" subtitle="Approvals and fixes that changed what Aira reads. Dismissals and discards are not timestamped, so they are not listed.">
      {history.entries.length === 0 ? <Empty>No changes recorded yet.</Empty> : (
        <ul className="flex flex-col gap-2">
          {history.entries.map((entry) => (
            <li key={entry.id} className="flex min-w-0 flex-wrap items-baseline justify-between gap-x-3 rounded-xl border border-border-subtle bg-surface-low px-3 py-2">
              <p className="min-w-0 break-words font-body text-sm text-ink">
                <span className="font-semibold">{entry.label}</span>
                {entry.target ? `: ${entry.target}` : ""}
              </p>
              <span className="font-body text-xs text-ink-muted">{relTime(entry.at)}</span>
            </li>
          ))}
        </ul>
      )}
      {history.dismissed_conflicts > 0 && (
        <p className="mt-2 font-body text-xs text-ink-secondary">
          {history.dismissed_conflicts} conflict{history.dismissed_conflicts === 1 ? " is" : "s are"} currently dismissed.
        </p>
      )}
    </SectionCard>
  );
}

export function FallbackSection({ signals }: { signals: FallbackSignals }) {
  return (
    <SectionCard title="Fallback signals" subtitle={`Handovers caused by an AI failure or a generic fallback reply, last ${signals.window_days} days.`}>
      <p className="font-body text-sm text-ink">
        <span className="font-display text-lg font-extrabold">{signals.count}</span>{" "}
        {signals.count === 1 ? "handover" : "handovers"}
      </p>
      <p className="mt-1 font-body text-xs text-ink-secondary">
        Inbox escalation for these triggers: {signals.escalation_enabled ? "on" : "not fully on"}
        {" "}(A generic fallback: {signals.triggers.A ? "on" : "off"}, B AI failure: {signals.triggers.B ? "on" : "off"}).
      </p>
      {signals.note && <p className="mt-1 font-body text-xs font-semibold text-warning">{signals.note}</p>}
    </SectionCard>
  );
}

/** Later work replaces these two blocks: "Test Aira" (answers-only sandbox, step 9) and a per-lead "What Aira saw" (step 8). */
export function LaterPlaceholders() {
  return (
    <div data-placeholder="operator-brain-later" className="grid gap-4 md:grid-cols-2">
      {/* PLACEHOLDER: Test Aira (blueprint step 9). Replace this block, keep the wrapper. */}
      <div data-placeholder="test-aira">
        <SectionCard title="Test Aira" subtitle="Coming later: ask Aira a question and see its answer, without creating a lead or sending anything.">
          <Empty>Not built yet.</Empty>
        </SectionCard>
      </div>
      {/* PLACEHOLDER: What Aira saw (blueprint step 8). Opens per lead from the Conversations view. */}
      <div data-placeholder="what-aira-saw">
        <SectionCard title="What Aira saw" subtitle="Coming later: open a lead in Conversations to see what Aira would see for it now.">
          <Empty>Not built yet.</Empty>
        </SectionCard>
      </div>
    </div>
  );
}
