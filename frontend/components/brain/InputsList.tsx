"use client";

import Link from "next/link";
import { useId } from "react";
import { cn } from "@/lib/utils";
import { SectionCard } from "./SectionCard";
import { ROW_LINK_CLASS } from "./WaitingRow";
import type { BrainInput, InputSection, InputState } from "./types";

const STATE_LABEL: Record<InputState, string> = {
  ok: "Set",
  missing: "Missing",
  off: "Off",
  attention: "Needs attention",
};

const STATE_CLASS: Record<InputState, string> = {
  ok: "bg-emerald-50 text-success",
  missing: "bg-amber-50 text-warning",
  off: "bg-surface-mid text-ink-secondary",
  attention: "bg-rose-50 text-danger",
};

const FALLBACK_REASON = "You don't have access to edit this.";

function SectionDots({ sections }: { sections: InputSection[] }) {
  const filledCount = sections.filter((s) => s.filled).length;
  return (
    <div className="mt-1.5">
      <ul className="flex flex-wrap gap-x-3 gap-y-1" aria-label={`${filledCount} of ${sections.length} sections filled`}>
        {sections.map((section) => (
          <li key={section.key} className="flex items-center gap-1 font-body text-[11px] text-ink-secondary">
            <span
              aria-hidden
              className={cn(
                "h-2 w-2 shrink-0 rounded-full border",
                section.filled ? "border-success bg-success" : "border-ink-muted bg-transparent",
              )}
            />
            <span>{section.label}</span>
            <span className="sr-only">{section.filled ? "filled" : "empty"}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function EditControl({ input, reasonId }: { input: BrainInput; reasonId: string }) {
  if (input.can_edit) {
    return (
      <Link href={input.edit_href} className={ROW_LINK_CLASS}>
        Edit
      </Link>
    );
  }
  return (
    <span
      role="link"
      aria-disabled="true"
      aria-describedby={reasonId}
      className="font-label text-xs font-bold text-ink-muted"
    >
      Edit
    </span>
  );
}

function InputRow({ input, readOnly }: { input: BrainInput; readOnly: boolean }) {
  const reasonId = useId();
  return (
    <li className="min-w-0 rounded-xl border border-border-subtle bg-surface-low px-3 py-2.5">
      <div className="flex min-w-0 flex-wrap items-center justify-between gap-x-3 gap-y-1.5">
        <div className="min-w-0 flex-1 basis-40">
          <p className="break-words font-body text-sm font-semibold text-ink">{input.label}</p>
          <p className="break-words font-body text-xs text-ink-secondary">{input.detail}</p>
        </div>
        <div className="flex shrink-0 items-center gap-3">
          <span className={cn("rounded-full px-2 py-0.5 font-label text-[10px] font-bold", STATE_CLASS[input.state])}>
            {STATE_LABEL[input.state]}
          </span>
          {!readOnly && <EditControl input={input} reasonId={reasonId} />}
        </div>
      </div>
      {input.sections && input.sections.length > 0 && <SectionDots sections={input.sections} />}
      {input.flag && <p className="mt-1 break-words font-body text-[11px] text-warning">{input.flag}</p>}
      {!readOnly && !input.can_edit && (
        <p id={reasonId} className="mt-1 font-body text-[11px] text-ink-secondary">
          {input.reason ?? FALLBACK_REASON}
        </p>
      )}
    </li>
  );
}

/** readOnly (operator console): no Edit control and no reason line, the rows only report state. */
export function InputsList({ inputs, readOnly = false }: { inputs: BrainInput[]; readOnly?: boolean }) {
  return (
    <SectionCard title="What you told Aira" subtitle="The five things Aira reads before it answers.">
      {inputs.length === 0 ? (
        <p className="font-body text-sm text-ink-secondary">Nothing to show yet.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {inputs.map((input) => (
            <InputRow key={input.key} input={input} readOnly={readOnly} />
          ))}
        </ul>
      )}
    </SectionCard>
  );
}
