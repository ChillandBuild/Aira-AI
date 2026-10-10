"use client";
import type { ReactNode } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

interface SidebarSectionProps {
  title: string;
  open: boolean;
  onToggle: () => void;
  children: ReactNode;
}

/** A product heading that folds its items open and shut. The parent renders it only when it has visible items. */
export function SidebarSection({ title, open, onToggle, children }: SidebarSectionProps) {
  return (
    <div className="space-y-0.5 pt-2 first:pt-0">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="flex items-center justify-between w-full px-3 pb-1 pt-1 rounded-md text-left font-label text-[10px] font-bold uppercase tracking-wider text-[#94a3b8] hover:text-[#0A1528] transition-colors"
      >
        <span className="truncate">{title}</span>
        {open ? <ChevronDown size={12} aria-hidden="true" /> : <ChevronRight size={12} aria-hidden="true" />}
      </button>
      {open && <div className="space-y-1.5">{children}</div>}
    </div>
  );
}
