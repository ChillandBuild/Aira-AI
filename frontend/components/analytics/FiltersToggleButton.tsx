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
          ? "border-violet-200 bg-violet-50 text-violet-700 hover:bg-violet-100"
          : "border-surface-mid bg-white text-on-surface hover:border-violet-300 hover:text-violet-700"
      )}
    >
      <Filter size={12} />
      <span>Filters</span>
    </button>
  );
}
