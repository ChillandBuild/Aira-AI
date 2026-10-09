"use client";
import { useEffect, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";

interface FilterPopoverProps {
  label: string;
  active: boolean;
  count?: number;
  children: React.ReactNode;
}

export function FilterPopover({ label, active, count, children }: FilterPopoverProps) {
  const [open, setOpen] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (
        panelRef.current &&
        !panelRef.current.contains(e.target as Node) &&
        buttonRef.current &&
        !buttonRef.current.contains(e.target as Node)
      ) {
        setOpen(false);
      }
    }

    if (open) {
      document.addEventListener("mousedown", handleClickOutside);
      return () => document.removeEventListener("mousedown", handleClickOutside);
    }
  }, [open]);

  useEffect(() => {
    function handleEscape(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }

    if (open) {
      document.addEventListener("keydown", handleEscape);
      return () => document.removeEventListener("keydown", handleEscape);
    }
  }, [open]);

  return (
    <div className="relative inline-block">
      <button
        ref={buttonRef}
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-haspopup="true"
        className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 font-label text-xs font-bold transition-all ${
          active
            ? "border-primary bg-primary/10 text-primary"
            : "border-dashed border-border text-ink-muted hover:text-ink"
        }`}
      >
        {label}
        {count !== undefined && count > 0 && <span className="text-primary"> · {count}</span>}
        <ChevronDown size={14} className={`transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div
          ref={panelRef}
          className="absolute left-0 top-full z-30 mt-1.5 min-w-[220px] rounded-xl border border-border bg-white p-2 shadow-lg"
        >
          {children}
        </div>
      )}
    </div>
  );
}
