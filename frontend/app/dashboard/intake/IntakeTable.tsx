"use client";
import { useEffect, useRef } from "react";
import { IntakeSession } from "@/lib/api";
import { FieldColumn } from "./columns";

const STATUS_BADGE: Record<string, string> = {
  awaiting_payment: "bg-amber-50 text-amber-700 border-amber-200",
  paid: "bg-emerald-50 text-emerald-700 border-emerald-200",
  resolved: "bg-stone-100 text-stone-600 border-stone-200",
};

const STATUS_LABEL: Record<string, string> = {
  awaiting_payment: "Awaiting payment",
  paid: "Paid",
  resolved: "Resolved",
};

interface IntakeTableProps {
  rows: IntakeSession[];
  columns: FieldColumn[];
  visibleKeys: Set<string>;
  selectedId: string | null;
  hasMore: boolean;
  loadingMore: boolean;
  onSelect: (row: IntakeSession) => void;
  onLoadMore: () => void;
}

export function IntakeTable({
  rows, columns, visibleKeys, selectedId, hasMore, loadingMore, onSelect, onLoadMore,
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
            <th className="sticky left-0 z-10 bg-surface px-4 py-2 font-label text-[10px] font-bold uppercase tracking-wide text-ink-muted">
              Lead
            </th>
            <th className="sticky left-[160px] z-10 bg-surface px-4 py-2 font-label text-[10px] font-bold uppercase tracking-wide text-ink-muted">
              Phone
            </th>
            <th className="px-4 py-2 font-label text-[10px] font-bold uppercase tracking-wide text-ink-muted">Status</th>
            <th className="px-4 py-2 font-label text-[10px] font-bold uppercase tracking-wide text-ink-muted">Package</th>
            <th className="px-4 py-2 font-label text-[10px] font-bold uppercase tracking-wide text-ink-muted">Amount</th>
            <th className="px-4 py-2 font-label text-[10px] font-bold uppercase tracking-wide text-ink-muted">Submitted</th>
            {shown.map((col) => (
              <th key={col.key} className="whitespace-nowrap px-4 py-2 font-label text-[10px] font-bold uppercase tracking-wide text-ink-muted">
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const isSelected = row.id === selectedId;
            const rowBg = isSelected ? "bg-primary-light/40" : "bg-surface";
            return (
              <tr
                key={row.id}
                onClick={() => onSelect(row)}
                className={`cursor-pointer border-b border-border-subtle hover:bg-surface-subtle ${isSelected ? "bg-primary-light/40" : ""}`}
              >
                <td className={`sticky left-0 z-10 ${rowBg} whitespace-nowrap px-4 py-3 font-label text-sm font-semibold text-ink`}>
                  {row.leads?.name || row.collected_data?.name || "Unknown lead"}
                </td>
                <td className={`sticky left-[160px] z-10 ${rowBg} whitespace-nowrap px-4 py-3 font-body text-sm text-ink-muted`}>
                  {row.leads?.phone || "—"}
                </td>
                <td className="whitespace-nowrap px-4 py-3">
                  <span className={`inline-flex rounded-full border px-2.5 py-1 font-label text-[10px] font-bold ${STATUS_BADGE[row.status]}`}>
                    {STATUS_LABEL[row.status]}
                  </span>
                </td>
                <td className="whitespace-nowrap px-4 py-3 font-body text-sm text-ink">{row.package_name || "—"}</td>
                <td className="whitespace-nowrap px-4 py-3 font-body text-sm text-ink">
                  {row.amount_paise ? `₹${(row.amount_paise / 100).toFixed(0)}` : "—"}
                  {row.amount_mismatch && (
                    <span className="ml-1 font-label text-[10px] font-bold text-amber-700" title="Amount paid differs from the package price">
                      ⚠
                    </span>
                  )}
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
