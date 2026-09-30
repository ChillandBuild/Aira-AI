"use client";

import { useState } from "react";
import { ChevronDown, Loader2, RotateCcw } from "lucide-react";
import { dismissedSourceLabel } from "./consistencyLogic";
import type { DismissedIssue } from "./types";

interface DismissedListProps {
  items: readonly DismissedIssue[];
  /** Why Restore is unavailable, or null. */
  blockedReason: string | null;
  isLocked: boolean;
  onRestore: (id: string) => Promise<void>;
}

/** "Dismissed (N)": collapsed by default; each row can be put back on the list. */
export function ConsistencyDismissedList({ items, blockedReason, isLocked, onRestore }: DismissedListProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [restoringId, setRestoringId] = useState<string | null>(null);
  const listId = "dismissed-conflicts-list";
  const reasonId = "dismissed-restore-reason";

  if (items.length === 0) return null;

  async function restore(id: string) {
    setRestoringId(id);
    try {
      await onRestore(id);
    } finally {
      setRestoringId(null);
    }
  }

  return (
    <div className="border-t border-border-subtle pt-2.5">
      <button
        type="button"
        onClick={() => setIsOpen((open) => !open)}
        aria-expanded={isOpen}
        aria-controls={listId}
        className="inline-flex min-h-9 items-center gap-1.5 rounded-lg font-label text-xs font-semibold text-ink-secondary hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
      >
        <ChevronDown size={14} className={isOpen ? "rotate-180 transition-transform" : "transition-transform"} aria-hidden />
        Dismissed ({items.length})
      </button>

      {isOpen && (
        <div id={listId} className="mt-2 space-y-2">
          {blockedReason && (
            <p id={reasonId} className="font-body text-[11px] text-ink-muted">
              {blockedReason}
            </p>
          )}
          <ul className="space-y-2">
            {items.map((item) => (
              <li key={item.id} className="flex min-w-0 flex-wrap items-start justify-between gap-2 rounded-xl border border-border-subtle bg-white px-3 py-2.5">
                <div className="min-w-0 flex-1 space-y-0.5">
                  <p className="break-words font-label text-[10px] font-bold uppercase tracking-wider text-ink-muted">
                    {dismissedSourceLabel(item)}
                  </p>
                  <p className="break-words font-label text-xs font-semibold text-ink">{item.topic}</p>
                  <p className="break-words font-body text-xs italic text-ink-muted">&ldquo;{item.quote}&rdquo;</p>
                </div>
                <button
                  type="button"
                  onClick={() => restore(item.id)}
                  disabled={blockedReason !== null || isLocked || restoringId !== null}
                  aria-describedby={blockedReason ? reasonId : undefined}
                  className="inline-flex min-h-9 shrink-0 items-center gap-1.5 rounded-lg border border-border px-3 font-label text-xs font-semibold text-ink-secondary hover:border-primary/40 hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 disabled:opacity-50"
                >
                  {restoringId === item.id ? <Loader2 size={12} className="animate-spin" /> : <RotateCcw size={12} />}
                  Restore
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
