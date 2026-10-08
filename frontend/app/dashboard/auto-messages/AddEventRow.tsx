"use client";
import { useEffect, useRef, useState } from "react";
import { Plus } from "lucide-react";
import { api, type AutoMessageCustomEvent } from "@/lib/api";
import { ghostBtn, inputCls, primaryBtn, deriveEventKey } from "./shared";

/** "+ Add your own event": turns into an inline form with a live preview of the code the developer will send. */
export function AddEventRow({
  customCount,
  limit,
  takenKeys,
  disabledReason,
  onCreated,
}: {
  customCount: number;
  limit: number;
  /** Keys already in use (built-in and custom), to catch a clash before asking the server. */
  takenKeys: string[];
  /** Why adding is off right now (e.g. no approved template); null when it is on. */
  disabledReason: string | null;
  onCreated: (event: AutoMessageCustomEvent) => void;
}) {
  const [open, setOpen] = useState(false);
  const [label, setLabel] = useState("");
  const [description, setDescription] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const nameRef = useRef<HTMLInputElement>(null);
  const openerRef = useRef<HTMLButtonElement>(null);

  const full = customCount >= limit;
  const key = deriveEventKey(label);
  const clash = key !== null && takenKeys.includes(key);
  const canCreate = key !== null && !clash && !saving;

  useEffect(() => {
    if (open) nameRef.current?.focus();
  }, [open]);

  function close() {
    setOpen(false);
    setLabel("");
    setDescription("");
    setError(null);
    requestAnimationFrame(() => openerRef.current?.focus());
  }

  async function create() {
    if (!canCreate) return;
    setSaving(true);
    setError(null);
    try {
      const created = await api.autoMessages.createEvent({
        label: label.trim(),
        ...(description.trim() ? { description: description.trim() } : {}),
      });
      setOpen(false);
      setLabel("");
      setDescription("");
      onCreated(created);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't add the event. Try again.");
    } finally {
      setSaving(false);
    }
  }

  const reason = disabledReason ?? (full ? `${customCount} of ${limit} used` : null);

  if (!open) {
    return (
      <li className="border-t border-border-subtle px-3 py-3 sm:px-4">
        <button
          ref={openerRef}
          type="button"
          onClick={() => setOpen(true)}
          disabled={reason !== null}
          className={ghostBtn}
          title={disabledReason ?? undefined}
        >
          <Plus size={13} /> Add your own event
        </button>
        {reason && <span className="ml-3 font-body text-xs text-ink-secondary">{reason}</span>}
      </li>
    );
  }

  const hint = !label.trim()
    ? null
    : key === null
      ? "Use a name that starts with a letter, like Kundli ready."
      : clash
        ? `${key} is already used.`
        : null;

  return (
    <li className="border-t border-border-subtle px-3 py-3 sm:px-4">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void create();
        }}
        onKeyDown={(e) => {
          if (e.key === "Escape") close();
        }}
        className="space-y-3 rounded-2xl border border-dashed border-primary/30 bg-primary-50/40 p-3"
      >
        <div className="grid gap-2 sm:grid-cols-2">
          <div className="space-y-1">
            <label htmlFor="new-event-name" className="font-label text-xs font-bold text-ink">
              Name
            </label>
            <input
              id="new-event-name"
              ref={nameRef}
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="Kundli ready"
              maxLength={60}
              className={inputCls}
            />
          </div>
          <div className="space-y-1">
            <label htmlFor="new-event-when" className="font-label text-xs font-bold text-ink">
              When does this happen? <span className="font-normal text-ink-secondary">(optional)</span>
            </label>
            <input
              id="new-event-when"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Your app finishes a report"
              maxLength={200}
              className={inputCls}
            />
          </div>
        </div>
        <p className="font-body text-xs text-ink-secondary" aria-live="polite">
          Code your app sends:{" "}
          <span className="font-mono font-bold text-primary">{key ?? "…"}</span>
        </p>
        {(hint || error) && (
          <p role="alert" className="font-body text-xs font-semibold text-danger">
            {error ?? hint}
          </p>
        )}
        <div className="flex flex-wrap gap-2">
          <button type="submit" disabled={!canCreate} className={`${primaryBtn} max-sm:w-full`}>
            {saving ? "Creating…" : "Create"}
          </button>
          <button type="button" onClick={close} disabled={saving} className={ghostBtn}>
            Cancel
          </button>
        </div>
      </form>
    </li>
  );
}
