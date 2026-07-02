"use client";
import { AlertTriangle, X } from "lucide-react";

interface ActionConfirmProps {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  description: string;
  confirmText: string;
  cancelText?: string;
  tone?: "danger" | "warning" | "primary";
  loading?: boolean;
}

const TONE_STYLE: Record<NonNullable<ActionConfirmProps["tone"]>, { icon: string; button: string }> = {
  danger: { icon: "bg-danger/10 text-danger", button: "bg-danger hover:bg-danger/90" },
  warning: { icon: "bg-warning/10 text-warning", button: "bg-warning hover:bg-warning/90" },
  primary: { icon: "bg-primary-muted text-primary", button: "bg-primary hover:bg-primary-dark" },
};

export function ActionConfirm({
  open,
  onClose,
  onConfirm,
  title,
  description,
  confirmText,
  cancelText = "Cancel",
  tone = "primary",
  loading,
}: ActionConfirmProps) {
  if (!open) return null;
  const style = TONE_STYLE[tone];

  return (
    <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-card shadow-xl w-full max-w-md p-6">
        <div className="flex items-start justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className={`w-10 h-10 rounded-full flex items-center justify-center ${style.icon}`}>
              <AlertTriangle size={20} />
            </div>
            <h3 className="text-lg font-bold text-ink">{title}</h3>
          </div>
          <button onClick={onClose} className="text-ink-muted hover:text-ink" aria-label="Close">
            <X size={18} />
          </button>
        </div>

        <p className="text-sm text-ink-secondary mb-6 whitespace-pre-line">{description}</p>

        <div className="flex gap-3">
          <button
            onClick={onClose}
            className="flex-1 px-4 py-2.5 border border-border text-sm text-ink-secondary rounded-xl hover:bg-surface-mid transition-colors"
          >
            {cancelText}
          </button>
          <button
            onClick={onConfirm}
            disabled={loading}
            className={`flex-1 px-4 py-2.5 text-white text-sm font-medium rounded-xl disabled:opacity-40 disabled:cursor-not-allowed transition-colors ${style.button}`}
          >
            {loading ? "Working…" : confirmText}
          </button>
        </div>
      </div>
    </div>
  );
}
