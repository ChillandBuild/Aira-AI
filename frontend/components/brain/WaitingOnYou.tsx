"use client";

import Link from "next/link";
import { ConsistencyPanel } from "@/components/ConsistencyPanel";
import { timeAgo } from "@/lib/utils";
import { ANCHOR_CONFLICTS, ANCHOR_FAILED, ANCHOR_TEMPLATES } from "./brainLogic";
import { FailedFileRow } from "./FailedFileRow";
import { SectionCard } from "./SectionCard";
import { ROW_BUTTON_CLASS, ROW_LINK_CLASS, WaitingRow } from "./WaitingRow";
import type { BrainWaiting } from "./types";

interface WaitingOnYouProps {
  waiting: BrainWaiting;
  canManage: boolean;
  /** Managers only: the conflicts panel checks itself on load, which needs knowledge.manage. */
  canAutoCheck: boolean;
  /** Remounts the conflicts panel so it re-reads after an approval. */
  panelKey: number;
  onOpenReview: (reviewId: string) => void;
}

function GroupLabel({ id, children }: { id?: string; children: string }) {
  return (
    <h3 id={id} className="scroll-mt-20 pb-1.5 font-label text-[11px] font-bold uppercase tracking-wider text-ink-muted">
      {children}
    </h3>
  );
}

function ConflictsBlock({ waiting, canAutoCheck, panelKey }: Pick<WaitingOnYouProps, "waiting" | "canAutoCheck" | "panelKey">) {
  if (canAutoCheck) {
    return (
      <div id={ANCHOR_CONFLICTS} className="scroll-mt-20">
        <ConsistencyPanel key={panelKey} />
      </div>
    );
  }
  if (waiting.consistency_count === 0) return null;
  const n = waiting.consistency_count;
  return (
    <div id={ANCHOR_CONFLICTS} className="scroll-mt-20 rounded-xl border border-amber-200 bg-amber-50/60 px-3.5 py-2.5">
      <p className="font-body text-xs text-ink">
        {n} {n === 1 ? "thing disagrees" : "things disagree"} with your Services page.
      </p>
      <p className="font-body text-[11px] text-ink-secondary">Someone with manage access can fix this.</p>
    </div>
  );
}

export function WaitingOnYou({ waiting, canManage, canAutoCheck, panelKey, onOpenReview }: WaitingOnYouProps) {
  const rejected = waiting.rejected_templates;
  return (
    <SectionCard title="Waiting on you" subtitle="Things Aira can't finish without you.">
      <div className="flex flex-col gap-4">
        {waiting.count === 0 && (
          <p className="font-body text-sm text-ink-secondary">Nothing is waiting on you.</p>
        )}

        {waiting.sort_reviews.length > 0 && (
          <div>
            <GroupLabel>Sorted files to review</GroupLabel>
            <ul className="flex flex-col gap-2">
              {waiting.sort_reviews.map((review) => (
                <WaitingRow key={review.id} title={review.title} meta={`Sorted ${timeAgo(review.created_at)}`}>
                  <button type="button" className={ROW_BUTTON_CLASS} onClick={() => onOpenReview(review.id)}>
                    Review
                  </button>
                </WaitingRow>
              ))}
            </ul>
          </div>
        )}

        <ConflictsBlock waiting={waiting} canAutoCheck={canAutoCheck} panelKey={panelKey} />

        {waiting.failed_files.length > 0 && (
          <div>
            <GroupLabel id={ANCHOR_FAILED}>Files that failed to sort</GroupLabel>
            <ul className="flex flex-col gap-2">
              {waiting.failed_files.map((file) => (
                <FailedFileRow key={file.id} file={file} canManage={canManage} />
              ))}
            </ul>
          </div>
        )}

        {rejected.length > 0 && (
          <div>
            <GroupLabel id={ANCHOR_TEMPLATES}>Templates WhatsApp rejected</GroupLabel>
            <ul className="flex flex-col gap-2">
              {rejected.map((template, index) => (
                <WaitingRow key={template.id ?? index} title={template.name ?? "A message template"} meta="Rejected by WhatsApp">
                  <Link href="/dashboard/templates" className={ROW_LINK_CLASS}>
                    Open templates
                  </Link>
                </WaitingRow>
              ))}
            </ul>
          </div>
        )}
      </div>
    </SectionCard>
  );
}
