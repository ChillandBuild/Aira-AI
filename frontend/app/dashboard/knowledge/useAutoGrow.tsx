"use client";

import { useCallback, useEffect, useLayoutEffect, useRef } from "react";
import type { TextareaHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

/**
 * Grows a textarea to fit its content instead of clipping it inside a
 * fixed-height box with inner scrolling.
 *
 * Recalculates:
 * - on mount (so an already-filled section is full height immediately)
 * - whenever `value` changes (typing, or a parent overwriting the field —
 *   e.g. the Convert-to-sections modal filling these in)
 * - on window resize (narrower widths wrap the same text onto more lines)
 *
 * `minRows` sets a floor so a short/empty section still reads as a proper
 * text field. There is no cap — the box always grows to show the whole
 * text, per the requirement this hook exists for.
 */
export function useAutoGrow(value: string, minRows = 3) {
  const ref = useRef<HTMLTextAreaElement | null>(null);

  const resize = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    // Collapse first so scrollHeight reflects the content's real size
    // instead of whatever (possibly larger) height was set previously.
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight}px`;
  }, []);

  // Layout effect: resize before paint so there's no visible flash of the
  // wrong height when `value` changes (typing, load, or the Convert modal).
  useLayoutEffect(() => {
    resize();
  }, [value, resize]);

  useEffect(() => {
    window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
  }, [resize]);

  return { ref, minRows };
}

interface AutoGrowTextareaProps
  extends Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, "rows" | "value"> {
  value: string;
  /** Minimum visible rows before the box grows. Defaults to ~3 lines. */
  minRows?: number;
}

/**
 * Drop-in replacement for <textarea> that auto-grows to fit its content.
 * Manual resize (dragging the corner handle) still works; it's simply
 * overridden the next time `value` changes, which is harmless.
 */
export function AutoGrowTextarea({ value, minRows = 3, className, ...rest }: AutoGrowTextareaProps) {
  const { ref, minRows: rows } = useAutoGrow(value, minRows);

  return (
    <textarea
      ref={ref}
      value={value}
      rows={rows}
      className={cn("resize-y overflow-hidden", className)}
      {...rest}
    />
  );
}
