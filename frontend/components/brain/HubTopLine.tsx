import Link from "next/link";
import { CheckCircle2, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";
import { topLineText, type MainAction } from "./brainLogic";

interface HubTopLineProps {
  waitingCount: number;
  action: MainAction;
  onOpenReview: (reviewId: string) => void;
}

const ACTION_CLASS =
  "inline-flex min-h-10 items-center justify-center rounded-xl bg-primary px-4 font-label text-sm font-bold text-white transition hover:bg-primary-dark focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40";

function ActionControl({ action, onOpenReview }: { action: MainAction; onOpenReview: (id: string) => void }) {
  if (action.kind === "review") {
    return (
      <button type="button" className={ACTION_CLASS} onClick={() => onOpenReview(action.reviewId)}>
        {action.label}
      </button>
    );
  }
  if (action.kind === "anchor") {
    return (
      <a href={`#${action.anchor}`} className={ACTION_CLASS}>
        {action.label}
      </a>
    );
  }
  return (
    <Link href={action.href} className={ACTION_CLASS}>
      {action.label}
    </Link>
  );
}

export function HubTopLine({ waitingCount, action, onOpenReview }: HubTopLineProps) {
  const isReady = waitingCount <= 0;
  const Icon = isReady ? CheckCircle2 : AlertTriangle;
  return (
    <div
      className={cn(
        "flex min-w-0 flex-wrap items-center justify-between gap-3 rounded-2xl border p-4 sm:p-5",
        isReady ? "border-emerald-200 bg-emerald-50/60" : "border-amber-200 bg-amber-50/60",
      )}
    >
      <div className="flex min-w-0 items-center gap-3">
        <span
          className={cn(
            "flex h-9 w-9 shrink-0 items-center justify-center rounded-full",
            isReady ? "bg-emerald-100 text-success" : "bg-amber-100 text-warning",
          )}
        >
          <Icon size={18} aria-hidden />
        </span>
        <p aria-live="polite" className="min-w-0 break-words font-display text-lg font-extrabold text-ink sm:text-xl">
          {topLineText(waitingCount)}
        </p>
      </div>
      <ActionControl action={action} onOpenReview={onOpenReview} />
    </div>
  );
}
