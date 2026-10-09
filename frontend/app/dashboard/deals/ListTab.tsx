"use client";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { MessageCircle, Link as LinkIcon, ChevronUp, ChevronDown } from "lucide-react";
import { api, DealFilters, DealListPage, DealSort } from "@/lib/api";
import { formatRupees } from "@/components/deals/money";
import { StageBadge } from "@/components/deals/StageBadge";
import { SourceBadge } from "@/components/deals/SourceBadge";
import { timeAgo, formatPhone } from "@/lib/utils";
import { getDealTags } from "@/lib/deal-tags";
import { shortRupees } from "@/lib/deal-filters";

const BRAND_COLORS = ["#038285", "#0A1528", "#6366f1", "#b45309", "#be123c", "#047857"];

function getColorForLead(leadId: string): string {
  let hash = 0;
  for (let i = 0; i < leadId.length; i++) {
    hash = ((hash << 5) - hash) + leadId.charCodeAt(i);
    hash = hash & hash;
  }
  return BRAND_COLORS[Math.abs(hash) % BRAND_COLORS.length];
}

function Avatar({ name, phone, leadId }: { name?: string | null; phone?: string | null; leadId: string }) {
  // Two-letter initials: first letters of first two words, else first char of phone
  let initials = "?";
  if (name) {
    const words = name.trim().split(/\s+/);
    initials = words.slice(0, 2).map((w) => w[0]).join("").toUpperCase();
    if (initials.length === 1) initials = initials[0];
  } else if (phone) {
    initials = phone.substring(0, 2).toUpperCase();
  }
  const color = getColorForLead(leadId);
  return (
    <div
      style={{ backgroundColor: color }}
      className="flex h-7 w-7 items-center justify-center rounded-full text-[10px] font-bold text-white shrink-0"
    >
      {initials}
    </div>
  );
}

