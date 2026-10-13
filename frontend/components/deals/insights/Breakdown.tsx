"use client";
import { Check } from "lucide-react";
import { cn } from "@/lib/utils";
import { formatRupees } from "@/components/deals/money";
import { DealSource, DealStats } from "@/lib/api";
import { SOURCE_LABEL } from "@/lib/deal-filters";
import { plural, SOURCE_COLOR, SOURCE_ORDER } from "./shared";

function Card({ title, meta, children }: { title: string; meta?: string; children: React.ReactNode }) {
  return (
    <section className="min-w-0 rounded-2xl border border-[#e2e8f0] bg-white p-4 sm:p-5">
      <div className="flex items-baseline justify-between gap-2">
        <h2 className="text-sm font-extrabold text-[#0A1528]">{title}</h2>
        {meta && <span className="truncate text-xs font-semibold text-[#64748b]">{meta}</span>}
      </div>
      {children}
    </section>
  );
}

export function Breakdown({
  allSources,
  selected,
  onToggleSource,
  topItems,
  lowStock,
}: {
  /** Unfiltered — every source keeps its row while a filter is on. */
  allSources: DealStats["by_source"];
  selected: DealSource[];
  onToggleSource: (s: DealSource) => void;
  topItems: DealStats["top_items"];
  lowStock: DealStats["low_stock"];
}) {
  const rows = SOURCE_ORDER.filter((s) => allSources[s]?.count).map((s) => ({ source: s, ...allSources[s]! }));
  rows.sort((a, b) => b.total_paise - a.total_paise);
  const total = rows.reduce((sum, r) => sum + r.total_paise, 0);
  const filtered = selected.length > 0;

  return (
    <div className="grid grid-cols-1 gap-3.5 lg:grid-cols-3">
      <Card title="Where sales came from" meta={rows.length > 1 ? "click to filter" : undefined}>
        {rows.length === 0 ? (
          <p className="mt-2 text-sm text-[#64748b]">No won deals this month.</p>
        ) : (
          <>
            <div className="mb-2 mt-3 flex h-2.5 gap-0.5 overflow-hidden rounded-full">
              {rows.map((r) => (
                <i
                  key={r.source}
                  className="block h-full transition-opacity"
                  style={{
                    width: `${total ? (r.total_paise / total) * 100 : 0}%`,
                    background: SOURCE_COLOR[r.source],
                    opacity: filtered && !selected.includes(r.source) ? 0.25 : 1,
                  }}
                />
              ))}
            </div>
            {rows.map((r) => {
              const on = selected.includes(r.source);
              return (
                <button
                  key={r.source}
                  type="button"
                  onClick={() => onToggleSource(r.source)}
                  aria-pressed={on}
                  className={cn(
                    "-mx-2 flex w-[calc(100%+1rem)] items-center justify-between gap-2.5 rounded-lg px-2 py-1.5 text-left text-[13px] transition-colors",
                    on ? "bg-primary/10" : "hover:bg-[#f8fafc]"
                  )}
                >
                  <span className="flex min-w-0 items-center gap-2 font-semibold text-[#0A1528]">
                    <i className="h-2 w-2 shrink-0 rounded-[3px]" style={{ background: SOURCE_COLOR[r.source] }} />
                    <span className="truncate">{SOURCE_LABEL[r.source]}</span>
                    <span className="shrink-0 font-semibold text-[#64748b]">
                      {plural(r.count, "deal")} · {total ? Math.round((r.total_paise / total) * 100) : 0}%
                    </span>
                  </span>
                  <span className="flex shrink-0 items-center gap-1.5 font-extrabold tabular-nums text-[#0A1528]">
                    {formatRupees(r.total_paise)}
                    {on && <Check size={13} className="text-primary" />}
                  </span>
                </button>
              );
            })}
          </>
        )}
      </Card>

      <Card
        title="Top items"
        meta={filtered ? `from ${selected.map((s) => SOURCE_LABEL[s]).join(", ")}` : "by revenue"}
      >
        {topItems.length === 0 ? (
          <p className="mt-2 text-sm text-[#64748b]">
            {filtered ? `Nothing sold through ${selected.map((s) => SOURCE_LABEL[s]).join(" or ")} this month.` : "Nothing sold this month."}
          </p>
        ) : (
          <ol className="mt-2">
            {topItems.slice(0, 6).map((item, i) => (
              <li key={item.name} className="flex items-center justify-between gap-2.5 py-1.5 text-[13px]">
                <span className="flex min-w-0 items-center gap-2">
                  <span className="w-3 shrink-0 font-semibold text-[#94a3b8]">{i + 1}</span>
                  <span className="truncate font-semibold text-[#0A1528]" title={item.name}>
                    {item.name}
                  </span>
                  <span className="shrink-0 font-semibold text-[#64748b]">×{item.qty}</span>
                </span>
                <span className="shrink-0 font-extrabold tabular-nums text-[#0A1528]">{formatRupees(item.total_paise)}</span>
              </li>
            ))}
          </ol>
        )}
      </Card>

      <Card title="Stock" meta="all products">
        {lowStock.length === 0 ? (
          <p className="mt-3 flex items-center gap-2 text-sm text-[#64748b]">
            <span className="grid h-6 w-6 place-items-center rounded-full bg-emerald-50 text-emerald-500">
              <Check size={14} strokeWidth={3} />
            </span>
            Nothing running low.
          </p>
        ) : (
          <ul className="mt-2">
            {lowStock.map((item) => {
              const left = item.stock_quantity - item.held_quantity;
              return (
                <li key={item.id} className="flex items-center justify-between gap-2.5 py-1.5 text-[13px]">
                  <span className="truncate font-semibold text-[#0A1528]" title={item.name}>
                    {item.name}
                  </span>
                  <span
                    className={cn(
                      "shrink-0 rounded-full border px-2 py-0.5 text-[11px] font-bold tabular-nums",
                      left <= 0 ? "border-rose-200 bg-rose-50 text-rose-700" : "border-amber-200 bg-amber-50 text-amber-700"
                    )}
                  >
                    {left <= 0 ? "Out of stock" : `${left} left`}
                    {item.held_quantity > 0 && ` · ${item.held_quantity} held`}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </Card>
    </div>
  );
}
