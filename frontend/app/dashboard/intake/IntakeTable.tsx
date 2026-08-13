"use client";
import { useEffect, useRef, useState } from "react";
import { Check, Copy, Pencil } from "lucide-react";
import { IntakeSession } from "@/lib/api";
import { FieldColumn } from "./columns";

const STATUS_BADGE: Record<string, string> = {
  awaiting_payment: "bg-amber-50 text-amber-700 border-amber-200",
  paid: "bg-emerald-50 text-emerald-700 border-emerald-200",
};

const STATUS_LABEL: Record<string, string> = {
  awaiting_payment: "Awaiting payment",
  paid: "Paid",
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
  rows, columns, visibleKeys, packages, hasMore, loadingMore, onLoadMore, onChangePackage,
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

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-left">
        <thead>
          <tr className="border-b border-border">
            <th className="sticky left-0 z-10 bg-surface-subtle px-4 py-2 font-label text-[10px] font-bold uppercase tracking-wide text-ink-muted">
              Lead
            </th>
            <th className="sticky left-[160px] z-10 bg-surface-subtle px-4 py-2 font-label text-[10px] font-bold uppercase tracking-wide text-ink-muted">
              Phone
            </th>
            <th className="px-4 py-2 font-label text-[10px] font-bold uppercase tracking-wide text-ink-muted">Status</th>
            <th className="px-4 py-2 font-label text-[10px] font-bold uppercase tracking-wide text-ink-muted">Package</th>
            <th className="px-4 py-2 font-label text-[10px] font-bold uppercase tracking-wide text-ink-muted">Amount</th>
            <th className="px-4 py-2 font-label text-[10px] font-bold uppercase tracking-wide text-ink-muted">Payment Link</th>
            <th className="px-4 py-2 font-label text-[10px] font-bold uppercase tracking-wide text-ink-muted">Submitted</th>
            {shown.map((col) => (
              <th key={col.key} className="whitespace-nowrap px-4 py-2 font-label text-[10px] font-bold uppercase tracking-wide text-ink-muted">
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id} className="border-b border-border-subtle hover:bg-surface-subtle">
              <td className="sticky left-0 z-10 whitespace-nowrap bg-surface-subtle px-4 py-3 font-label text-sm font-semibold text-ink">
                {row.leads?.name || row.collected_data?.name || "Unknown lead"}
              </td>
              <td className="sticky left-[160px] z-10 whitespace-nowrap bg-surface-subtle px-4 py-3 font-body text-sm text-ink-muted">
                {row.leads?.phone || "—"}
              </td>
              <td className="whitespace-nowrap px-4 py-3">
                <span className={`inline-flex rounded-full border px-2.5 py-1 font-label text-[10px] font-bold ${STATUS_BADGE[row.status]}`}>
                  {STATUS_LABEL[row.status]}
                </span>
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
              </td>
              <td className="whitespace-nowrap px-4 py-3">
                {row.payment_link ? <CopyLinkButton link={row.payment_link} /> : <span className="font-body text-sm text-ink-muted">—</span>}
              </td>
              <td className="whitespace-nowrap px-4 py-3 font-body text-sm text-ink-muted">
                {new Date(row.created_at).toLocaleDateString()}
              </td>
              {shown.map((col) => (
                <td key={col.key} className="whitespace-nowrap px-4 py-3 font-body text-sm text-ink">
                  {row.collected_data?.[col.key] || "—"}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <div ref={sentinel} className="h-8" />
      {loadingMore && (
        <p className="py-3 text-center font-body text-xs text-ink-muted">Loading more…</p>
      )}
    </div>
  );
}
