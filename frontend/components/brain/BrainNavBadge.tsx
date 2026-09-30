import { cn } from "@/lib/utils";

export type BrainBadgeVariant = "rail" | "row" | "menu";

// Same look as the Inbox badge: a small orange dot with a count on the collapsed
// rail, an orange-100 pill in the expanded list. "menu" reuses the pill for the
// mobile More drawer.
const VARIANT_CLASS: Record<BrainBadgeVariant, string> = {
  rail: "flex items-center justify-center w-4 h-4 rounded-full bg-orange-600 text-white text-[10px] font-bold min-w-[16px]",
  row: "flex-shrink-0 px-1.5 py-0.5 rounded-full bg-orange-100 text-orange-600 font-bold text-[9px] min-w-[16px] text-center",
  menu: "ml-auto flex-shrink-0 px-1.5 py-0.5 rounded-full bg-orange-100 text-orange-600 font-bold text-[10px] min-w-[18px] text-center",
};

const MAX_SHOWN = 9;

interface BrainNavBadgeProps {
  /** null or 0 draws nothing. */
  count: number | null;
  variant: BrainBadgeVariant;
}

export function BrainNavBadge({ count, variant }: BrainNavBadgeProps) {
  if (count === null || count <= 0) return null;
  const text = variant === "rail" && count > MAX_SHOWN ? `${MAX_SHOWN}+` : String(count);
  return (
    <span className={cn(VARIANT_CLASS[variant])} aria-label={`${count} waiting`}>
      {text}
    </span>
  );
}
