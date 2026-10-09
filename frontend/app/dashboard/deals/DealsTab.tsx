"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Search, List, KanbanSquare } from "lucide-react";
import { api, DealStage, DealSummaryStats, DealSource, PaymentMethod, DealAttention } from "@/lib/api";
import { filtersFromParams, filtersToParams, ATTENTION_LABEL, shortRupees, SOURCE_LABEL, PAYMENT_LABEL } from "@/lib/deal-filters";
import { ListTab } from "./ListTab";
import { BoardTab } from "./BoardTab";
import { FilterPopover } from "@/components/deals/FilterPopover";

const STAGE_ORDER: DealStage[] = ["quoted", "awaiting_payment", "won", "lost"];
const STAGE_LABEL: Record<DealStage, string> = {
  quoted: "Quoted",
  awaiting_payment: "Awaiting payment",
  won: "Won",
  lost: "Lost",
};

export function DealsTab({
  onOpenDeal,
  reloadToken,
}: {
  onOpenDeal: (id: string) => void;
  reloadToken: number;
}) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [summaryLoading, setSummaryLoading] = useState(true);
  const [summaryError, setSummaryError] = useState(false);
  const [summary, setSummary] = useState<DealSummaryStats | null>(null);
  const [searchText, setSearchText] = useState("");

  // Fix infinite fetch loop: memoize filters by URL string
  const paramsKey = searchParams.toString();
  const filters = useMemo(() => filtersFromParams(new URLSearchParams(paramsKey)), [paramsKey]);
  const view = (filters.view || "table") as "table" | "board";

  const updateFilters = useCallback(
    (newFilters: typeof filters) => {
      const params = filtersToParams(newFilters);
      router.replace(`/dashboard/deals?${params.toString()}`, { scroll: false });
    },
    [router]
  );

  // Sync search text from URL
  useEffect(() => {
    setSearchText(filters.q ?? "");
  }, [filters.q]);

  // Handle search input with 300ms debounce
  useEffect(() => {
    if (searchText === (filters.q ?? "")) return; // No change
    const timer = setTimeout(() => {
      updateFilters({ ...filters, q: searchText || undefined, page: 1 });
    }, 300);
    return () => clearTimeout(timer);
  }, [searchText, filters, updateFilters]);

  // Memoize summary filters to keep loadSummary stable
  const summaryFilters = useMemo(
    () => ({
      source: filters.source,
      q: filters.q,
      created_from: filters.created_from,
      created_to: filters.created_to,
      min_rupees: filters.min_rupees,
      max_rupees: filters.max_rupees,
      payment_method: filters.payment_method,
      product: filters.product,
      attention: filters.attention,
    }),
    [filters]
  );

  const loadSummary = useCallback(async () => {
    setSummaryLoading(true);
    setSummaryError(false);
    try {
      const data = await api.deals.summary(summaryFilters);
      setSummary(data);
    } catch {
      setSummaryError(true);
    } finally {
      setSummaryLoading(false);
    }
  }, [summaryFilters]);

  useEffect(() => {
    loadSummary();
  }, [loadSummary, reloadToken]);

  const stageTotals = summary ? summary.stages : null;
  const allStageCount = stageTotals ? Object.values(stageTotals).reduce((sum, s) => sum + s.count, 0) : 0;
  const allStageTotal = stageTotals ? Object.values(stageTotals).reduce((sum, s) => sum + s.total_paise, 0) : 0;

  const openCount = stageTotals
    ? (stageTotals.quoted?.count || 0) + (stageTotals.awaiting_payment?.count || 0)
    : 0;
  const openTotal = stageTotals
    ? (stageTotals.quoted?.total_paise || 0) + (stageTotals.awaiting_payment?.total_paise || 0)
    : 0;

  const wonCount = stageTotals?.won?.count || 0;
  const wonTotal = stageTotals?.won?.total_paise || 0;

  const lostCount = stageTotals?.lost?.count || 0;
  const closedCount = wonCount + lostCount;

  const winRate = closedCount > 0 ? ((wonCount / closedCount) * 100).toFixed(0) : null;
  const avgDeal = wonCount > 0 ? wonTotal / wonCount : null;

  const unpaid3dCount = summary?.unpaid_3d?.count || 0;
  const unpaid3dTotal = summary?.unpaid_3d?.total_paise || 0;

  // Fixed preset detection: filter out undefined values and internal keys
  const activeKeys = (Object.keys(filters) as (keyof typeof filters)[]).filter(
    (k) => !["view", "sort", "dir", "page", "stage"].includes(k) && filters[k] !== undefined
  );

  const viewName = {
    "all-deals": activeKeys.length === 0,
    "unpaid-3d":
      activeKeys.length === 1 &&
      activeKeys[0] === "attention" &&
      filters.attention?.length === 1 &&
      filters.attention[0] === "unpaid_3d",
    "big-deals":
      activeKeys.length === 1 &&
      activeKeys[0] === "min_rupees" &&
      filters.min_rupees === 10000,
    indiamart:
      activeKeys.length === 1 &&
      activeKeys[0] === "source" &&
      filters.source?.length === 1 &&
      filters.source[0] === "indiamart",
    "this-week": (() => {
      if (activeKeys.length !== 1 || activeKeys[0] !== "created_from") return false;
      const weekAgo = new Date();
      weekAgo.setDate(weekAgo.getDate() - 7);
      const weekAgoIso = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(weekAgo);
      return filters.created_from === weekAgoIso;
    })(),
  };

  return (
    <div className="flex h-full flex-col bg-white">
      {/* Header row */}
      <div className="flex items-center justify-between gap-4 border-b border-border px-5 py-4">
        <div>
          <h1 className="font-display text-2xl font-extrabold text-ink">Deals</h1>
          {!summaryLoading && allStageCount > 0 && (
            <p className="font-body text-xs text-ink-muted">{allStageCount} deals</p>
          )}
        </div>
        <div className="flex items-center gap-1 rounded-full border border-border bg-surface-subtle p-1">
          <button
            type="button"
            onClick={() => {
              const params = filtersToParams({ ...filters, view: "table" });
              router.replace(`/dashboard/deals?${params.toString()}`, { scroll: false });
            }}
            className={`rounded-full p-2 transition-all ${
              view === "table" ? "bg-white text-ink shadow-sm" : "text-ink-muted hover:text-ink"
            }`}
            title="Table view"
          >
            <List size={16} />
          </button>
          <button
            type="button"
            onClick={() => {
              const params = filtersToParams({ ...filters, view: "board" });
              router.replace(`/dashboard/deals?${params.toString()}`, { scroll: false });
            }}
            className={`rounded-full p-2 transition-all ${
              view === "board" ? "bg-white text-ink shadow-sm" : "text-ink-muted hover:text-ink"
            }`}
            title="Board view"
          >
            <KanbanSquare size={16} />
          </button>
        </div>
      </div>

      {/* KPI strip with error state */}
      {summaryError && (
        <div className="flex items-center justify-between bg-amber-50 px-5 py-2 border-b border-amber-200">
          <p className="font-body text-xs text-amber-700">Couldn&apos;t load the numbers.</p>
          <button
            type="button"
            onClick={loadSummary}
            className="rounded px-2 py-1 font-label text-xs font-bold text-amber-700 hover:bg-amber-100"
          >
            Retry
          </button>
        </div>
      )}

      {summaryLoading && (
        <div className="grid grid-cols-2 gap-px border-b border-border lg:grid-cols-5">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-20 animate-pulse bg-border-subtle" />
          ))}
        </div>
      )}
      {!summaryLoading && summary && (
        <div className="grid grid-cols-2 border-b border-border lg:grid-cols-5">
          {/* Open pipeline */}
          <div className="border-r border-border px-5 py-4 last:border-r-0">
            <p className="font-label text-[11px] font-bold uppercase tracking-wide text-ink-muted">Open pipeline</p>
            <p className="font-display text-xl font-extrabold tabular-nums text-ink">{shortRupees(openTotal)}</p>
            <p className="font-body text-xs text-ink-muted">{openCount} deals open</p>
          </div>

          {/* Won */}
          <div className="border-r border-border px-5 py-4 last:border-r-0">
            <p className="font-label text-[11px] font-bold uppercase tracking-wide text-ink-muted">Won</p>
            <p className="font-display text-xl font-extrabold tabular-nums text-emerald-600">{shortRupees(wonTotal)}</p>
            <p className="font-body text-xs text-ink-muted">{wonCount} deals</p>
          </div>

          {/* Win rate */}
          <div className="border-r border-border px-5 py-4 last:border-r-0">
            <p className="font-label text-[11px] font-bold uppercase tracking-wide text-ink-muted">Win rate</p>
            <p className="font-display text-xl font-extrabold tabular-nums text-ink">{winRate ? `${winRate}%` : "—"}</p>
            <p className="font-body text-xs text-ink-muted">
              {wonCount > 0 && closedCount > 0 ? `${wonCount} won of ${closedCount} closed` : "—"}
            </p>
          </div>

          {/* Avg deal */}
          <div className="border-r border-border px-5 py-4 last:border-r-0">
            <p className="font-label text-[11px] font-bold uppercase tracking-wide text-ink-muted">Avg deal</p>
            <p className="font-display text-xl font-extrabold tabular-nums text-ink">
              {avgDeal ? shortRupees(avgDeal) : "—"}
            </p>
            <p className="font-body text-xs text-ink-muted">{wonCount > 0 ? `per won deal` : "—"}</p>
          </div>

          {/* Unpaid 3+ days */}
          <div className="px-5 py-4">
            <button
              type="button"
              onClick={() => {
                updateFilters({
                  ...filters,
                  attention: filters.attention?.includes("unpaid_3d") ? undefined : ["unpaid_3d"],
                  page: 1,
                });
              }}
              className="w-full text-left hover:opacity-80 transition-opacity"
            >
              <p className="font-label text-[11px] font-bold uppercase tracking-wide text-ink-muted">Unpaid 3+ days</p>
              <p className="font-display text-xl font-extrabold tabular-nums text-ink">{unpaid3dCount}</p>
              <p className={`font-body text-xs ${unpaid3dTotal > 0 ? "text-amber-600" : "text-ink-muted"}`}>
                {unpaid3dTotal > 0 ? `${shortRupees(unpaid3dTotal)} waiting` : "Nothing waiting"}
              </p>
            </button>
          </div>
        </div>
      )}

      {/* Stage tabs - only in table view */}
      {view === "table" && (
        <div className="flex gap-0 border-b border-border px-5 text-sm">
          <button
            type="button"
            onClick={() => updateFilters({ ...filters, stage: undefined, page: 1 })}
            className={`px-3 py-3 font-label font-bold border-b-2 transition-all ${
              !filters.stage
                ? "border-primary text-ink"
                : "border-transparent text-ink-secondary hover:text-ink"
            }`}
          >
            All
            <span className="rounded-full bg-surface-mid px-1.5 text-[11px] text-ink-muted inline-block ml-2">
              {allStageCount}
            </span>
            <span className="text-ink-muted ml-1">{shortRupees(allStageTotal)}</span>
          </button>
          {STAGE_ORDER.map((stage) => {
            const count = stageTotals?.[stage]?.count || 0;
            const total = stageTotals?.[stage]?.total_paise || 0;
            return (
              <button
                key={stage}
                type="button"
                onClick={() => updateFilters({ ...filters, stage, page: 1 })}
                className={`px-3 py-3 font-label font-bold border-b-2 transition-all ${
                  filters.stage === stage
                    ? "border-primary text-ink"
                    : "border-transparent text-ink-secondary hover:text-ink"
                }`}
              >
                {STAGE_LABEL[stage]}
                <span
                  className={`rounded-full px-1.5 text-[11px] inline-block ml-2 ${
                    filters.stage === stage
                      ? "bg-primary/10 text-primary"
                      : "bg-surface-mid text-ink-muted"
                  }`}
                >
                  {count}
                </span>
                <span className="text-ink-muted ml-1">{shortRupees(total)}</span>
              </button>
            );
          })}
        </div>
      )}

      {/* Filter bar */}
      <div className="flex flex-wrap items-center gap-2 border-b border-border px-5 py-3">
        <div className="flex items-center gap-2 rounded-full border border-border bg-white px-3 py-2">
          <Search size={16} className="text-ink-muted" />
          <input
            type="text"
            placeholder="Search name, phone or D-0012"
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            className="flex-1 bg-transparent font-body text-sm text-ink placeholder:text-ink-muted outline-none"
          />
        </div>

        <FilterPopover
          label="Source"
          active={(filters.source?.length || 0) > 0}
          count={filters.source?.length}
        >
          <div className="space-y-1.5">
            {(["whatsapp", "form", "call", "walk_in", "manual", "indiamart", "justdial"] as const).map((source) => (
              <label key={source} className="flex items-center gap-2.5 cursor-pointer px-2 py-1.5">
                <input
                  type="checkbox"
                  checked={filters.source?.includes(source) || false}
                  onChange={(e) => {
                    const newSources = e.target.checked
                      ? [...(filters.source || []), source]
                      : (filters.source || []).filter((s) => s !== source);
                    updateFilters({ ...filters, source: newSources.length > 0 ? newSources : undefined, page: 1 });
                  }}
                  className="rounded border-border"
                />
                <span className="font-body text-sm text-ink">{SOURCE_LABEL[source]}</span>
              </label>
            ))}
          </div>
        </FilterPopover>

        <FilterPopover
          label="Created"
          active={!!(filters.created_from || filters.created_to)}
          count={filters.created_from || filters.created_to ? 1 : undefined}
        >
          <div className="space-y-2">
            <button
              type="button"
              onClick={() =>
                updateFilters({
                  ...filters,
                  created_from: undefined,
                  created_to: undefined,
                  page: 1,
                })
              }
              className="w-full rounded px-2 py-1.5 text-left font-body text-sm text-ink hover:bg-surface-subtle"
            >
              Any time
            </button>
            {["Last 7", "Last 30", "Last 90"].map((label, idx) => {
              const days = [7, 30, 90][idx];
              const from = new Date();
              from.setDate(from.getDate() - days);
              const fromIso = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(from);
              return (
                <button
                  key={label}
                  type="button"
                  onClick={() =>
                    updateFilters({
                      ...filters,
                      created_from: fromIso,
                      created_to: undefined,
                      page: 1,
                    })
                  }
                  className="w-full rounded px-2 py-1.5 text-left font-body text-sm text-ink hover:bg-surface-subtle"
                >
                  {label}
                </button>
              );
            })}
            <div className="space-y-1.5 border-t border-border pt-2">
              <label className="block">
                <span className="font-label text-[10px] font-bold uppercase text-ink-muted">From</span>
                <input
                  type="date"
                  value={filters.created_from || ""}
                  onChange={(e) =>
                    updateFilters({
                      ...filters,
                      created_from: e.target.value || undefined,
                      page: 1,
                    })
                  }
                  className="w-full rounded border border-border px-2 py-1.5 font-body text-sm"
                />
              </label>
              <label className="block">
                <span className="font-label text-[10px] font-bold uppercase text-ink-muted">To</span>
                <input
                  type="date"
                  value={filters.created_to || ""}
                  onChange={(e) =>
                    updateFilters({
                      ...filters,
                      created_to: e.target.value || undefined,
                      page: 1,
                    })
                  }
                  className="w-full rounded border border-border px-2 py-1.5 font-body text-sm"
                />
              </label>
            </div>
          </div>
        </FilterPopover>

        <FilterPopover
          label="Value"
          active={!!(filters.min_rupees || filters.max_rupees)}
          count={filters.min_rupees || filters.max_rupees ? 1 : undefined}
        >
          <div className="space-y-2">
            <label className="block">
              <span className="font-label text-[10px] font-bold uppercase text-ink-muted">Min ₹</span>
              <input
                type="number"
                value={filters.min_rupees ?? ""}
                onChange={(e) =>
                  updateFilters({
                    ...filters,
                    min_rupees: e.target.value ? parseInt(e.target.value, 10) : undefined,
                    page: 1,
                  })
                }
                placeholder="0"
                className="w-full rounded border border-border px-2 py-1.5 font-body text-sm"
              />
            </label>
            <label className="block">
              <span className="font-label text-[10px] font-bold uppercase text-ink-muted">Max ₹</span>
              <input
                type="number"
                value={filters.max_rupees ?? ""}
                onChange={(e) =>
                  updateFilters({
                    ...filters,
                    max_rupees: e.target.value ? parseInt(e.target.value, 10) : undefined,
                    page: 1,
                  })
                }
                placeholder="∞"
                className="w-full rounded border border-border px-2 py-1.5 font-body text-sm"
              />
            </label>
          </div>
        </FilterPopover>

        <FilterPopover
          label="Payment"
          active={(filters.payment_method?.length || 0) > 0}
          count={filters.payment_method?.length}
        >
          <div className="space-y-1.5">
            {(["razorpay", "cash", "upi", "card", "bank_transfer", "other"] as const).map((method) => (
              <label key={method} className="flex items-center gap-2.5 cursor-pointer px-2 py-1.5">
                <input
                  type="checkbox"
                  checked={filters.payment_method?.includes(method) || false}
                  onChange={(e) => {
                    const newMethods = e.target.checked
                      ? [...(filters.payment_method || []), method]
                      : (filters.payment_method || []).filter((m) => m !== method);
                    updateFilters({
                      ...filters,
                      payment_method: newMethods.length > 0 ? newMethods : undefined,
                      page: 1,
                    });
                  }}
                  className="rounded border-border"
                />
                <span className="font-body text-sm text-ink">{PAYMENT_LABEL[method]}</span>
              </label>
            ))}
          </div>
        </FilterPopover>

        {summary && summary.products.length > 0 && (
          <FilterPopover
            label="Product"
            active={(filters.product?.length || 0) > 0}
            count={filters.product?.length}
          >
            <div className="space-y-1.5 max-h-48 overflow-y-auto">
              {summary.products.map((product) => (
                <label key={product} className="flex items-center gap-2.5 cursor-pointer px-2 py-1.5">
                  <input
                    type="checkbox"
                    checked={filters.product?.includes(product) || false}
                    onChange={(e) => {
                      const newProducts = e.target.checked
                        ? [...(filters.product || []), product]
                        : (filters.product || []).filter((p) => p !== product);
                      updateFilters({
                        ...filters,
                        product: newProducts.length > 0 ? newProducts : undefined,
                        page: 1,
                      });
                    }}
                    className="rounded border-border"
                  />
                  <span className="font-body text-sm text-ink truncate">{product}</span>
                </label>
              ))}
            </div>
          </FilterPopover>
        )}

        <FilterPopover
          label="More"
          active={(filters.attention?.length || 0) > 0}
          count={filters.attention?.length}
        >
          <div className="space-y-1.5">
            {(["unpaid_3d", "link_expiring", "refund"] as const).map((att) => (
              <label key={att} className="flex items-center gap-2.5 cursor-pointer px-2 py-1.5">
                <input
                  type="checkbox"
                  checked={filters.attention?.includes(att) || false}
                  onChange={(e) => {
                    const newAttention = e.target.checked
                      ? [...(filters.attention || []), att]
                      : (filters.attention || []).filter((a) => a !== att);
                    updateFilters({
                      ...filters,
                      attention: newAttention.length > 0 ? newAttention : undefined,
                      page: 1,
                    });
                  }}
                  className="rounded border-border"
                />
                <span className="font-body text-sm text-ink">{ATTENTION_LABEL[att]}</span>
              </label>
            ))}
          </div>
        </FilterPopover>
      </div>

      {/* Views row - always show */}
      <div className="space-y-1.5 border-b border-border bg-surface-subtle px-5 py-2.5">
        <p className="font-label text-xs font-bold uppercase tracking-wide text-ink-muted">Views</p>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => updateFilters({ ...filters, view, page: 1 })}
            className={`inline-flex items-center rounded-full border px-3 py-1.5 font-body text-xs transition-all ${
              viewName["all-deals"]
                ? "border-primary bg-primary/10 text-primary"
                : "border-border text-ink hover:bg-white"
            }`}
          >
            All deals
          </button>

          <button
            type="button"
            onClick={() => updateFilters({ attention: ["unpaid_3d"], view, page: 1 })}
            className={`inline-flex items-center rounded-full border px-3 py-1.5 font-body text-xs transition-all ${
              viewName["unpaid-3d"]
                ? "border-primary bg-primary/10 text-primary"
                : "border-border text-ink hover:bg-white"
            }`}
          >
            Unpaid 3+ days
          </button>

          <button
            type="button"
            onClick={() => updateFilters({ min_rupees: 10000, view, page: 1 })}
            className={`inline-flex items-center rounded-full border px-3 py-1.5 font-body text-xs transition-all ${
              viewName["big-deals"]
                ? "border-primary bg-primary/10 text-primary"
                : "border-border text-ink hover:bg-white"
            }`}
          >
            Big deals ₹10k+
          </button>

          <button
            type="button"
            onClick={() => updateFilters({ source: ["indiamart"], view, page: 1 })}
            className={`inline-flex items-center rounded-full border px-3 py-1.5 font-body text-xs transition-all ${
              viewName["indiamart"]
                ? "border-primary bg-primary/10 text-primary"
                : "border-border text-ink hover:bg-white"
            }`}
          >
            IndiaMART
          </button>

          <button
            type="button"
            onClick={() => {
              const weekAgo = new Date();
              weekAgo.setDate(weekAgo.getDate() - 7);
              const weekAgoIso = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(weekAgo);
              updateFilters({ created_from: weekAgoIso, view, page: 1 });
            }}
            className={`inline-flex items-center rounded-full border px-3 py-1.5 font-body text-xs transition-all ${
              viewName["this-week"]
                ? "border-primary bg-primary/10 text-primary"
                : "border-border text-ink hover:bg-white"
            }`}
          >
            This week
          </button>

          {/* Active filter chips */}
          {activeKeys.map((key) => {
            const value = filters[key];
            if (!value) return null;

            if (key === "q" && typeof value === "string") {
              return (
                <button
                  key={key}
                  type="button"
                  onClick={() => updateFilters({ ...filters, q: undefined, page: 1 })}
                  className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-3 py-1.5 font-body text-xs text-primary"
                >
                  &quot;{value}&quot; ×
                </button>
              );
            }

            if (key === "source" && Array.isArray(value)) {
              return (
                <button
                  key={key}
                  type="button"
                  onClick={() => updateFilters({ ...filters, source: undefined, page: 1 })}
                  className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-3 py-1.5 font-body text-xs text-primary"
                >
                  {(value as string[]).map((s) => SOURCE_LABEL[s as DealSource]).join(", ")} ×
                </button>
              );
            }

            if (
              (key === "created_from" || key === "created_to") &&
              typeof value === "string"
            ) {
              if (key === "created_from") {
                return (
                  <button
                    key={key}
                    type="button"
                    onClick={() =>
                      updateFilters({
                        ...filters,
                        created_from: undefined,
                        created_to: undefined,
                        page: 1,
                      })
                    }
                    className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-3 py-1.5 font-body text-xs text-primary"
                  >
                    Created {value} to {filters.created_to || "∞"} ×
                  </button>
                );
              }
              return null;
            }

            if ((key === "min_rupees" || key === "max_rupees") && typeof value === "number") {
              if (key === "min_rupees") {
                return (
                  <button
                    key={key}
                    type="button"
                    onClick={() =>
                      updateFilters({
                        ...filters,
                        min_rupees: undefined,
                        max_rupees: undefined,
                        page: 1,
                      })
                    }
                    className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-3 py-1.5 font-body text-xs text-primary"
                  >
                    Value {value} to {filters.max_rupees || "∞"} ×
                  </button>
                );
              }
              return null;
            }

            if (key === "payment_method" && Array.isArray(value)) {
              return (
                <button
                  key={key}
                  type="button"
                  onClick={() => updateFilters({ ...filters, payment_method: undefined, page: 1 })}
                  className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-3 py-1.5 font-body text-xs text-primary"
                >
                  {(value as string[]).map((m) => PAYMENT_LABEL[m as PaymentMethod]).join(", ")} ×
                </button>
              );
            }

            if (key === "product" && Array.isArray(value)) {
              return (
                <button
                  key={key}
                  type="button"
                  onClick={() => updateFilters({ ...filters, product: undefined, page: 1 })}
                  className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-3 py-1.5 font-body text-xs text-primary"
                >
                  {value.join(", ")} ×
                </button>
              );
            }

            if (key === "attention" && Array.isArray(value)) {
              return (
                <button
                  key={key}
                  type="button"
                  onClick={() => updateFilters({ ...filters, attention: undefined, page: 1 })}
                  className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-3 py-1.5 font-body text-xs text-primary"
                >
                  {(value as string[]).map((a) => ATTENTION_LABEL[a as DealAttention]).join(", ")} ×
                </button>
              );
            }

            return null;
          })}

          {activeKeys.length > 0 && (
            <button
              type="button"
              onClick={() => updateFilters({ view, page: 1 })}
              className="font-body text-xs text-ink-muted hover:text-ink"
            >
              Clear all
            </button>
          )}
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-hidden">
        {view === "table" ? (
          <ListTab
            filters={filters}
            sort={filters.sort || "created_at"}
            dir={filters.dir || "desc"}
            page={filters.page || 1}
            onSortChange={(sort, dir) => updateFilters({ ...filters, sort, dir, page: 1 })}
            onPageChange={(page) => updateFilters({ ...filters, page })}
            onOpenDeal={onOpenDeal}
            reloadToken={reloadToken}
          />
        ) : (
          <BoardTab
            filters={filters}
            summary={summary}
            onOpenDeal={onOpenDeal}
            reloadToken={reloadToken}
          />
        )}
      </div>
    </div>
  );
}
