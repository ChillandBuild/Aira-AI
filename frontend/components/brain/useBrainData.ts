"use client";

import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { APPROVALS_CHANGED_EVENT } from "./approvalsEvent";
import { getBrain } from "./brainApi";
import { initialLatestState, reduceLatest, type LatestAction, type LatestState } from "./brainLogic";
import type { BrainResponse } from "./types";

// An approval can create a new conflict in the background (blueprint section 12),
// so the hub reloads right away and again after this delay.
const RECHECK_DELAY_MS = 8_000;

type BrainState = LatestState<BrainResponse>;

function brainReducer(state: BrainState, action: LatestAction<BrainResponse>): BrainState {
  return reduceLatest(state, action);
}

export interface BrainData {
  data: BrainResponse | null;
  error: string | null;
  isLoading: boolean;
  isRetrying: boolean;
  /** Changes on every approval-driven reload; use as a React key to remount the conflicts panel. */
  panelKey: number;
  retry: () => void;
}

export function useBrainData(enabled: boolean): BrainData {
  const [state, dispatch] = useReducer(brainReducer, undefined, initialLatestState<BrainResponse>);
  const [panelKey, setPanelKey] = useState(0);
  const [isRetrying, setIsRetrying] = useState(false);
  const seqRef = useRef(0);
  const isMountedRef = useRef(true);
  const recheckTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = useCallback(async (): Promise<void> => {
    seqRef.current += 1;
    const seq = seqRef.current;
    try {
      const data = await getBrain();
      if (isMountedRef.current) dispatch({ type: "success", seq, data });
    } catch (e) {
      const message = e instanceof Error ? e.message : "Couldn't load Aira Brain. Please try again.";
      if (isMountedRef.current) dispatch({ type: "failure", seq, message });
    }
  }, []);

  const reloadAfterApproval = useCallback(() => {
    void load();
    setPanelKey((k) => k + 1);
    if (recheckTimerRef.current !== null) clearTimeout(recheckTimerRef.current);
    recheckTimerRef.current = setTimeout(() => {
      recheckTimerRef.current = null;
      void load();
      setPanelKey((k) => k + 1);
    }, RECHECK_DELAY_MS);
  }, [load]);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      if (recheckTimerRef.current !== null) clearTimeout(recheckTimerRef.current);
    };
  }, []);

  useEffect(() => {
    if (!enabled) return;
    void load();
  }, [enabled, load]);

  useEffect(() => {
    if (!enabled) return;
    window.addEventListener(APPROVALS_CHANGED_EVENT, reloadAfterApproval);
    return () => window.removeEventListener(APPROVALS_CHANGED_EVENT, reloadAfterApproval);
  }, [enabled, reloadAfterApproval]);

  const retry = useCallback(() => {
    setIsRetrying(true);
    void load().finally(() => {
      if (isMountedRef.current) setIsRetrying(false);
    });
  }, [load]);

  return {
    data: state.data,
    error: state.error,
    isLoading: enabled && state.data === null && state.error === null,
    isRetrying,
    panelKey,
    retry,
  };
}
