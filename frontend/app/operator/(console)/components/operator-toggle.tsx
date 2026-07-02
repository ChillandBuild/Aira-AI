"use client";
/**
 * OperatorToggle — the operator console's standard switch control.
 *
 * Design choice: rather than a stock rounded pill with a blank sliding dot,
 * the knob itself carries a morphing glyph — a hollow "power" ring when off
 * that cross-fades and rotates into a solid check when on, riding the same
 * spring easing (`cubic-bezier(.34,1.56,.64,1)`) and violet gradient/glow
 * vocabulary as `EntitlementToggle` so the two feel like one family. The
 * glyph morph (rotate + opacity swap, not just a color change) is the
 * deliberate signature that makes this read as custom rather than a
 * default `<Switch>`. Loading state replaces the glyph with a spinner and
 * suspends the glow/gradient to signal "in flight". All motion is skipped
 * under `prefers-reduced-motion`.
 */
import { useEffect, useState } from "react";
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

const TRACK_SIZE = {
  md: "h-6 w-11",
  sm: "h-5 w-9",
};

const KNOB_SIZE = {
  md: "h-5 w-5",
  sm: "h-4 w-4",
};

const KNOB_TRAVEL = {
  md: 20,
  sm: 16,
};

const GLYPH_SIZE = {
  md: "h-3 w-3",
  sm: "h-2.5 w-2.5",
};

export function OperatorToggle({
  checked,
  onChange,
  disabled = false,
  loading = false,
  size = "md",
  "aria-label": ariaLabel,
}: OperatorToggleProps) {
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(false);
  const inactive = disabled || loading;

  useEffect(() => {
    const mql = window.matchMedia("(prefers-reduced-motion: reduce)");
    setPrefersReducedMotion(mql.matches);
    const handler = (e: MediaQueryListEvent) => setPrefersReducedMotion(e.matches);
    mql.addEventListener("change", handler);
    return () => mql.removeEventListener("change", handler);
  }, []);

  const handleClick = () => {
    if (inactive) return;
    onChange(!checked);
  };

  const knobStyle = prefersReducedMotion
    ? {}
    : {
        transform: checked ? `translateX(${KNOB_TRAVEL[size]}px)` : "translateX(0)",
        transition: "transform 0.3s cubic-bezier(.34,1.56,.64,1)",
      };

  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={ariaLabel}
      aria-busy={loading || undefined}
      disabled={inactive}
      onClick={handleClick}
      className={cn(
        "relative inline-flex shrink-0 items-center rounded-full",
        !prefersReducedMotion && "transition-colors duration-200",
        TRACK_SIZE[size],
        checked && !loading
          ? "bg-gradient-to-r from-primary to-violet-500"
          : "bg-ink-muted/25",
        !prefersReducedMotion && checked && !loading && "shadow-[0_0_12px_rgba(91,33,182,0.15)]",
        inactive ? "cursor-not-allowed opacity-50" : "cursor-pointer",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-surface"
      )}
    >
      <span
        className={cn(
          "flex items-center justify-center rounded-full bg-white shadow-md overflow-hidden",
          KNOB_SIZE[size]
        )}
        style={knobStyle}
      >
        {loading ? (
          <Loader2 className={cn(GLYPH_SIZE[size], "animate-spin text-ink-muted")} strokeWidth={3} />
        ) : (
          <span className="relative flex items-center justify-center h-full w-full">
            {/* Off glyph: hollow power ring */}
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="3"
              strokeLinecap="round"
              className={cn(
                GLYPH_SIZE[size],
                "absolute text-ink-muted",
                !prefersReducedMotion && "transition-all duration-200 ease-out",
                checked
                  ? "opacity-0 scale-50 rotate-45"
                  : "opacity-100 scale-100 rotate-0"
              )}
            >
              <path d="M12 2v6" />
              <path d="M18.36 6.64a9 9 0 1 1-12.73 0" />
            </svg>
            {/* On glyph: check */}
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="3"
              strokeLinecap="round"
              strokeLinejoin="round"
              className={cn(
                GLYPH_SIZE[size],
                "absolute text-primary",
                !prefersReducedMotion && "transition-all duration-200 ease-out",
                checked
                  ? "opacity-100 scale-100 rotate-0"
                  : "opacity-0 scale-50 -rotate-45"
              )}
            >
              <polyline points="20 6 9 17 4 12" />
            </svg>
          </span>
        )}
      </span>
    </button>
  );
}
