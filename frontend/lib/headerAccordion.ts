"use client";
import { useSyncExternalStore } from "react";

/**
 * Bridge between a settings <SettingsAccordion> and the app header.
 *
 * The section count and the expand/collapse-all control belong in the header
 * chrome, not stacked above the cards — but the accordion owns that state and
 * lives several routes below <AppHeader>. An external store keeps the two in
 * sync without a provider around the whole dashboard: publishing re-renders
 * only the header, not every page below it.
 */
export type HeaderAccordionState = {
  /** Number of registered sections — the header only shows itself above 1. */
  count: number;
  /** How many are currently expanded. */
  openCount: number;
  allOpen: boolean;
  toggleAll: () => void;
};

let snapshot: HeaderAccordionState | null = null;
const listeners = new Set<() => void>();

/** Called by the accordion on mount/state change; null clears the header. */
export function publishHeaderAccordion(next: HeaderAccordionState | null) {
  snapshot = next;
  listeners.forEach((l) => l());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

const getSnapshot = () => snapshot;
const getServerSnapshot = () => null;

export function useHeaderAccordion() {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}
