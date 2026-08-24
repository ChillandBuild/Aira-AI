"use client";
import { SegmentBadge } from "@/components/segment-badge";
import { cn, formatPhone } from "@/lib/utils";
import {
  TRIGGERS,
  channelOf,
  initialsOf,
  SEVERITY_TEXT,
  type EscalationLead,
  type Severity,
} from "@/lib/escalations";

/** Why the AI handed over, as a chip. Unknown reasons keep their raw text so a
 *  newly added trigger degrades to a readable grey chip instead of vanishing. */
export function TriggerChip({ reason }: { reason: string | null }) {
  if (!reason) return <span className="font-body text-xs text-ink-muted">—</span>;
  const known = TRIGGERS[reason];
  return (
    <span
      title={reason}
      className={cn(
        "inline-flex max-w-[190px] items-center truncate rounded-full border px-2.5 py-[3px] font-label text-[11px] font-bold",
        known?.className ?? "bg-surface-mid text-ink-secondary border-border"
      )}
    >
      {known?.label ?? reason}
    </span>
  );
}

export function ChannelCell({ lead }: { lead: EscalationLead }) {
  const ch = channelOf(lead);
  const handle = ch.label === "WhatsApp" ? formatPhone(ch.handle) : ch.handle;
  return (
    <span className="font-mono text-[11.5px] tracking-[-0.02em] text-ink-secondary">
      <b className={cn("font-bold", ch.className)}>{ch.label}</b>
      <span className="mx-1 text-ink-muted">·</span>
      {handle}
    </span>
  );
}

export function LeadCell({ lead }: { lead: EscalationLead }) {
  return (
    <span className="flex flex-wrap items-center gap-2">
      <span className="font-heading text-[13.5px] font-bold tracking-[-0.015em] text-ink">
        {lead?.name || "Unknown Lead"}
      </span>
      {lead?.segment && <SegmentBadge segment={lead.segment} />}
    </span>
  );
}

/** A person, or an explicit absence. Never renders a bare dash for "nobody" —
 *  unassigned and not-recorded mean different things and read differently. */
export function PersonCell({ name, empty }: { name: string | null; empty: string }) {
  if (!name) {
    return (
      <span className="flex items-center gap-2">
        <span className="flex h-[22px] w-[22px] flex-shrink-0 items-center justify-center rounded-full bg-surface-mid font-mono text-[9.5px] font-bold text-ink-muted">
          ?
        </span>
        {/* Not truncated: "Unassigned" is a fixed, known-length placeholder and
            was clipping to "Unassignea" in the narrower column. */}
        <span className="whitespace-nowrap font-body text-xs italic text-ink-muted">{empty}</span>
      </span>
    );
  }
  return (
    <span className="flex items-center gap-2">
      <span className="flex h-[22px] w-[22px] flex-shrink-0 items-center justify-center rounded-full bg-primary-muted font-mono text-[9.5px] font-bold text-primary">
        {initialsOf(name)}
      </span>
      <span className="truncate font-body text-xs font-semibold text-ink" title={name}>
        {name}
      </span>
    </span>
  );
}

export function DurationCell({ text, severity, sub }: { text: string; severity: Severity; sub?: string }) {
  return (
    <>
      <span className={cn("font-mono text-[12.5px] font-bold tabular-nums tracking-[-0.02em]", SEVERITY_TEXT[severity])}>
        {text}
      </span>
      {sub && <span className="mt-0.5 block font-body text-[10.5px] text-ink-muted">{sub}</span>}
    </>
  );
}

export function TableEmpty({
  icon,
  title,
  body,
}: {
  icon: React.ReactNode;
  title: string;
  body: string;
}) {
  return (
    <div className="mx-auto mt-10 max-w-md rounded-3xl border border-border bg-surface p-12 text-center shadow-card">
      <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-surface-mid">{icon}</div>
      <p className="font-heading text-lg font-bold text-ink">{title}</p>
      <p className="mt-1.5 font-body text-sm text-ink-secondary">{body}</p>
    </div>
  );
}

export function TableSkeleton({ columns, rows = 5 }: { columns: number; rows?: number }) {
  return (
    <tbody>
      {Array.from({ length: rows }).map((_, r) => (
        <tr key={r} className="border-b border-border-subtle">
          {Array.from({ length: columns }).map((_, c) => (
            <td key={c} className="px-3.5 py-3.5 first:pl-6 last:pr-6">
              <span
                className="block h-3.5 animate-pulse rounded-full bg-surface-mid"
                style={{ width: c === 0 ? "70%" : c === columns - 1 ? "45%" : "55%" }}
              />
            </td>
          ))}
        </tr>
      ))}
    </tbody>
  );
}
