"use client";

import { useState } from "react";
import { History, Loader2, Plus, X } from "lucide-react";
import { toast } from "sonner";
import { api, CatalogItem } from "@/lib/api";
import { cn } from "@/lib/utils";
import { StockHistoryDrawer } from "./StockHistoryDrawer";

type Mode = "restock" | "correct";

/**
 * Dialog for restocking or correcting an item's tracked stock. Setting stock
 * on an untracked item (stock_quantity === null) via restock initialises it.
 */
export function StockDialog({
  item,
  onClose,
  onAdjusted,
}: {
  item: CatalogItem;
  onClose: () => void;
  onAdjusted: (quantityAfter: number | null, tracked: boolean) => void;
}) {
  const [mode, setMode] = useState<Mode>("restock");
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<number | null>(null);
  const [showHistory, setShowHistory] = useState(false);

  const current = item.stock_quantity;

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const trimmed = amount.trim();
    if (!trimmed || Number.isNaN(Number(trimmed))) {
      setError("Enter a number");
      return;
    }

    let delta: number;
    let reason: "restock" | "adjustment";
    if (mode === "restock") {
      const n = Math.round(Number(trimmed));
      if (n <= 0) {
        setError("Restock amount must be greater than 0");
        return;
      }
      delta = n;
      reason = "restock";
    } else {
      const target = Math.round(Number(trimmed));
      if (target < 0) {
        setError("Stock count can't be negative");
        return;
      }
      delta = target - (current ?? 0);
      reason = "adjustment";
    }

    setIsSaving(true);
    setError(null);
    try {
      const res = await api.catalog.adjustStock(item.id, {
        delta,
        reason,
        note: note.trim() || undefined,
      });
      setResult(res.quantity_after);
      onAdjusted(res.quantity_after, res.tracked);
      toast.success(
        res.quantity_after != null ? `Stock updated — ${res.quantity_after} in stock` : "Stock updated"
      );
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to update stock";
      setError(message);
      toast.error(message);
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-dialog flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-sm rounded-card bg-white p-5 shadow-xl">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="font-display text-lg font-bold text-ink">Update stock</h3>
          <button type="button" onClick={onClose} className="text-ink-muted hover:text-ink" aria-label="Close">
            <X size={18} />
          </button>
        </div>

        <p className="mb-4 truncate text-sm text-ink-muted" title={item.name}>{item.name}</p>

        <div className="mb-4 flex items-center justify-between rounded-xl bg-surface-low px-3 py-2">
          <span className="text-xs font-semibold uppercase text-ink-muted">Currently</span>
          <span className="font-display text-sm font-bold text-ink">
            {current == null ? "Not tracked" : `${current} in stock`}
          </span>
        </div>

        <div className="mb-4 flex gap-1 rounded-xl border border-border bg-surface-low p-1">
          <button
            type="button"
            onClick={() => {
              setMode("restock");
              setAmount("");
              setError(null);
            }}
            className={cn(
              "flex-1 rounded-lg py-1.5 text-sm font-semibold transition-colors",
              mode === "restock" ? "bg-primary text-white" : "text-ink-muted hover:text-ink"
            )}
          >
            Restock
          </button>
          <button
            type="button"
            onClick={() => {
              setMode("correct");
              setAmount(current != null ? String(current) : "");
              setError(null);
            }}
            className={cn(
              "flex-1 rounded-lg py-1.5 text-sm font-semibold transition-colors",
              mode === "correct" ? "bg-primary text-white" : "text-ink-muted hover:text-ink"
            )}
          >
            Correct count
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-xs font-semibold uppercase text-ink-muted">
              {mode === "restock" ? "Add to stock" : "Actual count now"}
            </label>
            <div className="relative">
              {mode === "restock" && (
                <Plus size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-muted" />
              )}
              <input
                type="number"
                min={mode === "restock" ? 1 : 0}
                step="1"
                autoFocus
                value={amount}
                onChange={(event) => setAmount(event.target.value)}
                placeholder={mode === "restock" ? "e.g. 20" : "e.g. 15"}
                className={cn(
                  "h-10 w-full rounded-xl border border-border bg-surface-low pr-3 text-sm outline-none focus:border-primary",
                  mode === "restock" ? "pl-9" : "pl-3"
                )}
              />
            </div>
            {mode === "correct" && (
              <p className="mt-1 text-xs text-ink-muted">
                Saved as a correction of {Math.round(Number(amount || "0")) - (current ?? 0) >= 0 ? "+" : ""}
                {Number.isNaN(Number(amount)) ? 0 : Math.round(Number(amount || "0")) - (current ?? 0)} from what&apos;s
                on record.
              </p>
            )}
          </div>

          <div>
            <label className="mb-1 block text-xs font-semibold uppercase text-ink-muted">Note (optional)</label>
            <input
              value={note}
              onChange={(event) => setNote(event.target.value)}
              placeholder="e.g. New shipment from supplier"
              className="h-10 w-full rounded-xl border border-border bg-surface-low px-3 text-sm outline-none focus:border-primary"
            />
          </div>

          {error && <p className="text-sm text-danger">{error}</p>}
          {result != null && !error && (
            <p className="text-sm font-semibold text-success">Now {result} in stock.</p>
          )}

          <div className="flex items-center justify-between gap-2 pt-1">
            <button
              type="button"
              onClick={() => setShowHistory(true)}
              className="inline-flex items-center gap-1.5 text-xs font-semibold text-primary hover:underline"
            >
              <History size={13} />
              History
            </button>
            <div className="flex gap-2">
              <button type="button" onClick={onClose} className="btn-ghost px-4 py-2">
                Close
              </button>
              <button
                type="submit"
                disabled={isSaving}
                className="btn-primary inline-flex items-center gap-2 px-4 py-2 disabled:opacity-60"
              >
                {isSaving && <Loader2 size={14} className="animate-spin" />}
                Save
              </button>
            </div>
          </div>
        </form>
      </div>

      {showHistory && (
        <StockHistoryDrawer itemId={item.id} itemName={item.name} onClose={() => setShowHistory(false)} />
      )}
    </div>
  );
}
