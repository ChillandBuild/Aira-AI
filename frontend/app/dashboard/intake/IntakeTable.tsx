"use client";
import { useEffect, useRef, useState } from "react";
import { Check, CheckCircle2, Copy, Pencil } from "lucide-react";
import { IntakeSession } from "@/lib/api";
import { FieldColumn } from "./columns";

const STATUS_BADGE: Record<string, string> = {
  awaiting_payment: "bg-amber-50 text-amber-700 border-amber-200",
  paid: "bg-emerald-50 text-emerald-700 border-emerald-200",
  resolved: "bg-slate-50 text-slate-500 border-slate-200",
};

const STATUS_LABEL: Record<string, string> = {
  awaiting_payment: "Awaiting payment",
  paid: "Paid",
  resolved: "Resolved",
};

interface PackageOption {
  key: string;
  name: string;
  amount_paise: number;
}

interface IntakeTableProps {
  rows: IntakeSession[];
  columns: FieldColumn[];
  visibleKeys: Set<string>;
  packages: PackageOption[];
  hasMore: boolean;
  loadingMore: boolean;
  onLoadMore: () => void;
  onChangePackage: (sessionId: string, packageKey: string) => void;
  onResolve: (sessionId: string) => Promise<void>;
}

function CopyLinkButton({ link }: { link: string }) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    await navigator.clipboard.writeText(link);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <button
      type="button"
      onClick={handleCopy}
      aria-label="Copy payment link"
      title={copied ? "Copied" : "Copy payment link"}
      className="inline-flex items-center gap-1 rounded-lg border border-border px-2 py-1 font-label text-[10px] font-bold text-ink-muted hover:bg-surface-subtle"
    >
      {copied ? <Check size={11} className="text-emerald-600" /> : <Copy size={11} />}
      {copied ? "Copied" : "Copy link"}
    </button>
  );
}

const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/;

/** Dates are stored as 2003-11-19; staff read day-first, so show 19-11-2003. */
function formatAnswer(value: string | undefined): string {
  if (!value) return "—";
  const iso = ISO_DATE.exec(value);
  return iso ? `${iso[3]}-${iso[2]}-${iso[1]}` : value;
}

function AstroCell({ row }: { row: IntakeSession }) {
  if (!row.astro || row.status === "awaiting_payment") {
    return <span className="font-body text-sm text-ink-muted">—</span>;
  }
  if (row.astro.sent) {
    return (
      <span
        title={row.astro.horoscope_id ? `Horoscope ${row.astro.horoscope_id}` : undefined}
        className="inline-flex rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 font-label text-[10px] font-bold text-emerald-700"
      >
        Sent #{row.astro.question_id}
      </span>
    );
  }
  return (
    <span
      title="This paid question has not reached AstroTamil yet. Aira keeps retrying and alerts staff if it stays stuck."
      className="inline-flex rounded-full border border-red-200 bg-red-50 px-2.5 py-1 font-label text-[10px] font-bold text-red-700"
    >
      Not sent
    </span>
  );
}

function ResolveButton({ sessionId, onResolve }: { sessionId: string; onResolve: (sessionId: string) => Promise<void> }) {
  const [resolving, setResolving] = useState(false);

  async function handleResolve(e: React.MouseEvent) {
    e.stopPropagation();
    setResolving(true);
    try {
      await onResolve(sessionId);
    } finally {
      setResolving(false);
    }
  }

  return (
    <button
      type="button"
      onClick={handleResolve}
      disabled={resolving}
      aria-label="Mark resolved"
      title="Mark resolved"
      className="ml-1.5 inline-flex items-center gap-1 rounded-lg border border-border px-1.5 py-0.5 font-label text-[10px] font-bold text-ink-muted hover:bg-surface-subtle disabled:opacity-50"
    >
      <CheckCircle2 size={11} />
      {resolving ? "…" : "Resolve"}
    </button>
  );
}

function PackageCell({
  row, packages, onChangePackage,
}: {
  row: IntakeSession;
  packages: PackageOption[];
  onChangePackage: (sessionId: string, packageKey: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const canEdit = row.status === "awaiting_payment" && packages.length > 1;

  if (editing) {
    return (
      <select
        autoFocus
        value={row.package_key ?? ""}
        onChange={(e) => {
          onChangePackage(row.id, e.target.value);
          setEditing(false);
        }}
        onBlur={() => setEditing(false)}
        className="rounded-lg border border-border px-2 py-1 font-body text-sm"
        onClick={(e) => e.stopPropagation()}
      >
        {packages.map((p) => (
          <option key={p.key} value={p.key}>
            {p.name} — ₹{(p.amount_paise / 100).toFixed(0)}
          </option>
        ))}
      </select>
    );
  }

  return (
    <span className="inline-flex items-center gap-1.5">
      {row.package_name || "—"}
      {canEdit && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            setEditing(true);
          }}
          aria-label="Change package"
          title="Change package"
          className="text-ink-muted hover:text-ink"
        >
          <Pencil size={11} />
        </button>
      )}
    </span>
  );
}

