"use client";

import { useEffect, useState, type RefObject } from "react";

/** True once the window has scrolled past `threshold` pixels. */
export function useScrolled(threshold: number): boolean {
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const update = () => setScrolled(window.scrollY > threshold);
    update();
    window.addEventListener("scroll", update, { passive: true });
    return () => window.removeEventListener("scroll", update);
  }, [threshold]);
  return scrolled;
}

/** Calls `onAway` on a pointer press outside `ref` or on Escape, while `active`. */
export function useDismiss(ref: RefObject<HTMLElement>, active: boolean, onAway: (viaEscape: boolean) => void) {
  useEffect(() => {
    if (!active) return;
    const onPointer = (e: PointerEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onAway(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onAway(true);
    };
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [ref, active, onAway]);
}

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

/** Keeps Tab and Shift+Tab inside `ref` while `active`, and locks page scroll. */
export function useFocusTrap(ref: RefObject<HTMLElement>, active: boolean) {
  useEffect(() => {
    const root = ref.current;
    if (!active || !root) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Tab") return;
      const items = Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE));
      if (items.length === 0) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    const html = document.documentElement;
    const previousOverflow = html.style.overflow;
    html.style.overflow = "hidden";
    root.addEventListener("keydown", onKey);
    return () => {
      html.style.overflow = previousOverflow;
      root.removeEventListener("keydown", onKey);
    };
  }, [ref, active]);
}
