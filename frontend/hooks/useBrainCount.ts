"use client";

import { useEffect, useSyncExternalStore } from "react";
import { API_URL, getAuthHeaders } from "@/lib/api";
import {
  INITIAL_COUNT_STATE,
  badgeCount,
  nextCountState,
  type CountState,
  type PollResult,
} from "@/components/brain/brainLogic";
import { APPROVALS_CHANGED_EVENT } from "@/components/brain/approvalsEvent";

// One module-level store and one timer, shared by every component that shows the
// Aira Brain badge (sidebar rail, sidebar list, More menu). Each caller passes its
// own gate; polling runs while at least one gate is open and stops when none is.

const POLL_INTERVAL_MS = 60_000;
const COUNT_URL = `${API_URL}/api/v1/brain/count`;

let state: CountState = INITIAL_COUNT_STATE;
let retainers = 0;
let timer: ReturnType<typeof setInterval> | null = null;
let requestSeq = 0;
// Bumped whenever polling stops, so a request still in flight cannot repopulate
// the store after the last subscriber left (or for the next user in this tab).
let generation = 0;
const listeners = new Set<() => void>();

function emit(): void {
  listeners.forEach((listener) => listener());
}

function commit(next: CountState): void {
  if (next === state) return;
  state = next;
  emit();
}

async function fetchCount(seq: number): Promise<PollResult> {
  try {
    const auth = await getAuthHeaders();
    const res = await fetch(COUNT_URL, { headers: auth });
    if (!res.ok) return { seq, ok: false, status: res.status };
    return { seq, ok: true, data: await res.json() };
  } catch {
    // Network error or unreadable body: same as any failed poll, keep the last value.
    return { seq, ok: false };
  }
}

async function poll(): Promise<void> {
  const startedIn = generation;
  requestSeq += 1;
  const result = await fetchCount(requestSeq);
  if (startedIn !== generation) return;
  commit(nextCountState(state, result));
}

function onApprovalsChanged(): void {
  void poll();
}

function retain(): () => void {
  retainers += 1;
  if (retainers === 1) {
    void poll();
    timer = setInterval(() => void poll(), POLL_INTERVAL_MS);
    window.addEventListener(APPROVALS_CHANGED_EVENT, onApprovalsChanged);
  }
  let released = false;
  return () => {
    if (released) return;
    released = true;
    retainers -= 1;
    if (retainers > 0) return;
    if (timer !== null) clearInterval(timer);
    timer = null;
    window.removeEventListener(APPROVALS_CHANGED_EVENT, onApprovalsChanged);
    generation += 1;
    commit(INITIAL_COUNT_STATE);
  };
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

const getSnapshot = (): CountState => state;
const getServerSnapshot = (): CountState => INITIAL_COUNT_STATE;

/**
 * The number of things waiting on the client, or null when there is nothing to
 * show: gate closed, before the first success, after a 403/404, or a count of 0.
 * Hooks order: call this above any early return in the caller.
 */
export function useBrainCount(enabled: boolean): number | null {
  useEffect(() => {
    if (!enabled) return;
    return retain();
  }, [enabled]);

  const current = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  return enabled ? badgeCount(current) : null;
}
