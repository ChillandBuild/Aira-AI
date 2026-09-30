"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { checkNow, getReport } from "./consistencyApi";
import type { Report } from "./types";

interface Options {
  /** Only someone with knowledge.manage may POST /consistency/check. */
  canManage: boolean;
  /** Changes when the host wants a re-read (the hub bumps it after an approval). */
  reloadSignal: number;
}

export interface ConsistencyReportState {
  report: Report | null;
  isLoading: boolean;
  isChecking: boolean;
  error: string | null;
  load: () => Promise<void>;
  runCheck: () => Promise<void>;
}

/** Reads the report (latest response wins) and, for managers, checks once on its own when it is missing or stale. */
export function useConsistencyReport({ canManage, reloadSignal }: Options): ConsistencyReportState {
  const [report, setReport] = useState<Report | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isChecking, setIsChecking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const seqRef = useRef(0);
  const appliedSeqRef = useRef(0);
  const hasAutoChecked = useRef(false);
  const isMounted = useRef(true);

  useEffect(() => {
    isMounted.current = true;
    return () => {
      isMounted.current = false;
    };
  }, []);

  const load = useCallback(async () => {
    seqRef.current += 1;
    const seq = seqRef.current;
    try {
      const next = await getReport();
      if (!isMounted.current || seq < appliedSeqRef.current) return;
      appliedSeqRef.current = seq;
      setReport(next);
      setError(null);
    } catch (e) {
      if (isMounted.current) setError(e instanceof Error ? e.message : "Couldn't load. Please try again.");
    } finally {
      if (isMounted.current) setIsLoading(false);
    }
  }, []);

  const runCheck = useCallback(async () => {
    if (!canManage) return;
    setIsChecking(true);
    setError(null);
    try {
      const next = await checkNow();
      if (!isMounted.current) return;
      seqRef.current += 1;
      appliedSeqRef.current = seqRef.current;
      setReport(next);
    } catch (e) {
      if (isMounted.current) setError(e instanceof Error ? e.message : "Couldn't check right now. Please try again.");
    } finally {
      if (isMounted.current) setIsChecking(false);
    }
  }, [canManage]);

  // First read, and a re-read (with a fresh chance to auto-check) each time the host bumps reloadSignal.
  useEffect(() => {
    hasAutoChecked.current = false;
    void load();
  }, [load, reloadSignal]);

  useEffect(() => {
    if (!canManage || !report || hasAutoChecked.current) return;
    if (report.checked_at && !report.stale) return;
    hasAutoChecked.current = true;
    void runCheck();
  }, [canManage, report, runCheck]);

  return { report, isLoading, isChecking, error, load, runCheck };
}
