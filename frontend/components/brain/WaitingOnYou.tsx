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
  isOwner: boolean;
  /** Bumped after an approval; the conflicts panel re-reads when it changes. */
  panelKey: number;
  /** The conflicts panel changed something (fix, dismiss, restore): announce it so the count and the hub reload. */
  onConflictsChanged: () => void;
  onOpenReview: (reviewId: string) => void;
}

function GroupLabel({ id, children }: { id?: string; children: string }) {
  return (
    <h3 id={id} className="scroll-mt-20 pb-1.5 font-label text-[11px] font-bold uppercase tracking-wider text-ink-muted">
      {children}
    </h3>
  );
}

export function WaitingOnYou({ waiting, canManage, isOwner, panelKey, onConflictsChanged, onOpenReview }: WaitingOnYouProps) {
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

        <div id={ANCHOR_CONFLICTS} className="scroll-mt-20">
          <ConsistencyPanel
            embedded
            canManage={canManage}
            isOwner={isOwner}
            reloadSignal={panelKey}
            onChanged={onConflictsChanged}
          />
        </div>

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
