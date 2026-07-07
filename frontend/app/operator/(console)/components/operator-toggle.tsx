"use client";
/**
 * OperatorToggle — the operator console's standard switch control.
 * Reimplemented as a modern segmented pill selector matching settings style.
 */
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

interface OperatorToggleProps {
  checked: boolean;
  onChange: (next: boolean) => void;
  disabled?: boolean;
  loading?: boolean;
  size?: "sm" | "md";
  "aria-label": string;
}

export function OperatorToggle({
  checked,
  onChange,
  disabled = false,
  loading = false,
  size = "md",
  "aria-label": ariaLabel,
}: OperatorToggleProps) {
  const inactive = disabled || loading;

  const handleToggle = (target: boolean) => {
    if (inactive) return;
    if (checked !== target) {
      onChange(target);
    }
  };

  const buttonPadding = size === "sm" ? "px-2 py-0.5 text-[10px]" : "px-3 py-0.5 text-xs";

  return (
    <div
      role="group"
      aria-label={ariaLabel}
      className={cn(
        "relative inline-flex p-0.5 rounded-full bg-border-subtle/80 border border-border/40 select-none shrink-0",
        inactive && "opacity-50 cursor-not-allowed"
      )}
    >
      <button
        type="button"
        disabled={inactive}
        onClick={() => handleToggle(false)}
        className={cn(
          "relative z-10 font-label font-bold rounded-full transition-all duration-300",
          buttonPadding,
          !checked && !loading
            ? "bg-white text-ink shadow-[0_2px_8px_rgba(28,25,23,0.06)]"
            : "text-ink-muted hover:text-ink",
          inactive && "cursor-not-allowed"
        )}
      >
        {loading && !checked ? (
          <Loader2 className="h-3 w-3 animate-spin text-ink-muted inline-block" strokeWidth={3} />
        ) : (
          "Off"
        )}
      </button>
      <button
        type="button"
        disabled={inactive}
        onClick={() => handleToggle(true)}
        className={cn(
          "relative z-10 font-label font-bold rounded-full transition-all duration-300",
          buttonPadding,
          checked && !loading
            ? "bg-gradient-to-r from-primary to-violet-500 text-white shadow-[0_2px_8px_rgba(91,33,182,0.2)]"
            : "text-ink-muted hover:text-ink",
          inactive && "cursor-not-allowed"
        )}
      >
        {loading && checked ? (
          <Loader2 className="h-3 w-3 animate-spin text-white inline-block" strokeWidth={3} />
        ) : (
          "On"
        )}
      </button>
    </div>
  );
}
