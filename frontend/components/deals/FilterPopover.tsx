"use client";
import { useEffect, useRef, useState } from "react";
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

  useEffect(() => {
    if (!open) return;
    function handleClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
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

      {open && (
        <div
          onClick={closeOnPick ? () => setOpen(false) : undefined}
          className="absolute left-0 top-full z-30 mt-1 min-w-[220px] rounded-xl border border-[#e2e8f0] bg-white p-1.5 shadow-lg"
        >
          {children}
        </div>
      )}
    </div>
  );
}
