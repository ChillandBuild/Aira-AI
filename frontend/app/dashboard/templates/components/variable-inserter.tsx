"use client";

import { useRef, useMemo } from "react";
import { Plus } from "lucide-react";
import { detectVariables } from "../types";
import { bodyBlockers, renumberVariables, shortTemplateTip, sampleBlockers, tidyVariables } from "../template-rules";
import FieldMessages, { SampleInputs, useFixNotes } from "./field-messages";

type VariableInserterProps = {
  value: string;
  onChange: (value: string) => void;
  samples: Record<number, string>;
  onSamplesChange: (samples: Record<number, string>) => void;
  placeholder?: string;
  maxLength?: number;
  rows?: number;
  label: string;
  helperText?: string;
  /** id of the textarea; sample inputs are `${id}-sample-${n}` */
  id?: string;
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
  samples,
  onSamplesChange,
  placeholder = "Type your message here…",
  maxLength = 1024,
  rows = 4,
  label,
  helperText,
  id = "template-body",
}: VariableInserterProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const { notes, show } = useFixNotes();

  const variables = useMemo(() => detectVariables(value), [value]);
  const blockers = useMemo(() => bodyBlockers(value, id).filter((b) => b.inline), [value, id]);
  const tip = useMemo(() => (blockers.length ? null : shortTemplateTip(value)), [value, blockers]);
  const missingSamples = useMemo(() => sampleBlockers(value, samples, `${id}-sample-`), [value, samples, id]);
  const messagesId = `${id}-messages`;

  function handleChange(next: string) {
    const tidied = tidyVariables(next);
    show("body", tidied.note);
    onChange(tidied.text);
  }

  function renumber() {
    const { text, moved } = renumberVariables(value);
    const nextSamples: Record<number, string> = {};
    Object.entries(moved).forEach(([oldN, newN]) => {
      nextSamples[newN] = samples[Number(oldN)] ?? "";
    });
    onChange(text);
    onSamplesChange(nextSamples);
    show("body", "Renumbered the variables in order. Your samples moved with them.");
  }

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
      <label htmlFor={id} className="font-body text-sm font-medium text-ink mb-1.5 block">
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
        id={id}
        ref={textareaRef}
        value={value}
        onChange={(e) => handleChange(e.target.value)}
        placeholder={placeholder}
        rows={rows}
        maxLength={maxLength}
        aria-describedby={messagesId}
        aria-invalid={blockers.length > 0}
        className={`input resize-y min-h-[100px] text-sm ${
          blockers.length ? "border-red-400 focus:border-red-500" : ""
        }`}
      />

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
                style={{ background: "var(--primary-50)", color: "var(--primary-900)" }}
              >
                {`{{${v}}}`}
              </span>
            ))}
          </div>
        )}
      </div>

      <FieldMessages
        id={messagesId}
        note={notes.body}
        blockers={blockers}
        tip={tip}
        onFix={(fix) => fix === "renumber" && renumber()}
      />

      {blockers.length === 0 && (
        <>
          <SampleInputs
            variables={variables}
            samples={samples}
            onChange={onSamplesChange}
            idPrefix={`${id}-sample-`}
          />
          <FieldMessages id={`${id}-sample-messages`} blockers={missingSamples} />
        </>
      )}
    </div>
  );
}
