"use client";
import { useCallback, useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import { HandoverFeed } from "@/components/brain/HandoverFeed";
import { HeadlineStrip } from "@/components/brain/HeadlineStrip";
import { InputsList } from "@/components/brain/InputsList";
import { isOperatorBrainResponse, type OperatorBrainResponse } from "@/components/brain/operatorBrain";
import { operatorFetch } from "@/lib/operator";
import { SkeletonCard, SkeletonTable } from "../components/skeleton";
import type { SectionType } from "../sidebar";
import {
  FallbackSection,
  HistorySection,
  LaterPlaceholders,
  OperatorOnlyRows,
  StatusDetail,
  WaitingReadOnly,
} from "./brain-sections";

interface BrainViewProps {
  tenantId: string;
  /** Switches the client console to another view (used by "Open in Config"). */
  onOpenSection?: (section: SectionType) => void;
}

export function BrainView({ tenantId, onOpenSection }: BrainViewProps) {
  const [brain, setBrain] = useState<OperatorBrainResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const body: unknown = await operatorFetch<unknown>(`/api/v1/operator/clients/${tenantId}/brain`);
      if (!isOperatorBrainResponse(body)) throw new Error("Aira Brain sent an unexpected response.");
      setBrain(body);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load Aira Brain");
    } finally {
      setLoading(false);
    }
  }, [tenantId]);

  useEffect(() => { load(); }, [load]);

  if (loading && !brain) {
    return (
      <div className="space-y-6">
        <SkeletonCard />
        <SkeletonTable rows={4} />
        <SkeletonTable rows={3} />
      </div>
    );
  }

  if (error && !brain) {
    return <div className="p-4 bg-red-50 border border-danger/20 rounded-xl text-sm text-danger">{error}</div>;
  }

  if (!brain) return null;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <p className="font-body text-xs text-ink-secondary">Read-only view of what this client&apos;s Aira knows and how customers are being handled.</p>
        <button
          type="button"
          onClick={load}
          disabled={loading}
          className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-white px-3 py-1.5 font-label text-xs font-bold text-ink hover:bg-surface-mid disabled:opacity-50"
        >
          <RefreshCw size={12} className={loading ? "animate-spin" : ""} /> Refresh
        </button>
      </div>
      {error && <div className="p-3 bg-red-50 border border-danger/20 rounded-xl text-xs text-danger">{error}</div>}

      <HeadlineStrip headline={brain.headline} seeItHref={null} />
      <WaitingReadOnly waiting={brain.waiting} />
      <InputsList inputs={brain.inputs} readOnly />
      <HandoverFeed handovers={brain.handovers} readOnly />
      <StatusDetail status={brain.status} />
      <OperatorOnlyRows rows={brain.operator_rows} onOpenSection={onOpenSection && ((section) => onOpenSection(section as SectionType))} />
      <HistorySection history={brain.history} />
      <FallbackSection signals={brain.fallback_signals} />
      <LaterPlaceholders />
    </div>
  );
}
