import Link from "next/link";
import { timeAgo } from "@/lib/utils";
import { handoverAction, type HandoverAction } from "./brainLogic";
import { SectionCard } from "./SectionCard";
import { ROW_BUTTON_CLASS, ROW_LINK_CLASS } from "./WaitingRow";
import type { BrainHandover, HandoverKind } from "./types";

const KIND_LABEL: Record<HandoverKind, string> = {
  asked_for_human: "Asked for a person",
  knowledge_gap: "Gap in what Aira knows",
  payment: "Payment problem",
  other: "Other",
};

const ADD_ANSWER_HREF = "/dashboard/knowledge?tab=documents";

function chatHref(leadId: string): string {
  return `/dashboard/conversations?lead=${encodeURIComponent(leadId)}`;
}

function HandoverActionView({ action }: { action: HandoverAction }) {
  if (action.kind === "none") return null;
  if (action.kind === "no_inbox_access") {
    return <p className="mt-2 font-body text-xs text-ink-muted">Chat details need inbox access</p>;
  }
  return (
    <div className="mt-2">
      {action.kind === "add_answer" ? (
        <Link href={ADD_ANSWER_HREF} className={ROW_BUTTON_CLASS}>
          Add an answer
        </Link>
      ) : (
        <Link href={chatHref(action.leadId)} className={ROW_LINK_CLASS}>
          Open the chat
        </Link>
      )}
    </div>
  );
}

function HandoverRow({ handover, readOnly }: { handover: BrainHandover; readOnly: boolean }) {
  return (
    <li className="min-w-0 rounded-xl border border-border-subtle bg-surface-low px-3 py-2.5">
      <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
        <span className="rounded-full bg-primary-50 px-2 py-0.5 font-label text-[10px] font-bold text-primary">
          {KIND_LABEL[handover.kind] ?? KIND_LABEL.other}
        </span>
        <span className="font-body text-[11px] text-ink-muted">{timeAgo(handover.opened_at)}</span>
      </div>
      <p className="mt-1 break-words font-body text-sm text-ink">{handover.reason}</p>
      <p className="mt-1 break-words font-body text-xs text-ink-secondary">
        <span className="font-bold">Likely message: </span>
        {handover.likely_question ? (
          <span>&ldquo;{handover.likely_question}&rdquo;</span>
        ) : (
          <span className="text-ink-muted">not available for this one</span>
        )}
      </p>
      <HandoverActionView action={handoverAction(handover, readOnly)} />
    </li>
  );
}

/** readOnly (operator console): the client-dashboard action links are left out. */
export function HandoverFeed({ handovers, readOnly = false }: { handovers: BrainHandover[]; readOnly?: boolean }) {
  return (
    <SectionCard title="Why customers reached a human" subtitle="Recent chats Aira passed to your team.">
      {handovers.length === 0 ? (
        <p className="font-body text-sm text-ink-secondary">No customers have needed a human recently.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {handovers.map((handover) => (
            <HandoverRow key={handover.handover_id} handover={handover} readOnly={readOnly} />
          ))}
        </ul>
      )}
    </SectionCard>
  );
}
