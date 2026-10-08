"use client";
import { useState } from "react";
import { Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import { ghostBtn, type EventInfo } from "./shared";

/** Deletes a custom event and its message. Asks inline, never with a browser pop-up. */
export function DeleteEvent({ ev, onDeleted }: { ev: EventInfo; onDeleted: () => void }) {
  const [asking, setAsking] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function remove() {
    setDeleting(true);
    setError(null);
    try {
      await api.autoMessages.deleteEvent(ev.key);
      onDeleted();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't delete it. Try again.");
      setDeleting(false);
    }
  }

  if (!asking) {
    return (
      <button type="button" onClick={() => setAsking(true)} className={`${ghostBtn} hover:!border-danger/40 hover:!text-danger`}>
        <Trash2 size={12} /> Delete event
      </button>
    );
  }

  return (
    <div role="alertdialog" aria-label={`Delete ${ev.label}`} className="space-y-2 rounded-xl border border-rose-200 bg-rose-50 p-3">
      <p className="font-body text-xs text-rose-700">
        Delete {ev.label} and its message? Your app&apos;s <span className="font-mono font-bold">{ev.key}</span> events will be ignored.
      </p>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={remove}
          disabled={deleting}
          className="inline-flex items-center justify-center rounded-lg bg-danger px-3 py-1.5 font-label text-xs font-bold text-white hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-danger/40 disabled:opacity-50 max-sm:min-h-[44px]"
        >
          {deleting ? "Deleting…" : "Delete"}
        </button>
        <button type="button" onClick={() => setAsking(false)} disabled={deleting} className={ghostBtn}>
          Keep
        </button>
      </div>
      {error && (
        <p role="alert" className="font-body text-xs font-semibold text-danger">
          {error}
        </p>
      )}
    </div>
  );
}