export function IntakeTable({
  rows, columns, visibleKeys, packages, hasMore, loadingMore, onLoadMore, onChangePackage, onResolve,
}: IntakeTableProps) {
  const sentinel = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const node = sentinel.current;
    if (!node || !hasMore) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && !loadingMore) onLoadMore();
      },
      { rootMargin: "200px" }
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [hasMore, loadingMore, onLoadMore]);

  const shown = columns.filter((c) => visibleKeys.has(c.key));
  // Only a client connected to AstroTamil gets rows carrying "astro"; everyone else sees no column.
  const showAstro = rows.some((r) => r.astro);

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-left">
        <thead>
          <tr className="border-b border-border bg-surface-subtle">
            <th className="sticky left-0 z-20 w-[180px] min-w-[180px] max-w-[180px] bg-surface-subtle px-4 py-2 font-label text-[10px] font-bold uppercase tracking-wide text-ink-muted">
              Lead
            </th>
            <th className="sticky left-[180px] z-20 w-[140px] min-w-[140px] max-w-[140px] border-r border-border bg-surface-subtle px-4 py-2 font-label text-[10px] font-bold uppercase tracking-wide text-ink-muted shadow-[inset_-1px_0_0_0_#e8e3db]">
              Phone
            </th>
            <th className="whitespace-nowrap px-4 py-2 font-label text-[10px] font-bold uppercase tracking-wide text-ink-muted">Status</th>
            <th className="whitespace-nowrap px-4 py-2 font-label text-[10px] font-bold uppercase tracking-wide text-ink-muted">Package</th>
            <th className="whitespace-nowrap px-4 py-2 font-label text-[10px] font-bold uppercase tracking-wide text-ink-muted">Amount</th>
            <th className="whitespace-nowrap px-4 py-2 font-label text-[10px] font-bold uppercase tracking-wide text-ink-muted">Payment Link</th>
            {showAstro && (
              <th className="whitespace-nowrap px-4 py-2 font-label text-[10px] font-bold uppercase tracking-wide text-ink-muted">AstroTamil</th>
            )}
            <th className="whitespace-nowrap px-4 py-2 font-label text-[10px] font-bold uppercase tracking-wide text-ink-muted">Submitted</th>
            {shown.map((col) => (
              <th key={col.key} className="whitespace-nowrap px-4 py-2 font-label text-[10px] font-bold uppercase tracking-wide text-ink-muted">
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const leadName = row.leads?.name || row.collected_data?.name || "Unknown lead";
            const leadPhone = row.leads?.phone || "—";
            return (
              <tr key={row.id} className="group border-b border-border-subtle hover:bg-surface-subtle">
                <td
                  title={leadName}
                  className="sticky left-0 z-10 w-[180px] min-w-[180px] max-w-[180px] bg-surface px-4 py-3 font-label text-sm font-semibold text-ink group-hover:bg-surface-subtle"
                >
                  <div className="truncate" title={leadName}>
                    {leadName}
                  </div>
                </td>
                <td
                  title={leadPhone}
                  className="sticky left-[180px] z-10 w-[140px] min-w-[140px] max-w-[140px] whitespace-nowrap border-r border-border bg-surface px-4 py-3 font-body text-sm text-ink-muted shadow-[inset_-1px_0_0_0_#e8e3db] group-hover:bg-surface-subtle"
                >
                  <div className="truncate" title={leadPhone}>
                    {leadPhone}
                  </div>
                </td>
                <td className="whitespace-nowrap px-4 py-3">
                  <span className={`inline-flex rounded-full border px-2.5 py-1 font-label text-[10px] font-bold ${STATUS_BADGE[row.status]}`}>
                    {STATUS_LABEL[row.status]}
                  </span>
                  {row.status === "paid" && <ResolveButton sessionId={row.id} onResolve={onResolve} />}
                </td>
                <td className="whitespace-nowrap px-4 py-3 font-body text-sm text-ink">
                  <PackageCell row={row} packages={packages} onChangePackage={onChangePackage} />
                </td>
                <td className="whitespace-nowrap px-4 py-3 font-body text-sm text-ink">
                  {row.amount_paise ? `₹${(row.amount_paise / 100).toFixed(0)}` : "—"}
                  {row.amount_mismatch && (
                    <span className="ml-1 font-label text-[10px] font-bold text-amber-700" title="Amount paid differs from the package price">
                      ⚠
                    </span>
                  )}
                  {!!row.gst_amount_paise && row.gst_amount_paise > 0 && (
                    <div className="font-body text-[11px] text-ink-muted">
                      (incl. ₹{(row.gst_amount_paise / 100).toFixed(2)} GST)
                    </div>
                  )}
                </td>
                <td className="whitespace-nowrap px-4 py-3">
                  {row.payment_link ? <CopyLinkButton link={row.payment_link} /> : <span className="font-body text-sm text-ink-muted">—</span>}
                </td>
                {showAstro && (
                  <td className="whitespace-nowrap px-4 py-3">
                    <AstroCell row={row} />
                  </td>
                )}
                <td className="whitespace-nowrap px-4 py-3 font-body text-sm text-ink-muted">
                  {new Date(row.created_at).toLocaleDateString()}
                </td>
                {shown.map((col) => (
                  <td key={col.key} className="whitespace-nowrap px-4 py-3 font-body text-sm text-ink">
                    {formatAnswer(row.collected_data?.[col.key])}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
      <div ref={sentinel} className="h-8" />
      {loadingMore && (
        <p className="py-3 text-center font-body text-xs text-ink-muted">Loading more…</p>
      )}
    </div>
  );
}
