"use client";
/**
 * OperatorToggle — the operator console's standard switch control.
 * A thin wrapper over the shared SwitchPill so the console and the tenant
 * dashboard can never drift apart; it only adds the console's `loading`
 * behaviour and its size vocabulary.
 */
import { SwitchPill } from "@/components/ui/controls";

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
  return (
    <SwitchPill
      on={checked}
      onChange={onChange}
      disabled={disabled}
      loading={loading}
      size={size}
      aria-label={ariaLabel}
    />
  );
}
