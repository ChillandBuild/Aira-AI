"use client";

import { useEffect, useState } from "react";

interface MotionPrefs {
  reducedMotion: boolean;
  coarsePointer: boolean;
}

/**
 * Detects reduced-motion preference and coarse (touch) pointers so each
 * landing animation can pick its own fallback. SSR-safe: starts "calm"
 * (reducedMotion=true) until the client confirms, avoiding a motion flash.
 */
export function useReducedMotion(): MotionPrefs {
  const [prefs, setPrefs] = useState<MotionPrefs>({
    reducedMotion: true,
    coarsePointer: false,
  });

  useEffect(() => {
    const motionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    const pointerQuery = window.matchMedia("(pointer: coarse)");

    const sync = () =>
      setPrefs({
        reducedMotion: motionQuery.matches,
        coarsePointer: pointerQuery.matches,
      });

    sync();
    motionQuery.addEventListener("change", sync);
    pointerQuery.addEventListener("change", sync);
    return () => {
      motionQuery.removeEventListener("change", sync);
      pointerQuery.removeEventListener("change", sync);
    };
  }, []);

  return prefs;
}
