"use client";

import { useRef, useMemo } from "react";
import { Plus } from "lucide-react";
import { detectVariables, validateTemplateBody, templateBodyWarning } from "../types";

type VariableInserterProps = {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  maxLength?: number;
  rows?: number;
  label: string;
  helperText?: string;
};

/* ── helpers ─────────────────────────────────────────────────── */

function nextVariableNumber(text: string): number {
  const vars = detectVariables(text);
  if (vars.length === 0) return 1;
  return Math.max(...vars) + 1;
}

/* ── component ───────────────────────────────────────────────── */

export default function VariableInserter({
  value,
  onChange,
  placeholder = "Type your message here…",
  maxLength = 1024,
  rows = 4,
  label,
  helperText,
}: VariableInserterProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const variables = useMemo(() => detectVariables(value), [value]);
  const validationError = useMemo(() => validateTemplateBody(value), [value]);
  const validationWarning = useMemo(
    () => (validationError ? null : templateBodyWarning(value)),
    [value, validationError]
  );

  function insertVariable() {
    const el = textareaRef.current;
    if (!el) return;

    const num = nextVariableNumber(value);
    const tag = `{{${num}}}`;
    const start = el.selectionStart ?? value.length;
    const end = el.selectionEnd ?? value.length;

    const newVal = value.slice(0, start) + tag + value.slice(end);
    onChange(newVal);

    // Restore cursor position after React re-render
    requestAnimationFrame(() => {
      el.focus();
      const pos = start + tag.length;
      el.setSelectionRange(pos, pos);
    });
  }

  return (
    <div>
      {/* Label */}
      <label className="font-body text-sm font-medium text-ink mb-1.5 block">
        {label}
      </label>

      {/* Toolbar */}
      <div className="flex items-center gap-2 mb-1.5">
        <button
          type="button"
          onClick={insertVariable}
          className="flex items-center gap-1 px-2.5 py-1 rounded-lg border border-border-subtle bg-white text-xs font-medium text-ink-secondary hover:bg-surface-subtle hover:border-border transition-colors"
        >
          <Plus size={12} />
          Insert Variable
        </button>
        {helperText && (
          <p className="font-body text-[11px] text-ink-muted">{helperText}</p>
        )}
      </div>

      {/* Textarea */}
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        rows={rows}
        maxLength={maxLength}
        className={`input resize-y min-h-[100px] text-sm ${
          validationError ? "border-red-400 focus:border-red-500" : ""
        }`}
      />

      {/* Meta template rule violation / advisory */}
      {validationError && (
        <p className="font-body text-[11px] text-red-600 mt-1">{validationError}</p>
      )}
      {!validationError && validationWarning && (
        <p className="font-body text-[11px] text-amber-600 mt-1">{validationWarning}</p>
      )}

      {/* Footer: char count + detected vars */}
      <div className="flex items-center justify-between mt-1.5 flex-wrap gap-2">
        {/* Character count */}
        <p className="font-body text-[11px] text-ink-muted">
          <span
            className={
              value.length > maxLength * 0.9
                ? "text-amber-600 font-medium"
                : ""
            }
          >
            {value.length}
          </span>
          /{maxLength}
        </p>

        {/* Detected variables */}
        {variables.length > 0 && (
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="font-body text-[10px] text-ink-muted uppercase tracking-wider">
              Vars:
            </span>
            {variables.map((v) => (
              <span
                key={v}
                className="inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-semibold"
                style={{ background: "#DCF8C6", color: "#075E54" }}
              >
                {`{{${v}}}`}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
