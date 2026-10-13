"use client";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { COMPARE_COLORS, MAX_COMPARE, monthKey, monthsText, parseMonth, SHORT_MONTHS } from "./shared";

/**
 * A popover with a caller-drawn trigger. Portalled to <body> for the same reason as
 * FilterPopover: the dashboard content wrapper clips anything that overflows it.
 */
export function Popover({
  trigger,
  children,
  align = "left",
}: {
  trigger: (open: boolean, toggle: () => void) => React.ReactNode;
  children: (close: () => void) => React.ReactNode;
  align?: "left" | "right";
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);

  useLayoutEffect(() => {
    if (!open) return;
    function place() {
      const rect = ref.current?.getBoundingClientRect();
      if (!rect) return;
      const width = panelRef.current?.offsetWidth ?? 260;
      const wanted = align === "right" ? rect.right - width : rect.left;
      setPos({ top: rect.bottom + 6, left: Math.max(8, Math.min(wanted, window.innerWidth - width - 8)) });
    }
    place();
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    return () => {
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
    };
  }, [open, align]);

  useEffect(() => {
    if (!open) return;
    function outside(e: MouseEvent) {
      const target = e.target as Node;
      if (ref.current?.contains(target) || panelRef.current?.contains(target)) return;
      setOpen(false);
    }
    function escape(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", outside);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("mousedown", outside);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);

  return (
    <div ref={ref} className="relative shrink-0">
      {trigger(open, () => setOpen((o) => !o))}
      {open &&
        createPortal(
          <div
            ref={panelRef}
            style={{ top: pos?.top ?? 0, left: pos?.left ?? 0, visibility: pos ? "visible" : "hidden" }}
            className="fixed z-50 rounded-2xl border border-[#e2e8f0] bg-white p-2 shadow-lg"
          >
            {children(() => setOpen(false))}
          </div>,
          document.body
        )}
    </div>
  );
}

/** Year header with ‹ › and a 3×4 grid of months. Months after `max` can't be picked. */
export function MonthGrid({
  value,
  max,
  activeMonths,
  onPick,
}: {
  value: string | null;
  max: string;
  activeMonths: Set<string>;
  onPick: (month: string) => void;
}) {
  const [year, setYear] = useState(() => parseMonth(value ?? max).year);
  const maxYear = parseMonth(max).year;

  return (
    <div className="w-[248px]">
      <div className="flex items-center justify-between px-1 pb-2">
        <button
          type="button"
          onClick={() => setYear((y) => y - 1)}
          aria-label="Previous year"
          className="grid h-7 w-7 place-items-center rounded-lg text-[#334155] hover:bg-slate-50"
        >
          <ChevronLeft size={15} />
        </button>
        <span className="text-sm font-extrabold tabular-nums text-[#0A1528]">{year}</span>
        <button
          type="button"
          onClick={() => setYear((y) => y + 1)}
          disabled={year >= maxYear}
          aria-label="Next year"
          className="grid h-7 w-7 place-items-center rounded-lg text-[#334155] hover:bg-slate-50 disabled:text-slate-300 disabled:hover:bg-transparent"
        >
          <ChevronRight size={15} />
        </button>
      </div>
      <div className="grid grid-cols-3 gap-1">
        {SHORT_MONTHS.map((name, i) => {
          const key = monthKey(year, i + 1);
          const blocked = key > max;
          const selected = key === value;
          return (
            <button
              key={key}
              type="button"
              disabled={blocked}
              onClick={() => onPick(key)}
              className={cn(
                "relative rounded-lg py-2 text-xs font-bold transition-colors",
                selected ? "bg-primary text-white" : "text-[#0A1528] hover:bg-slate-50",
                blocked && "cursor-not-allowed text-slate-300 hover:bg-transparent"
              )}
            >
              {name}
              {activeMonths.has(key) && (
                <span
                  className={cn(
                    "absolute bottom-1 left-1/2 h-1 w-1 -translate-x-1/2 rounded-full",
                    selected ? "bg-white" : "bg-primary"
                  )}
                />
              )}
            </button>
          );
        })}
      </div>
      <p className="mt-2 flex items-center gap-1.5 px-1 text-[11px] text-[#64748b]">
        <span className="h-1 w-1 rounded-full bg-primary" /> had sales
      </p>
    </div>
  );
}

/**
 * Tick up to MAX_COMPARE months to compare with. Year chips jump straight to a year
 * (the current one, last year, and any year that had sales); nothing applies until "Compare".
 */
export function CompareGrid({
  picked,
  max,
  exclude,
  activeMonths,
  onApply,
}: {
  picked: string[];
  max: string;
  exclude: string;
  activeMonths: Set<string>;
  onApply: (months: string[]) => void;
}) {
  const maxYear = parseMonth(max).year;
  const [draft, setDraft] = useState<string[]>(picked);
  const [year, setYear] = useState(() => parseMonth([...picked].sort().pop() ?? max).year);
  const years = Array.from(
    new Set([maxYear, maxYear - 1, ...Array.from(activeMonths).concat(picked).map((m) => parseMonth(m).year)])
  ).sort((a, b) => b - a);
  const full = draft.length >= MAX_COMPARE;
  const unchanged = draft.length === picked.length && draft.every((m) => picked.includes(m));

  function toggle(key: string) {
    setDraft((d) => (d.includes(key) ? d.filter((m) => m !== key) : d.length < MAX_COMPARE ? [...d, key] : d));
  }

  return (
    <div className="w-[264px]">
      <div className="flex flex-wrap gap-1 px-0.5 pb-2" role="group" aria-label="Year">
        {years.map((y) => {
          const count = draft.filter((m) => parseMonth(m).year === y).length;
          return (
            <button
              key={y}
              type="button"
              onClick={() => setYear(y)}
              aria-pressed={year === y}
              className={cn(
                "relative rounded-full border px-3 py-1 text-xs font-bold tabular-nums transition-colors",
                year === y ? "border-[#0A1528] bg-[#0A1528] text-white" : "border-[#e2e8f0] text-[#334155] hover:border-slate-300"
              )}
            >
              {y}
              {count > 0 && year !== y && (
                <span className="absolute -right-1 -top-1 grid h-3.5 w-3.5 place-items-center rounded-full bg-primary text-[9px] text-white">
                  {count}
                </span>
              )}
            </button>
          );
        })}
      </div>

      <div className="grid grid-cols-3 gap-1">
        {SHORT_MONTHS.map((name, i) => {
          const key = monthKey(year, i + 1);
          const index = draft.indexOf(key);
          const on = index >= 0;
          const blocked = key > max || key === exclude || (!on && full);
          return (
            <button
              key={key}
              type="button"
              disabled={blocked}
              onClick={() => toggle(key)}
              aria-pressed={on}
              title={key === exclude ? "This is the month you're viewing" : !on && full ? `You can compare up to ${MAX_COMPARE} months` : undefined}
              className={cn(
                "relative flex items-center justify-center gap-1 rounded-lg border py-2 text-xs font-bold transition-colors",
                on ? "border-primary bg-primary/10 text-primary" : "border-transparent text-[#0A1528] hover:bg-slate-50",
                blocked && "cursor-not-allowed text-slate-300 hover:bg-transparent"
              )}
            >
              {on && <i className="h-2 w-2 rounded-full" style={{ background: COMPARE_COLORS[index] }} />}
              {name}
              {activeMonths.has(key) && !on && (
                <span className={cn("absolute bottom-1 left-1/2 h-1 w-1 -translate-x-1/2 rounded-full", blocked ? "bg-slate-300" : "bg-primary")} />
              )}
            </button>
          );
        })}
      </div>

      <div className="mt-2 flex items-center justify-between gap-2 px-1">
        <span className="min-w-0 truncate text-[11px] text-[#64748b]">
          {full ? `${MAX_COMPARE} of ${MAX_COMPARE} picked · untick one to swap` : draft.length ? monthsText(draft) : (
            <span className="flex items-center gap-1.5"><span className="h-1 w-1 rounded-full bg-primary" /> had sales · pick up to {MAX_COMPARE}</span>
          )}
        </span>
        {draft.length > 0 && (
          <button type="button" onClick={() => setDraft([])} className="shrink-0 text-[11px] font-bold text-[#64748b] hover:text-[#0A1528]">
            Clear
          </button>
        )}
      </div>
      <button
        type="button"
        disabled={draft.length === 0 || unchanged}
        onClick={() => onApply(draft)}
        className="mt-2 w-full rounded-xl bg-primary py-2 text-xs font-bold text-white transition-opacity hover:bg-primary/90 disabled:opacity-40"
      >
        {draft.length > 1 ? `Compare with these ${draft.length} months` : "Compare"}
      </button>
    </div>
  );
}
