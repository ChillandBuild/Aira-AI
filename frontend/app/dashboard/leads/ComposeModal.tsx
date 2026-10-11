"use client";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { FileText, Loader2, MessageSquare, Send, X } from "lucide-react";
import { api, type SendDetailsTemplate } from "@/lib/api";
import { cn } from "@/lib/utils";
import { VARIABLE_LABEL, blankVariables, renderTemplate, templateLabel } from "@/app/dashboard/telecalling/lib/send-details";

type Mode = "text" | "template";

const INPUT =
  "mt-1 w-full px-4 py-2.5 bg-surface-low rounded-xl font-body text-sm border border-surface-mid focus:ring-2 focus:ring-primary focus:outline-none";
const LABEL = "font-label text-xs font-semibold text-on-surface-muted uppercase tracking-wider";

export function ComposeModal({ onClose, onSent, canManageLeads }: { onClose: () => void; onSent: () => void; canManageLeads: boolean }) {
  const [mode, setMode] = useState<Mode>("text");
  const [phone, setPhone] = useState("");
  const [name, setName] = useState("");
  const [message, setMessage] = useState("");
  const [templates, setTemplates] = useState<SendDetailsTemplate[] | null>(null);
  const [templatesError, setTemplatesError] = useState<string | null>(null);
  const [templateId, setTemplateId] = useState("");
  const [values, setValues] = useState<string[]>([]);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load the approved templates the first time Template is picked.
  useEffect(() => {
    if (mode !== "template" || templates !== null) return;
    api.leads
      .composeTemplates()
      .then((rows) => {
        setTemplates(rows);
        if (rows[0]) setTemplateId(rows[0].id);
      })
      .catch((err) => {
        setTemplates([]);
        setTemplatesError(err instanceof Error ? err.message : "Couldn't load templates");
      });
  }, [mode, templates]);

  const template = useMemo(() => templates?.find((t) => t.id === templateId) ?? null, [templates, templateId]);

  // Fresh blanks for each template: business details come pre-filled, the name follows the Name field.
  useEffect(() => {
    setValues(template ? template.variables.map((v) => (v.role === "customer_name" ? name.trim() : v.value)) : []);
    // Only when the template changes; typing in Name updates its blank below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [template]);

  function onNameChange(next: string) {
    setName(next);
    if (!template) return;
    setValues((prev) =>
      template.variables.map((v, i) => (v.role === "customer_name" && (prev[i] ?? "") === name.trim() ? next.trim() : prev[i] ?? "")),
    );
  }

  const blanksLeft = template ? blankVariables(values) : 0;
  const canSend =
    canManageLeads &&
    !sending &&
    phone.trim().length > 0 &&
    (mode === "text" ? message.trim().length > 0 : !!template && blanksLeft === 0);

  async function send() {
    if (!canSend) return;
    setSending(true);
    setError(null);
    try {
      if (mode === "template" && template) {
        await api.leads.composeTemplate(phone.trim(), template.id, values, name.trim() || undefined);
      } else {
        await api.leads.compose(phone.trim(), message.trim(), name.trim() || undefined);
      }
      onSent();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Send failed");
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="fixed inset-0 z-dialog flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div
        className="bg-surface rounded-card shadow-card w-full max-w-md max-h-[calc(100dvh-2rem)] overflow-y-auto p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-5">
          <h3 className="font-display text-lg font-bold text-primary">New WhatsApp Message</h3>
          <button onClick={onClose} aria-label="Close" className="text-on-surface-muted hover:text-on-surface">
            <X size={18} />
          </button>
        </div>

        <div className="space-y-4">
          <div>
            <label className={LABEL} htmlFor="compose-phone">Phone Number</label>
            <input
              id="compose-phone"
              autoFocus
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="+919876543210"
              className={INPUT}
            />
          </div>

          <div>
            <label className={LABEL} htmlFor="compose-name">
              Name <span className="text-on-surface-muted/60 normal-case">(optional)</span>
            </label>
            <input
              id="compose-name"
              value={name}
              onChange={(e) => onNameChange(e.target.value)}
              placeholder="Lead name"
              className={INPUT}
            />
          </div>

          <div>
            <span className={LABEL}>Send as</span>
            <div role="tablist" className="mt-1 grid grid-cols-2 gap-1 rounded-xl border border-surface-mid bg-surface-low p-1">
              {([
                ["text", "Free message", MessageSquare],
                ["template", "Template", FileText],
              ] as const).map(([value, label, Icon]) => (
                <button
                  key={value}
                  type="button"
                  role="tab"
                  aria-selected={mode === value}
                  onClick={() => {
                    setMode(value);
                    setError(null);
                  }}
                  className={cn(
                    "flex items-center justify-center gap-1.5 rounded-lg py-2 font-label text-xs font-bold transition-all",
                    mode === value ? "bg-white text-primary shadow-sm" : "text-on-surface-muted hover:text-on-surface",
                  )}
                >
                  <Icon size={13} />
                  {label}
                </button>
              ))}
            </div>
          </div>

          {mode === "text" ? (
            <>
              <div>
                <label className={LABEL} htmlFor="compose-message">Message</label>
                <textarea
                  id="compose-message"
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  rows={4}
                  placeholder="Hello! ..."
                  className={cn(INPUT, "resize-none")}
                />
              </div>
              <div className="flex items-start gap-2 p-3 rounded-xl bg-amber-50 border border-amber-100">
                <p className="font-label text-xs text-amber-800 leading-relaxed">
                  <strong>Heads up:</strong> If this person hasn&apos;t messaged you in the last 24 hours, WhatsApp only
                  accepts an <strong>approved template</strong>.{" "}
                  <button type="button" onClick={() => setMode("template")} className="font-bold underline underline-offset-2">
                    Send a template instead
                  </button>
                </p>
              </div>
            </>
          ) : templates === null ? (
            <div className="flex items-center gap-2 rounded-xl bg-surface-low p-4 font-body text-sm text-on-surface-muted">
              <Loader2 size={14} className="animate-spin" /> Loading templates…
            </div>
          ) : templates.length === 0 ? (
            <div className="rounded-xl border border-surface-mid bg-surface-low p-4 font-body text-sm text-on-surface-muted">
              {templatesError ?? "No approved text templates on this WhatsApp number yet."}{" "}
              <Link href="/dashboard/templates" className="font-semibold text-primary hover:underline">
                Create one on the Templates page
              </Link>
            </div>
          ) : (
            <>
              <div>
                <label className={LABEL} htmlFor="compose-template">Template</label>
                <select
                  id="compose-template"
                  value={templateId}
                  onChange={(e) => setTemplateId(e.target.value)}
                  className={cn(INPUT, "cursor-pointer")}
                >
                  {templates.map((t) => (
                    <option key={t.id} value={t.id}>{templateLabel(t)}</option>
                  ))}
                </select>
              </div>

              {template?.variables.map((v, i) => (
                <div key={v.key}>
                  <label className={LABEL} htmlFor={`compose-var-${v.key}`}>
                    {`{{${v.key}}}`} · {v.role ? VARIABLE_LABEL[v.role] : "Fill this in"}
                  </label>
                  <input
                    id={`compose-var-${v.key}`}
                    value={values[i] ?? ""}
                    onChange={(e) => setValues((prev) => prev.map((old, j) => (j === i ? e.target.value : old)))}
                    className={INPUT}
                  />
                </div>
              ))}

              {template && (
                <div>
                  <span className={LABEL}>Preview</span>
                  <p className="mt-1 whitespace-pre-wrap rounded-xl border border-primary/15 bg-primary-light px-4 py-3 font-body text-sm text-on-surface">
                    {renderTemplate(template.body_text, values)}
                  </p>
                  {blanksLeft > 0 && (
                    <p className="mt-1.5 font-label text-xs text-on-surface-muted">
                      Fill {blanksLeft === 1 ? "the last blank" : `${blanksLeft} blanks`} to send.
                    </p>
                  )}
                </div>
              )}
            </>
          )}

          {error && (
            <div className="p-3 rounded-xl bg-red-50 border border-red-100">
              <p className="font-label text-xs text-red-700">{error}</p>
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2 mt-6">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-surface-low text-on-surface-muted rounded-xl font-label text-sm font-semibold hover:bg-surface-mid"
          >
            Cancel
          </button>
          <button
            onClick={send}
            disabled={!canSend}
            title={canManageLeads ? "Send message" : "Read-only role: sending is disabled"}
            className="flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-xl font-label text-sm font-semibold hover:bg-primary/90 disabled:opacity-50"
          >
            {sending ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
            {sending ? "Sending…" : mode === "template" ? "Send template" : "Send"}
          </button>
        </div>
      </div>
    </div>
  );
}
