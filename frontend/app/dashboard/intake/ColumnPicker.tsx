"use client";
import { useEffect, useRef, useState } from "react";
import { Columns3 } from "lucide-react";
import { FieldColumn } from "./columns";

const STORAGE_KEY = "intake:hidden-columns";

interface ColumnPickerProps {
  columns: FieldColumn[];
  hiddenKeys: Set<string>;
  onChange: (next: Set<string>) => void;
}

export function ColumnPicker({ columns, hiddenKeys, onChange }: ColumnPickerProps) {
  const [open, setOpen] = useState(false);
  const container = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored) onChange(new Set(JSON.parse(stored) as string[]));
    // Restore once on mount; onChange is stable enough for this one-shot read.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    function onClickOutside(event: MouseEvent) {
      if (container.current && !container.current.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  function toggle(key: string) {
    const next = new Set(hiddenKeys);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    onChange(next);
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(Array.from(next)));
  }

  return (
    <div ref={container} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="inline-flex items-center gap-1 rounded-full border border-border px-3 py-1.5 font-label text-xs font-bold text-ink hover:bg-surface-subtle"
      >
        <Columns3 size={12} /> Columns
      </button>

      {open && (
        <div className="absolute right-0 z-20 mt-2 max-h-72 w-56 overflow-y-auto rounded-2xl border border-border bg-white p-2 shadow-lg">
          {columns.length === 0 ? (
            <p className="p-2 font-body text-xs text-ink-muted">No field columns yet.</p>
          ) : (
            columns.map((col) => (
              <label
                key={col.key}
                className="flex cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-surface-subtle"
              >
                <input
                  type="checkbox"
                  checked={!hiddenKeys.has(col.key)}
                  onChange={() => toggle(col.key)}
                />
                <span className="font-body text-sm text-ink">{col.label}</span>
              </label>
            ))
          )}
        </div>
      )}
    </div>
  );
}
