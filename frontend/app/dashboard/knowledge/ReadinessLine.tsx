"use client";

// One line above the drop zone: which Business Kit headings Aira already has. It only
// nudges -- nothing is blocked. Served by GET /knowledge/readiness (knowledge.view), so
// unlike the old owner-only Description row it tells managers the truth too.
//
// "Add": Description parts open the Description tab (owner-only editing). Prices and
// customer questions take a short text that is uploaded as a .txt file through the
// normal upload -> sort -> review path, so there is no second way to write facts.

import { useEffect, useState } from "react";
import { AlertTriangle, ArrowRight, Check, ChevronDown, Loader2 } from "lucide-react";
import { api, KnowledgeReadinessItem } from "@/lib/api";
import { cn } from "@/lib/utils";

type ItemKey = KnowledgeReadinessItem["key"];

const TEXT_ITEMS: Partial<Record<ItemKey, { file: string; placeholder: string }>> = {
  prices: {
    file: "Prices (added in Aira).txt",
    placeholder: "One product or service per line, with its exact price.\ne.g. Haircut - Rs 300",
  },
  questions: {
    file: "Customer questions (added in Aira).txt",
    placeholder: "Q: Can I get a refund?\nA: Yes, within 7 days of payment.",
  },
};

const LEVEL_ORDER: Record<KnowledgeReadinessItem["level"], number> = { must: 0, nice: 1, optional: 2 };

interface Props {
  refreshKey: string;
  isOwner: boolean;
  canManage: boolean;
  onOpenDescription: () => void;
  onAddText: (file: File) => Promise<void>;
}

export default function ReadinessLine({ refreshKey, isOwner, canManage, onOpenDescription, onAddText }: Props) {
  const [items, setItems] = useState<KnowledgeReadinessItem[] | null>(null);
  const [showAll, setShowAll] = useState(false);
  const [adding, setAdding] = useState<ItemKey | null>(null);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api.knowledge
      .readiness()
      .then((res) => !cancelled && setItems(res.data))
      .catch(() => !cancelled && setItems(null));
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  if (!items) return null;

  const ready = items.filter((i) => i.ok).length;
  const missing = items
    .filter((i) => !i.ok && i.level !== "optional")
    .sort((a, b) => LEVEL_ORDER[a.level] - LEVEL_ORDER[b.level]);
  const mustMissing = missing.filter((i) => i.level === "must");
  const next = missing[0];

  function canAdd(key: ItemKey): boolean {
    return TEXT_ITEMS[key] ? canManage : isOwner;
  }

  function startAdd(key: ItemKey) {
    if (!TEXT_ITEMS[key]) {
      onOpenDescription();
      return;
    }
    setAdding(key);
    setDraft("");
  }

  async function saveText() {
    const target = adding && TEXT_ITEMS[adding];
    if (!target || !draft.trim()) return;
    setSaving(true);
    try {
      await onAddText(new File([draft.trim()], target.file, { type: "text/plain" }));
      setAdding(null);
      setDraft("");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="border-b border-surface-mid/60 px-4 py-3.5 sm:px-5">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <span
          className={cn(
            "inline-flex shrink-0 items-center gap-1.5 rounded-lg border px-2 py-0.5 font-label text-[10.5px] font-bold",
            mustMissing.length === 0
              ? "border-emerald-200 bg-emerald-50 text-emerald-700"
              : "border-amber-200 bg-amber-50 text-amber-700"
          )}
        >
          {mustMissing.length === 0 ? <Check size={10} strokeWidth={3} /> : <AlertTriangle size={10} strokeWidth={2.5} />}
          {ready} of {items.length}
        </span>
        <span className="font-display text-sm font-bold text-on-surface">
          {mustMissing.length === 0 ? "Aira is ready" : "Aira readiness"}
        </span>
        {next && (
          <span className="font-body text-xs text-on-surface-muted">
            {next.label} missing{next.level === "nice" ? " (nice to have)" : ""}
          </span>
        )}
        <div className="ml-auto flex items-center gap-2">
          <button
            type="button"
            onClick={() => setShowAll((v) => !v)}
            aria-expanded={showAll}
            className="flex items-center gap-1 font-label text-xs font-semibold text-on-surface-muted hover:text-on-surface"
          >
            Details
            <ChevronDown size={13} className={cn("transition-transform", showAll && "rotate-180")} />
          </button>
          {next && canAdd(next.key) && adding === null && (
            <button
              type="button"
              onClick={() => startAdd(next.key)}
              className="flex shrink-0 items-center gap-1.5 rounded-xl border border-surface-mid bg-white px-3.5 py-2 font-label text-xs font-semibold text-primary transition-colors hover:bg-primary/5"
            >
              Add <ArrowRight size={13} />
            </button>
          )}
        </div>
      </div>

      {showAll && (
        <ul className="mt-3 grid grid-cols-1 gap-1.5 sm:grid-cols-2">
          {items.map((item) => (
            <li key={item.key} className="flex items-center gap-2 font-body text-xs">
              <span
                className={cn(
                  "h-2 w-2 shrink-0 rounded-full",
                  item.ok ? "bg-emerald-500" : item.level === "must" ? "bg-amber-500" : "bg-surface-mid"
                )}
              />
              <span className={item.ok ? "text-on-surface" : "text-on-surface-muted"}>{item.label}</span>
              {!item.ok && item.level === "optional" && <span className="text-on-surface-muted">(optional)</span>}
              {!item.ok && canAdd(item.key) && adding === null && (
                <button
                  type="button"
                  onClick={() => startAdd(item.key)}
                  className="font-label font-semibold text-primary hover:underline"
                >
                  Add
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      {adding && TEXT_ITEMS[adding] && (
        <div className="mt-3 space-y-2">
          <textarea
            id={`readiness-add-${adding}`}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={4}
            autoFocus
            placeholder={TEXT_ITEMS[adding]!.placeholder}
            className="input w-full resize-y font-body text-sm"
          />
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setAdding(null)}
              disabled={saving}
              className="rounded-xl px-3.5 py-2 font-label text-xs font-semibold text-on-surface-muted hover:bg-surface-low"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={saveText}
              disabled={saving || !draft.trim()}
              className="flex items-center gap-1.5 rounded-xl bg-primary px-3.5 py-2 font-label text-xs font-semibold text-white transition-colors hover:bg-primary-dark disabled:opacity-50"
            >
              {saving && <Loader2 size={13} className="animate-spin" />}
              Save
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
