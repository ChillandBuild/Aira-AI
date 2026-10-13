"use client";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
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

const PANEL_WIDTH = 220;

// Same trigger look as the Segments page's FilterMenu ("Source: All ▾"), but the
// panel holds any content so a filter can take several ticks. The panel is fixed to
// the viewport so a sideways-scrolling filter strip can't clip it.
export function FilterPopover({ label, value, active, closeOnPick = false, children }: FilterPopoverProps) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);
  const ref = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    if (!open || !buttonRef.current) return;
    const rect = buttonRef.current.getBoundingClientRect();
    setPos({
      top: rect.bottom + 4,
      left: Math.max(8, Math.min(rect.left, window.innerWidth - PANEL_WIDTH - 8)),
    });
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function handleClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    function handleEscape(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    // The panel is pinned to where the button was; any outside scroll would leave it floating.
    function handleScroll(e: Event) {
      if (panelRef.current && panelRef.current.contains(e.target as Node)) return;
      setOpen(false);
    }
    function handleResize() {
      setOpen(false);
    }
    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleEscape);
    window.addEventListener("scroll", handleScroll, true);
    window.addEventListener("resize", handleResize);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleEscape);
      window.removeEventListener("scroll", handleScroll, true);
      window.removeEventListener("resize", handleResize);
    };
  }, [open]);

  return (
    <div ref={ref} className="relative shrink-0">
      <button
        ref={buttonRef}
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-haspopup="true"
        title={`${label}: ${value}`}
        className={cn(
          "flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-lg border px-2.5 py-1.5 text-xs font-bold transition-colors",
          active
            ? "border-primary bg-primary/5 text-primary"
            : "border-[#e2e8f0] bg-white text-[#0A1528] hover:border-slate-300"
        )}
      >
        <span className="max-w-[180px] truncate">
          {label}: {value}
        </span>
        <ChevronDown size={14} className={cn("transition-transform", open && "rotate-180")} />
      </button>

      {open && pos && (
        <div
          ref={panelRef}
          onClick={closeOnPick ? () => setOpen(false) : undefined}
          style={{ top: pos.top, left: pos.left, minWidth: PANEL_WIDTH }}
          className="fixed z-30 rounded-xl border border-[#e2e8f0] bg-white p-1.5 shadow-lg"
        >
          {children}
        </div>
      )}
    </div>
  );
}
