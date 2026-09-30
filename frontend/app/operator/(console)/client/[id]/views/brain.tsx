"use client";
import { useCallback, useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import { NextBrainAction } from "@/components/brain/NextBrainAction";
import { BrainWorkspace } from "@/components/brain/BrainWorkspace";
import { HandoverFeed } from "@/components/brain/HandoverFeed";
import { HeadlineStrip } from "@/components/brain/HeadlineStrip";
import { InputsList } from "@/components/brain/InputsList";
import { TestAira } from "@/components/brain/TestAira";
import { isOperatorBrainResponse, type OperatorBrainResponse } from "@/components/brain/operatorBrain";
import { operatorFetch } from "@/lib/operator";
import { SkeletonCard, SkeletonTable } from "../components/skeleton";
import type { SectionType } from "../sidebar";
import {
  FallbackSection,
  HistorySection,
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
  const [activeSection, setActiveSection] = useState("overview");
  const [brain, setBrain] = useState<OperatorBrainResponse | null>(null);
  const [refreshedAt, setRefreshedAt] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const body: unknown = await operatorFetch<unknown>(`/api/v1/operator/clients/${tenantId}/brain`);
      if (!isOperatorBrainResponse(body)) throw new Error("Aira Brain sent an unexpected response.");
      setBrain(body);
      setRefreshedAt(new Date().toISOString());
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
        <p className="font-body text-xs text-ink-secondary">Read-only client settings and approvals; Test Aira is available here.
          {refreshedAt && <> Status loaded at <time dateTime={refreshedAt}>{new Date(refreshedAt).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit", timeZone: "Asia/Kolkata" })} IST</time>.</>}</p>
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

      <NextBrainAction brain={brain} onSelect={setActiveSection} activeSection={activeSection} readOnly />
      <BrainWorkspace key={tenantId} activeId={activeSection} onSelect={setActiveSection} sections={[
        { id: "overview", label: "Overview", description: "Client activity and reply readiness at a glance.", content: <><HeadlineStrip headline={brain.headline} seeItHref={null} /><StatusDetail status={brain.status} />{brain.operator_rows.some((row) => row.state === "missing" || row.state === "attention") && <div className="rounded-xl bg-amber-50 p-4"><p className="font-body text-sm text-ink">Platform configuration also needs attention. Check the missing or flagged settings before relying on replies.</p><button type="button" onClick={() => setActiveSection("operations")} className="mt-2 min-h-10 font-label text-sm font-bold text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary">Check operations</button></div>}</> },
        { id: "approvals", label: "Needs attention", description: "Items waiting for the client to review or fix.", count: brain.waiting.count, content: <WaitingReadOnly waiting={brain.waiting} /> },
        { id: "knowledge", label: "What Aira knows", description: "The information this client has given Aira.", content: <InputsList inputs={brain.inputs} readOnly /> },
        { id: "handovers", label: "Handovers", description: "Conversations that needed a person and fallback signals.", content: <><HandoverFeed handovers={brain.handovers} readOnly /><FallbackSection signals={brain.fallback_signals} /></> },
        { id: "operations", label: "Operations", description: "Operator configuration checks and recent history.", content: <><OperatorOnlyRows rows={brain.operator_rows} onOpenSection={onOpenSection && ((section) => onOpenSection(section as SectionType))} /><HistorySection history={brain.history} /><div className="rounded-xl bg-surface-low p-4"><h2 className="font-display text-sm font-extrabold text-ink">Inspect a customer’s context</h2><p className="mt-1 font-body text-sm text-ink-secondary">Open a conversation in Inbox and select “What Aira saw” to reconstruct the information Aira would see now.</p>{onOpenSection && <button type="button" onClick={() => onOpenSection("conversations")} className="mt-2 min-h-10 font-label text-sm font-bold text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary">Open Inbox</button>}</div></> },
        { id: "test", label: "Test Aira", description: "Try a customer message using this client’s Aira.", content: <TestAira key={tenantId} endpoint={`/api/v1/operator/clients/${tenantId}/brain/sandbox`} canUse /> },
      ]} />
    </div>
  );
}
