"use client";
import { useState } from "react";
import { Lock } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

export type ToggleState = "on" | "off" | "locked" | "metered";

interface Usage {
  used: number;
  included: number;
}

interface EntitlementToggleProps {
  checked: boolean;
  onChange: (next: boolean) => void;
  label: string;
  priceLabel?: string;
  state?: ToggleState;
  usage?: Usage;
  disabled?: boolean;
  size?: "sm" | "md";
}

const METERED_COLORS = {
  warning: (usage: Usage) => usage.included > 0 && usage.used >= usage.included * 0.8,
  danger: (usage: Usage) => usage.included > 0 && usage.used >= usage.included,
};

export function EntitlementToggle({
  checked,
  onChange,
  label,
  priceLabel,
  state = "on",
  usage,
  disabled = false,
  size = "md",
}: EntitlementToggleProps) {
  const [isHovered, setIsHovered] = useState(false);
  const prefersReducedMotion = typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const trackClasses = cn(
    "relative inline-flex items-center rounded-full transition-colors duration-200",
    size === "md" ? "h-6 w-11" : "h-5 w-9",
    state === "locked" && "cursor-not-allowed",
    state === "on" && "bg-gradient-to-r from-primary to-violet-500",
    state === "off" && "bg-ink-muted/20",
    state === "locked" && "bg-ink-muted/10",
    state === "metered" && "bg-gradient-to-r from-primary to-violet-500",
    disabled && "cursor-not-allowed opacity-50",
    !prefersReducedMotion && state === "on" && "shadow-[0_0_12px_rgba(91,33,182,0.15)]"
  );

  const knobStyle = prefersReducedMotion
    ? {}
    : {
        transform: checked ? (size === "md" ? "translateX(20px)" : "translateX(16px)") : "translateX(0)",
        transition: "transform 0.3s cubic-bezier(.34,1.56,.64,1)",
      };

  const handleClick = () => {
    if (disabled || state === "locked" || state === "metered") return;
    onChange(!checked);
  };

  const progress = usage && usage.included > 0
    ? Math.min(1, Math.max(0, usage.used / usage.included))
    : 0;
  const strokeColor = usage && METERED_COLORS.danger(usage)
    ? "#dc2626"
    : usage && METERED_COLORS.warning(usage)
    ? "#d97706"
    : "#059669";

  // Proportional progress ring geometry (r=8 within a 24x24 viewBox).
  const RING_RADIUS = 8;
  const RING_CIRCUMFERENCE = 2 * Math.PI * RING_RADIUS;
  const ringOffset = RING_CIRCUMFERENCE * (1 - progress);

  const showMeteredRing = state === "metered" && !!usage;
  const showCheck = checked && !showMeteredRing;

  return (
    <div className="flex items-center gap-3">
      <div
        className={trackClasses}
        onClick={handleClick}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
      >
        <div
          className={cn(
            "rounded-full bg-white shadow-md flex items-center justify-center overflow-hidden",
            size === "md" ? "h-5 w-5" : "h-4 w-4"
          )}
          style={knobStyle}
        >
          {showMeteredRing ? (
            <svg
              className={cn(size === "md" ? "h-3.5 w-3.5" : "h-3 w-3")}
              viewBox="0 0 24 24"
              fill="none"
            >
              {/* Track */}
              <circle
                cx="12"
                cy="12"
                r={RING_RADIUS}
                stroke="currentColor"
                className="text-ink-muted/25"
                strokeWidth="3"
              />
              {/* Proportional progress arc — starts at 12 o'clock, fills clockwise */}
              <circle
                cx="12"
                cy="12"
                r={RING_RADIUS}
                stroke={strokeColor}
                strokeWidth="3"
                strokeLinecap="round"
                strokeDasharray={RING_CIRCUMFERENCE}
                strokeDashoffset={ringOffset}
                transform="rotate(-90 12 12)"
                style={prefersReducedMotion ? undefined : { transition: "stroke-dashoffset 0.4s ease, stroke 0.2s ease" }}
              />
            </svg>
          ) : showCheck ? (
            <svg
              className={cn(
                "text-primary transition-opacity",
                size === "md" ? "h-3 w-3" : "h-2.5 w-2.5"
              )}
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="3"
            >
              <polyline points="20 6 9 17 4 12" />
            </svg>
          ) : null}
        </div>
        {state === "locked" && (
          <svg
            className={cn(
              "absolute inset-0 w-full h-full text-ink-muted/40 pointer-events-none",
              size === "md" ? "p-1.5" : "p-1"
            )}
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
          >
            <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
            <path d="M7 11V7a5 5 0 0 1 10 0v4" />
          </svg>
        )}
      </div>
      
      <span className="text-sm text-ink-secondary flex-1">{label}</span>
      
      {priceLabel && (
        <span
          className={cn(
            "text-xs px-2 py-0.5 rounded-full bg-primary-light text-primary font-medium whitespace-nowrap",
            !prefersReducedMotion && "transition-all duration-300 ease-out",
            isHovered
              ? "opacity-100 translate-x-0"
              : prefersReducedMotion
              ? "opacity-90"
              : "opacity-0 translate-x-1"
          )}
        >
          {priceLabel}
        </span>
      )}
    </div>
  );
}


export function EntitlementCard({
  icon: Icon,
  name,
  description,
  price,
  state,
  checked,
  onToggle,
  usage,
  dependencyNote,
}: {
  icon: LucideIcon;
  name: string;
  description: string;
  price: string;
  state: ToggleState;
  checked: boolean;
  onToggle: (checked: boolean) => void;
  usage?: Usage;
  dependencyNote?: string;
}) {
  const locked = state === "locked";
  return (
    <div className={cn(
      "bg-white rounded-card border border-border p-4 shadow-sm transition-shadow",
      locked ? "opacity-75" : "hover:shadow-md"
    )}>
      <div className="flex items-start gap-3 mb-3">
        <div className={cn(
          "relative flex h-10 w-10 shrink-0 items-center justify-center rounded-xl",
          locked ? "bg-surface-mid text-ink-muted" : "bg-primary-light text-primary"
        )}>
          <Icon size={20} />
          {locked && (
            <span className="absolute -bottom-1 -right-1 flex h-4 w-4 items-center justify-center rounded-full bg-ink-muted text-white ring-2 ring-white">
              <Lock size={9} strokeWidth={2.5} />
            </span>
          )}
        </div>
        <div className="min-w-0 flex-1">
          <h4 className={cn("text-sm font-semibold", locked ? "text-ink-secondary" : "text-ink")}>{name}</h4>
          <p className="text-xs text-ink-muted mt-1">{description}</p>
        </div>
      </div>
      
      <EntitlementToggle
        checked={checked}
        onChange={onToggle}
        label=""
        priceLabel={price}
        state={state}
        usage={usage}
      />
      
      {dependencyNote && (
        <p className="text-xs text-ink-muted mt-2">{dependencyNote}</p>
      )}
    </div>
  );
}