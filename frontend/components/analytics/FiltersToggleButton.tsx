"use client";

import { Filter } from "lucide-react";
import { cn } from "@/lib/utils";

export function FiltersToggleButton({
  open,
  active,
  onClick,
}: {
  open: boolean;
  active?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "flex w-full items-center justify-center gap-2 rounded-xl border px-3 py-2 font-label text-xs font-bold shadow-sm transition-all",
        open || active
          ? "border-primary-200 bg-primary-50 text-primary-700 hover:bg-primary-100"
          : "border-surface-mid bg-white text-on-surface hover:border-primary-300 hover:text-primary-700"
      )}
    >
      <Filter size={12} />
      <span>Filters</span>
    </button>
  );
}
