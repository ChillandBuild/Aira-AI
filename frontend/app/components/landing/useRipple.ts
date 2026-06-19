"use client";

import { useCallback } from "react";

/**
 * Returns a pointer-down handler that spawns a water-ripple inside the target
 * element, emanating from the click point. The host element must have
 * `position: relative; overflow: hidden` and the `.ripple-host` class
 * (styled in landing.css). Self-cleaning — the span removes itself on
 * animation end.
 */
export function useRipple() {
  return useCallback((e: React.PointerEvent<HTMLElement>) => {
    const host = e.currentTarget;
    const rect = host.getBoundingClientRect();
    const size = Math.max(rect.width, rect.height);
    const ripple = document.createElement("span");
    ripple.className = "ripple-ink";
    ripple.style.width = ripple.style.height = `${size}px`;
    ripple.style.left = `${e.clientX - rect.left - size / 2}px`;
    ripple.style.top = `${e.clientY - rect.top - size / 2}px`;
    ripple.addEventListener("animationend", () => ripple.remove());
    host.appendChild(ripple);
  }, []);
}