export function ListTab({
  filters,
  sort,
  dir,
  page,
  onSortChange,
  onPageChange,
  onOpenDeal,
  reloadToken,
}: {
  filters: DealFilters & { view?: string };
  sort: DealSort;
  dir: "asc" | "desc";
  page: number;
  onSortChange: (sort: DealSort, dir: "asc" | "desc") => void;
  onPageChange: (page: number) => void;
  onOpenDeal: (id: string) => void;
  reloadToken: number;
}) {
  const router = useRouter();
  const [data, setData] = useState<DealListPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [copyingId, setCopyingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const result = await api.deals.list(
        {
          stage: filters.stage,
          source: filters.source,
          q: filters.q,
          created_from: filters.created_from,
          created_to: filters.created_to,
          min_rupees: filters.min_rupees,
          max_rupees: filters.max_rupees,
          payment_method: filters.payment_method,
          product: filters.product,
          attention: filters.attention,
        },
        { sort, dir, page, limit: 50 }
      );
      setData(result);
      setSelectedIds(new Set());
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, [filters, sort, dir, page]);

  useEffect(() => {
    load();
  }, [load, reloadToken]);

  const handleSort = (newSort: DealSort) => {
    if (sort === newSort) {
      onSortChange(newSort, dir === "asc" ? "desc" : "asc");
    } else {
      onSortChange(newSort, "desc");
    }
  };

  const selectedCount = selectedIds.size;
  const selectedTotal = selectedCount > 0 ? Array.from(selectedIds).reduce((sum, id) => {
    const deal = data?.data.find((d) => d.id === id);
    return sum + (deal?.total_paise || 0);
  }, 0) : 0;

  const handleSelectAll = () => {
    if (selectedCount === data?.data.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(data?.data.map((d) => d.id) || []));
    }
  };

  const handleExport = () => {
    if (selectedCount === 0) return;

    const deals = data?.data.filter((d) => selectedIds.has(d.id)) || [];
    const csv = [
      ["Deal", "Customer", "Phone", "Items", "Stage", "Source", "Value (₹)", "Payment", "Created"].join(","),
      ...deals.map((deal) => {
        const payment = deal.payment_method || deal.lost_reason || "—";
        const created = new Date(deal.created_at).toLocaleDateString("en-IN");
        return [
          `"${deal.deal_label}"`,
          `"${(deal.lead.name || "").replace(/"/g, '""')}"`,
          `"${(deal.lead.phone || "").replace(/"/g, '""')}"`,
          `"${deal.item_summary.replace(/"/g, '""')}"`,
          deal.stage,
          deal.source,
          Math.round(deal.total_paise / 100),
          `"${payment.replace(/"/g, '""')}"`,
          created,
        ].join(",");
      }),
    ].join("\n");

    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "deals-selected.csv";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  if (loading) {
    return (
      <div className="space-y-2 p-4">
        {[...Array(8)].map((_, i) => (
          <div key={i} className="h-10 animate-pulse rounded-xl bg-border-subtle" />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center gap-3 py-16 text-center">
        <p className="font-body text-sm text-ink-muted">Could not load deals.</p>
        <button
          type="button"
          onClick={load}
          className="rounded-xl bg-primary px-4 py-2 font-label text-xs font-bold text-white hover:bg-primary/90"
        >
          Retry
        </button>
      </div>
    );
  }

  if (!data || data.data.length === 0) {
    return (
      <div className="flex flex-col items-center gap-4 py-16 text-center">
        <p className="font-body text-sm text-ink-muted">No deals match these filters.</p>
        <button
          type="button"
          onClick={() => {
            const params = new URLSearchParams();
            params.set("tab", "deals");
            router.replace(`/dashboard/deals?${params.toString()}`, { scroll: false });
          }}
          className="rounded-xl border border-border px-4 py-2 font-label text-xs font-bold text-ink hover:bg-surface-subtle"
        >
          Clear filters
        </button>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      {selectedCount > 0 && (
        <div className="flex items-center justify-between gap-4 bg-ink px-5 py-2 text-white">
          <div className="font-body text-sm">
            {selectedCount} selected · {shortRupees(selectedTotal)}
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleExport}
              className="rounded px-3 py-1.5 font-label text-xs font-bold hover:bg-ink/90"
            >
              Export selected
            </button>
            <button
              type="button"
              onClick={() => setSelectedIds(new Set())}
              className="rounded px-3 py-1.5 font-label text-xs font-bold hover:bg-ink/90"
            >
              Clear
            </button>
          </div>
        </div>
      )}

      <div className="flex-1 overflow-x-auto">
        <table className="w-full border-collapse text-left text-sm">
          <thead>
            <tr className="border-b border-border">
              <th className="w-8 px-4 py-3 text-center">
                <input
                  type="checkbox"
                  checked={selectedCount > 0 && selectedCount === data.data.length}
                  ref={(el) => {
                    if (el) el.indeterminate = selectedCount > 0 && selectedCount < data.data.length;
                  }}
                  onChange={handleSelectAll}
                  className="cursor-pointer rounded border-border"
                />
              </th>
              <th className="px-4 py-3">
                <button
                  type="button"
                  onClick={() => handleSort("deal_number")}
                  className="font-label text-[10px] font-bold uppercase tracking-wide text-ink-muted hover:text-ink flex items-center gap-1"
                >
                  Deal
                  {sort === "deal_number" && (dir === "asc" ? <ChevronUp size={12} /> : <ChevronDown size={12} />)}
                </button>
              </th>
              <th className="px-4 py-3 font-label text-[10px] font-bold uppercase tracking-wide text-ink-muted">Customer</th>
              <th className="px-4 py-3 font-label text-[10px] font-bold uppercase tracking-wide text-ink-muted">Items</th>
              <th className="px-4 py-3 font-label text-[10px] font-bold uppercase tracking-wide text-ink-muted">Stage</th>
              <th className="px-4 py-3 font-label text-[10px] font-bold uppercase tracking-wide text-ink-muted">Source</th>
              <th className="px-4 py-3 text-right">
                <button
                  type="button"
                  onClick={() => handleSort("total_paise")}
                  className="font-label text-[10px] font-bold uppercase tracking-wide text-ink-muted hover:text-ink flex items-center justify-end gap-1 w-full"
                >
                  Value
                  {sort === "total_paise" && (dir === "asc" ? <ChevronUp size={12} /> : <ChevronDown size={12} />)}
                </button>
              </th>
              <th className="px-4 py-3 font-label text-[10px] font-bold uppercase tracking-wide text-ink-muted">Payment</th>
              <th className="px-4 py-3 font-label text-[10px] font-bold uppercase tracking-wide text-ink-muted">Last activity</th>
              <th className="px-4 py-3 text-right">
                <button
                  type="button"
                  onClick={() => handleSort("created_at")}
                  className="font-label text-[10px] font-bold uppercase tracking-wide text-ink-muted hover:text-ink flex items-center justify-end gap-1 w-full"
                >
                  Created
                  {sort === "created_at" && (dir === "asc" ? <ChevronUp size={12} /> : <ChevronDown size={12} />)}
                </button>
              </th>
              <th className="px-4 py-3 w-12 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {data.data.map((deal) => {
              const tags = getDealTags(deal);
              return (
                <tr
                  key={deal.id}
                  className="group border-b border-border-subtle hover:bg-surface-subtle transition-colors cursor-pointer"
                >
                  <td
                    className="px-4 py-3 text-center"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <input
                      type="checkbox"
                      checked={selectedIds.has(deal.id)}
                      onChange={(e) => {
                        const newSelected = new Set(selectedIds);
                        if (e.target.checked) {
                          newSelected.add(deal.id);
                        } else {
                          newSelected.delete(deal.id);
                        }
                        setSelectedIds(newSelected);
                      }}
                      className="cursor-pointer rounded border-border"
                      onClick={(e) => e.stopPropagation()}
                    />
                  </td>
                  <td
                    className="px-4 py-3 font-mono text-xs text-ink whitespace-nowrap"
                    onClick={() => onOpenDeal(deal.id)}
                  >
                    {deal.deal_label}
                  </td>
                  <td
                    className="px-4 py-3 whitespace-nowrap"
                    onClick={() => onOpenDeal(deal.id)}
                  >
                    <div className="flex items-center gap-2">
                      <Avatar name={deal.lead.name} phone={deal.lead.phone} leadId={deal.lead.id} />
                      <div className="min-w-0">
                        <p className="font-body text-sm font-bold text-ink truncate">{deal.lead.name || "—"}</p>
                        <p className="font-body text-xs text-ink-muted truncate">{formatPhone(deal.lead.phone)}</p>
                      </div>
                    </div>
                  </td>
                  <td
                    className="px-4 py-3 max-w-xs"
                    onClick={() => onOpenDeal(deal.id)}
                  >
                    <p className="font-body text-sm text-ink-muted truncate">{deal.item_summary}</p>
                  </td>
                  <td
                    className="px-4 py-3 whitespace-nowrap"
                    onClick={() => onOpenDeal(deal.id)}
                  >
                    <div className="space-y-1">
                      <StageBadge stage={deal.stage} />
                      {tags.length > 0 && (
                        <div className="flex flex-wrap gap-1">
                          {tags.map((tag) => (
                            <span
                              key={tag.key}
                              className={`inline-flex items-center rounded-full border px-1.5 py-0.5 font-label text-[10px] font-bold whitespace-nowrap ${
                                tag.tone === "muted"
                                  ? "bg-slate-50 text-slate-600 border-slate-200"
                                  : tag.tone === "warning"
                                  ? "bg-amber-50 text-amber-700 border-amber-200"
                                  : "bg-rose-50 text-rose-600 border-rose-200"
                              }`}
                            >
                              {tag.label}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  </td>
                  <td
                    className="px-4 py-3 whitespace-nowrap"
                    onClick={() => onOpenDeal(deal.id)}
                  >
                    <SourceBadge source={deal.source} />
                  </td>
                  <td
                    className="px-4 py-3 font-display text-sm font-bold text-ink whitespace-nowrap text-right tabular-nums"
                    onClick={() => onOpenDeal(deal.id)}
                  >
                    {formatRupees(deal.total_paise)}
                  </td>
                  <td
                    className="px-4 py-3 font-body text-sm text-ink-muted whitespace-nowrap"
                    onClick={() => onOpenDeal(deal.id)}
                  >
                    {deal.payment_method
                      ? { razorpay: "Razorpay", cash: "Cash", upi: "UPI", card: "Card", bank_transfer: "Bank transfer", other: "Other" }[deal.payment_method]
                      : deal.lost_reason || "—"}
                  </td>
                  <td
                    className="px-4 py-3 font-body text-sm text-ink-muted whitespace-nowrap"
                    onClick={() => onOpenDeal(deal.id)}
                  >
                    {deal.last_activity_at ? timeAgo(deal.last_activity_at) : "—"}
                  </td>
                  <td
                    className="px-4 py-3 font-body text-sm text-ink-muted whitespace-nowrap text-right"
                    onClick={() => onOpenDeal(deal.id)}
                  >
                    {timeAgo(deal.created_at)}
                  </td>
                  <td
                    className="px-4 py-3 opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 transition-opacity flex items-center justify-end gap-1"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <button
                      type="button"
                      onClick={() => router.push(`/dashboard/conversations?lead=${deal.lead.id}`)}
                      className="p-1.5 hover:bg-surface-subtle rounded transition-colors"
                      title="Open chat"
                    >
                      <MessageCircle size={16} className="text-ink-muted" />
                    </button>
                    {deal.payment_link && (
                      <button
                        type="button"
                        onClick={() => {
                          navigator.clipboard.writeText(deal.payment_link!);
                          setCopyingId(deal.id);
                          setTimeout(() => setCopyingId(null), 1500);
                        }}
                        className="p-1.5 hover:bg-surface-subtle rounded transition-colors"
                        title="Copy payment link"
                      >
                        <LinkIcon
                          size={16}
                          className={copyingId === deal.id ? "text-emerald-600" : "text-ink-muted"}
                        />
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between border-t border-border px-5 py-3 bg-surface-subtle">
        <p className="font-body text-xs text-ink-muted">
          Showing {(page - 1) * 50 + 1}–{Math.min(page * 50, data.total)} of {data.total} · total {shortRupees(
            data.data.reduce((sum, d) => sum + d.total_paise, 0)
          )}
          {" "}(this page)
        </p>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => onPageChange(page - 1)}
            disabled={page === 1}
            className="rounded border border-border px-3 py-1.5 font-label text-xs font-bold text-ink disabled:opacity-50 hover:bg-white disabled:hover:bg-transparent"
          >
            Prev
          </button>
          <button
            type="button"
            onClick={() => onPageChange(page + 1)}
            disabled={page * 50 >= data.total}
            className="rounded border border-border px-3 py-1.5 font-label text-xs font-bold text-ink disabled:opacity-50 hover:bg-white disabled:hover:bg-transparent"
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
}
