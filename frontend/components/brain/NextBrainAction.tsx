import Link from "next/link";
import { ArrowRight, AlertTriangle, MessageSquare } from "lucide-react";
import { cn } from "@/lib/utils";
import { nextBrainStep } from "./nextStep";
import type { BrainResponse } from "./types";

export function NextBrainAction({ brain, onSelect, readOnly = false, canManageSettings = false, activeSection }: {
  brain: BrainResponse;
  onSelect: (section: string) => void;
  readOnly?: boolean;
  canManageSettings?: boolean;
  activeSection?: string;
}) {
  const step = nextBrainStep(brain);
  const directHref = !readOnly && canManageSettings ? step.href : undefined;
  const actionClass = "inline-flex min-h-11 items-center gap-2 rounded-xl bg-primary px-4 font-label text-sm font-bold text-white hover:bg-primary-dark focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2";
  const Icon = step.needsAttention ? AlertTriangle : MessageSquare;
  return (
    <section aria-label="Recommended next step" className={cn("flex min-w-0 flex-wrap items-start justify-between gap-4 rounded-2xl border p-4 sm:p-5", step.needsAttention ? "border-amber-200 bg-amber-50/60" : "border-border bg-white")}>
      <div className="flex min-w-0 flex-1 basis-64 items-start gap-3">
        <Icon size={20} aria-hidden className={cn("mt-0.5 shrink-0", step.needsAttention ? "text-warning" : "text-primary")} />
        <div className="min-w-0">
          <h2 className="font-display text-lg font-extrabold text-ink">{step.title}</h2>
          <p className="mt-1 max-w-prose font-body text-sm text-ink-secondary">{step.detail}</p>
          {readOnly && step.needsAttention && <p className="mt-2 font-body text-xs text-ink-secondary">Client settings and approvals are read-only here; the client makes these changes in their dashboard.</p>}
        </div>
      </div>
      {directHref ? (
        <Link href={directHref} className={actionClass}>{step.label}<ArrowRight size={15} aria-hidden /></Link>
      ) : activeSection !== step.section ? (
        <button type="button" onClick={() => onSelect(step.section)} className={actionClass}>
          {step.href ? "View reply settings" : step.label}<ArrowRight size={15} aria-hidden />
        </button>
      ) : null}
    </section>
  );
}
