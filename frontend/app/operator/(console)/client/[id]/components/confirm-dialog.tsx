"use client";
import { useState } from "react";
import { AlertTriangle, X } from "lucide-react";

interface ConfirmDialogProps {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  description: string;
  details: { label: string; count: number }[];
  confirmText: string;
  loading?: boolean;
}

export function ConfirmDialog({ open, onClose, onConfirm, title, description, details, confirmText, loading }: ConfirmDialogProps) {
  const [typed, setTyped] = useState("");
  if (!open) return null;

  return (
    <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-card shadow-xl w-full max-w-md p-6">
        <div className="flex items-start justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-warning/10 flex items-center justify-center">
              <AlertTriangle size={20} className="text-warning" />
            </div>
            <h3 className="text-lg font-bold text-ink">{title}</h3>
          </div>
          <button onClick={onClose} className="text-ink-muted hover:text-ink"><X size={18} /></button>
        </div>

        <p className="text-sm text-ink-secondary mb-3">{description}</p>

        {details.length > 0 && (
          <ul className="text-sm text-ink mb-4 space-y-1">
            {details.map(d => (
              <li key={d.label} className="flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-danger" />
                <span className="font-medium">{d.count.toLocaleString()}</span> {d.label}
              </li>
            ))}
          </ul>
        )}

        <p className="text-sm text-ink-secondary mb-2">
          Type <span className="font-mono font-bold text-ink">{confirmText}</span> to confirm:
        </p>
        <input
          value={typed}
          onChange={e => setTyped(e.target.value)}
          className="w-full border border-border rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-danger/20 focus:border-danger mb-4 font-mono"
          placeholder={confirmText}
        />

        <div className="flex gap-3">
          <button onClick={onClose} className="flex-1 px-4 py-2.5 border border-border text-sm text-ink-secondary rounded-xl hover:bg-surface-mid transition-colors">
            Cancel
          </button>
          <button
            onClick={() => { onConfirm(); setTyped(""); }}
            disabled={typed !== confirmText || loading}
            className="flex-1 px-4 py-2.5 bg-danger text-white text-sm font-medium rounded-xl hover:bg-danger/90 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {loading ? "Deleting…" : "Delete Forever"}
          </button>
        </div>
      </div>
    </div>
  );
}
