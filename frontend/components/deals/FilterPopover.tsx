"use client";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

interface FilterPopoverProps {
  label: string;
  /** What the button shows after the label, e.g. "All" or "WhatsApp, Form". */
  value: string;
  active: boolean;
  /** Close the panel after a pick — for single-choice menus. */
  closeOnPick?: boolean;
  children: React.ReactNode;
}

// Same trigger look as the Segments page's FilterMenu ("Source: All ▾"), but the
// panel holds any content so a filter can take several ticks.
export function FilterPopover({ label, value, active, closeOnPick = false, children }: FilterPopoverProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);

  // The panel is portalled to <body> with fixed coordinates: the dashboard's content
  // wrapper (ClientLayout) has overflow-x-hidden — which also clips vertically — and
  // is only as tall as the page, so an in-place panel was cut off when the list was short.
  useLayoutEffect(() => {
    if (!open) return;
    function place() {
      const rect = ref.current?.getBoundingClientRect();
      if (!rect) return;
      const width = panelRef.current?.offsetWidth ?? 220;
      setPos({ top: rect.bottom + 4, left: Math.max(8, Math.min(rect.left, window.innerWidth - width - 8)) });
    }
    place();
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    return () => {
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function handleClickOutside(e: MouseEvent) {
      const target = e.target as Node;
      if (ref.current?.contains(target) || panelRef.current?.contains(target)) return;
      setOpen(false);
    }
    function handleEscape(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleEscape);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleEscape);
    };
  }, [open]);

  return (
    <div ref={ref} className="relative shrink-0">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-haspopup="true"
        title={`${label}: ${value}`}
        className={cn(
          "flex shrink-0 items-center gap-1 whitespace-nowrap rounded-lg border px-2.5 py-1.5 text-xs font-bold transition-colors",
          active
            ? "border-primary bg-primary/5 text-primary"
            : "border-[#e2e8f0] bg-white text-[#0A1528] hover:border-slate-300"
        )}
      >
        <span className="max-w-[130px] truncate">
          {label}: {value}
        </span>
        <ChevronDown size={12} className={cn("transition-transform", open && "rotate-180")} />
      </button>

      {open &&
        createPortal(
          <div
            ref={panelRef}
            onClick={closeOnPick ? () => setOpen(false) : undefined}
            style={{ top: pos?.top ?? 0, left: pos?.left ?? 0, visibility: pos ? "visible" : "hidden" }}
            className="fixed z-50 min-w-[220px] rounded-xl border border-[#e2e8f0] bg-white p-1.5 shadow-lg"
          >
            {children}
          </div>,
          document.body
        )}
    </div>
  );
}
