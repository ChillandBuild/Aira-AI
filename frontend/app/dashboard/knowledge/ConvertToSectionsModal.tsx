"use client";

import { useEffect, useState, useCallback } from "react";
import { Loader2, AlertTriangle } from "lucide-react";
import { API_URL, getAuthHeaders } from "@/lib/api";
import { wordCount, SECTION_KEYS_ORDERED } from "./profileSections";

export interface ConvertResult {
  sections: Record<string, string>;
  removed: Array<{ text: string; why: string }>;
  facts_to_move: string[];
  suggested_handover: string;
  total_words: number;
  warnings: Array<{ key: string; words: number; limit: number }>;
  errors: string[];
}

interface ConvertToSectionsModalProps {
  text: string;
  onClose: () => void;
  onApply: (result: ConvertResult) => void;
}

export default function ConvertToSectionsModal({ text, onClose, onApply }: ConvertToSectionsModalProps) {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ConvertResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleConvert = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const auth = await getAuthHeaders();
      const res = await fetch(`${API_URL}/api/v1/ai-tune/profile/convert`, {
        method: "POST",
        headers: { ...auth, "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });

      if (!res.ok) {
        throw new Error("Failed to convert sections");
      }

      const data: ConvertResult = await res.json();
      setResult(data);
    } catch {
      setError("Failed to convert sections. Please try again.");
    } finally {
      setLoading(false);
    }
  }, [text]);

  useEffect(() => {
    handleConvert();
  }, [handleConvert]);

  if (loading && !result) {
    return (
      <div className="fixed inset-0 z-dialog flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
        <div className="bg-surface rounded-2xl p-8 border border-surface-mid shadow-2xl max-w-lg w-full">
          <div className="flex items-center justify-center gap-3">
            <Loader2 size={20} className="animate-spin text-primary" />
            <p className="font-body text-sm text-on-surface">
              Aira is sorting your description… this can take up to a minute.
            </p>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="fixed inset-0 z-dialog flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
        <div className="bg-surface rounded-2xl p-6 md:p-8 border border-surface-mid shadow-2xl max-w-lg w-full space-y-4">
          <div className="flex items-start gap-2">
            <AlertTriangle size={16} className="text-red-600 flex-shrink-0 mt-0.5" />
            <p className="font-body text-sm text-red-700">{error}</p>
          </div>
          <button
            onClick={onClose}
            className="w-full px-4 py-2.5 bg-primary text-white rounded-xl font-label text-sm font-semibold hover:bg-primary/90 transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    );
  }

  if (!result) return null;

  return (
    <div className="fixed inset-0 z-dialog flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm overflow-y-auto" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Convert to sections"
        className="flex flex-col rounded-2xl border border-surface-mid bg-surface shadow-2xl animate-in fade-in zoom-in-95 duration-150 my-8 max-w-2xl w-full"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="space-y-6 overflow-y-auto max-h-[calc(90vh-120px)] p-6 md:p-8">
          <div>
            <h3 className="font-display text-lg font-bold text-on-surface">Sorted sections</h3>
            <p className="font-body text-xs text-on-surface-muted mt-1">
              {result.total_words} words across {Object.values(result.sections).filter((t) => t).length} sections.
              Review and adjust as needed.
            </p>
          </div>

          {/* Errors */}
          {result.errors.length > 0 && (
            <div className="space-y-2">
              {result.errors.map((err, i) => (
                <div
                  key={i}
                  className="flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 p-3 font-body text-xs text-red-800"
                >
                  <AlertTriangle size={14} className="flex-shrink-0 mt-0.5" />
                  <span>{err}</span>
                </div>
              ))}
            </div>
          )}

          {/* Warnings */}
          {result.warnings.length > 0 && (
            <div className="space-y-2">
              {result.warnings.map((w, i) => (
                <div
                  key={i}
                  className="flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 p-3 font-body text-xs text-amber-800"
                >
                  <AlertTriangle size={14} className="flex-shrink-0 mt-0.5" />
                  <span>
                    {w.key}: {w.words} words (over {w.limit})
                  </span>
                </div>
              ))}
            </div>
          )}

          {/* Sections */}
          <div className="space-y-4">
            {SECTION_KEYS_ORDERED.map((key) => {
              const text = result.sections[key];
              if (!text) return null;
              const words = wordCount(text);
              return (
                <div
                  key={key}
                  className="rounded-xl border border-surface-mid bg-surface-low p-4 space-y-2"
                >
                  <div className="flex items-center justify-between">
                    <p className="font-label text-xs font-semibold text-primary uppercase tracking-wider">
                      {key.replace(/_/g, " ")}
                    </p>
                    <span className="font-mono text-xs text-on-surface-muted">{words} words</span>
                  </div>
                  <p className="font-body text-sm leading-relaxed text-on-surface whitespace-pre-wrap">
                    {text}
                  </p>
                </div>
              );
            })}
          </div>

          {/* Removed */}
          {result.removed.length > 0 && (
            <div className="space-y-3">
              <div>
                <h4 className="font-label text-xs font-bold text-primary uppercase tracking-wider">
                  Removed
                </h4>
                <p className="font-body text-xs text-on-surface-muted mt-1">
                  Text that didn&apos;t fit into a section.
                </p>
              </div>
              <div className="space-y-2">
                {result.removed.map((r, i) => (
                  <div
                    key={i}
                    className="rounded-lg border border-surface-mid bg-surface-low p-3 space-y-1"
                  >
                    <p className="font-body text-xs text-on-surface whitespace-pre-wrap">{r.text}</p>
                    <p className="font-body text-[10px] text-on-surface-muted italic">{r.why}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Facts to move */}
          {result.facts_to_move.length > 0 && (
            <div className="space-y-3">
              <div>
                <h4 className="font-label text-xs font-bold text-primary uppercase tracking-wider">
                  Move these to Documents
                </h4>
                <p className="font-body text-xs text-on-surface-muted mt-1">
                  Consider uploading these as separate reference documents.
                </p>
              </div>
              <ul className="space-y-2">
                {result.facts_to_move.map((fact, i) => (
                  <li key={i} className="font-body text-xs text-on-surface pl-4">
                    • {fact}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Suggested handover */}
          {result.suggested_handover && (
            <div className="space-y-2">
              <label htmlFor="handover" className="font-label text-xs font-bold text-primary uppercase tracking-wider">
                Suggested handover line
              </label>
              <p className="font-body text-xs text-on-surface-muted">
                Paste this into &quot;When Aira can&apos;t help&quot; below if you like it.
              </p>
              <textarea
                id="handover"
                value={result.suggested_handover}
                readOnly
                rows={3}
                className="w-full px-4 py-3.5 rounded-xl bg-surface-low border border-surface-mid font-body text-xs leading-relaxed text-on-surface"
              />
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between gap-2 border-t border-surface-mid bg-surface-low px-4 pt-4 pb-[calc(1rem+env(safe-area-inset-bottom,0px))] md:px-6 md:pt-6 md:pb-[calc(1.5rem+env(safe-area-inset-bottom,0px))]">
          <button
            onClick={onClose}
            className="flex-1 px-4 py-2.5 bg-surface border border-surface-mid text-on-surface rounded-xl font-label text-sm font-semibold hover:bg-surface-low transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={() => onApply(result)}
            className="flex-1 px-4 py-2.5 bg-primary text-white rounded-xl font-label text-sm font-semibold hover:bg-primary/90 transition-colors"
          >
            Use these sections
          </button>
        </div>
      </div>
    </div>
  );
}
