"use client";

import { useState } from "react";
import { AlertTriangle, Loader2 } from "lucide-react";
import { useAuthRole } from "@/app/dashboard/contexts/AuthRoleContext";
import KnowledgeReviewModal from "@/app/dashboard/knowledge/KnowledgeReviewModal";
import { announceApprovalsChanged } from "@/components/brain/approvalsEvent";
import { pickMainAction } from "@/components/brain/brainLogic";
import { CanReply } from "@/components/brain/CanReply";
import { HandoverFeed } from "@/components/brain/HandoverFeed";
import { HeadlineStrip } from "@/components/brain/HeadlineStrip";
import { HubTopLine } from "@/components/brain/HubTopLine";
import { InputsList } from "@/components/brain/InputsList";
import { useBrainData } from "@/components/brain/useBrainData";
import { WaitingOnYou } from "@/components/brain/WaitingOnYou";

function LoadingState() {
  return (
    <div className="flex flex-col gap-4" aria-busy="true" aria-label="Loading Aira Brain">
      {[64, 48, 160, 200].map((height) => (
        <div key={height} className="animate-pulse rounded-2xl bg-border-subtle" style={{ height }} aria-hidden />
      ))}
    </div>
  );
}

function ErrorState({ message, isRetrying, onRetry }: { message: string; isRetrying: boolean; onRetry: () => void }) {
  return (
    <div role="alert" className="flex flex-col items-start gap-3 rounded-2xl border border-rose-200 bg-rose-50/60 p-4 sm:p-5">
      <div className="flex min-w-0 items-start gap-2.5">
        <AlertTriangle size={16} className="mt-0.5 shrink-0 text-danger" aria-hidden />
        <p className="min-w-0 break-words font-body text-sm text-ink">{message}</p>
      </div>
      <button
        type="button"
        onClick={onRetry}
        disabled={isRetrying}
        className="inline-flex min-h-9 items-center rounded-lg border border-border bg-white px-3 font-label text-xs font-bold text-ink hover:border-primary/40 disabled:opacity-50"
      >
        {isRetrying && <Loader2 size={12} className="mr-1.5 animate-spin" aria-hidden />}
        Try again
      </button>
    </div>
  );
}

export default function AiraBrainPage() {
  const { role, permissions, loading: roleLoading } = useAuthRole();
  const canView = role === "owner" || permissions.includes("knowledge.view") || permissions.includes("knowledge.manage");
  const canManage = role === "owner" || permissions.includes("knowledge.manage");
  const isOwner = role === "owner";

  const { data, error, isLoading, isRetrying, panelKey, retry } = useBrainData(canView);
  const [reviewingDocumentId, setReviewingDocumentId] = useState<string | null>(null);

  function openReview(reviewId: string): void {
    const review = data?.waiting.sort_reviews.find((r) => r.id === reviewId);
    if (review) setReviewingDocumentId(review.document_id);
  }

  // The modal's handlers only announce; the hub and the sidebar badge both listen
  // for the event, so there is one path from "approved" to "reloaded".
  function closeReview(): void {
    setReviewingDocumentId(null);
    announceApprovalsChanged();
  }

  if (roleLoading) return <LoadingState />;

  if (!canView) {
    return (
      <div className="mx-auto max-w-3xl rounded-2xl border border-border bg-white p-5">
        <p className="font-body text-sm text-ink-secondary">You don&apos;t have access to Aira Brain.</p>
      </div>
    );
  }

  return (
    <>
      <div className="mx-auto flex min-w-0 max-w-3xl flex-col gap-4">
        {isLoading && <LoadingState />}
        {!isLoading && error && data === null && <ErrorState message={error} isRetrying={isRetrying} onRetry={retry} />}
        {data && (
          <>
            <HubTopLine
              waitingCount={data.waiting.count}
              action={pickMainAction(data.waiting)}
              onOpenReview={openReview}
            />
            <HeadlineStrip headline={data.headline} />
            <WaitingOnYou
              waiting={data.waiting}
              canManage={canManage}
              isOwner={isOwner}
              panelKey={panelKey}
              onConflictsChanged={announceApprovalsChanged}
              onOpenReview={openReview}
            />
            <HandoverFeed handovers={data.handovers} />
            <InputsList inputs={data.inputs} />
            <CanReply status={data.status} />
          </>
        )}
      </div>

      {/* Outside the flex column on purpose: a fixed overlay inside a gap/space container gets pushed off the top edge. */}
      {reviewingDocumentId && (
        <KnowledgeReviewModal
          documentId={reviewingDocumentId}
          canManage={canManage}
          isOwner={isOwner}
          onClose={() => setReviewingDocumentId(null)}
          onFinished={closeReview}
          onResorted={closeReview}
        />
      )}
    </>
  );
}
