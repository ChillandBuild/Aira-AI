"use client";
import { useCallback, useEffect, useState } from "react";
import { MessageCircle, RefreshCw, Send } from "lucide-react";
import { toast } from "sonner";
import { api, type SendDetailsContext, type SendDetailsTemplate } from "@/lib/api";
import { timeAgo } from "@/lib/utils";
import { VARIABLE_LABEL, blankVariables, renderTemplate, templateLabel } from "../lib/send-details";

type ReadyContext = Extract<SendDetailsContext, { available: true }>;

export interface SendDetailsViewProps {
  context: ReadyContext;
  sending: boolean;
  readOnly?: boolean;
  onSendText: (text: string) => void;
  onSendTemplate: (template: SendDetailsTemplate, values: string[]) => void;
}

const SEND = "flex items-center justify-center gap-1.5 rounded-xl bg-emerald-600 px-4 py-2 font-label text-xs font-bold text-white shadow-sm transition-all hover:bg-emerald-700 disabled:opacity-50";

/** Presentational: free message inside the 24 h window, otherwise an approved template. */
export function SendDetailsView({ context, sending, readOnly = false, onSendText, onSendTemplate }: SendDetailsViewProps) {
  const [text, setText] = useState(context.free_text);
  const [templateId, setTemplateId] = useState(context.templates[0]?.id ?? "");
  const template = context.templates.find((t) => t.id === templateId) ?? null;
  const [values, setValues] = useState<string[]>(template ? template.variables.map((v) => v.value) : []);
  const blanks = template ? blankVariables(values) : 0;

  // The useState initialisers above only run once. When the parent re-fetches (e.g. after
  // a send, or the customer's last-inbound time moving the window), `context` is a new
  // object and the draft has to re-sync to it -- otherwise a sent message's stale text
  // sits in the box after the reload instead of the fresh pre-fill.
  useEffect(() => {
    setText(context.free_text);
    const firstTemplate = context.templates[0] ?? null;
    setTemplateId(firstTemplate?.id ?? "");
    setValues(firstTemplate ? firstTemplate.variables.map((v) => v.value) : []);
  }, [context]);

  function pickTemplate(id: string) {
    setTemplateId(id);
    const next = context.templates.find((t) => t.id === id);
    setValues(next ? next.variables.map((v) => v.value) : []);
  }

  return (
    <div className="flex min-w-0 flex-1 flex-col gap-3 rounded-2xl border border-[#e2e8f0] bg-white p-4 shadow-sm">
      <h3 className="flex items-center gap-1.5 font-display text-xs font-black uppercase tracking-widest text-[#13284A]">
        <MessageCircle size={12} className="text-emerald-500" /> Send details on WhatsApp
      </h3>
      <span
        className={`inline-flex items-center gap-1.5 self-start rounded-full border px-2 py-0.5 font-label text-[9px] font-bold ${
          context.window_open ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-amber-200 bg-amber-50 text-amber-700"
        }`}
      >
        <span className={`h-1.5 w-1.5 rounded-full ${context.window_open ? "bg-emerald-500" : "bg-amber-500"}`} />
        {context.window_open
          ? `Free message · customer wrote ${context.last_inbound_at ? timeAgo(context.last_inbound_at) : "recently"}`
          : "Template needed · no message from the customer in 24 h"}
      </span>

      {context.window_open ? (
        <>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={7}
            aria-label="Message"
            className="w-full resize-none rounded-xl border border-[#e2e8f0] bg-[#f8fafc]/40 p-3 font-body text-xs leading-relaxed transition-all focus:bg-white focus:outline-none focus:ring-2 focus:ring-emerald-300"
          />
          <button type="button" disabled={readOnly || sending || !text.trim()} onClick={() => onSendText(text.trim())} className={SEND}>
            {sending ? <RefreshCw size={12} className="animate-spin" /> : <Send size={12} />} Send
          </button>
        </>
      ) : context.templates.length === 0 ? (
        <p className="rounded-xl border border-dashed border-[#e2e8f0] bg-[#f8fafc] p-3 font-body text-[11px] leading-relaxed text-[#475569]">
          No approved templates yet. Add one under Templates (for example <span className="font-semibold">call_details_share</span>) and it shows here once Meta approves it.
        </p>
      ) : (
        <>
          <select
            value={templateId}
            onChange={(e) => pickTemplate(e.target.value)}
            aria-label="Template"
            className="w-full rounded-xl border border-[#e2e8f0] bg-white px-3 py-2 font-body text-xs text-[#1e293b] focus:outline-none focus:ring-2 focus:ring-emerald-300"
          >
            {context.templates.map((t) => (
              <option key={t.id} value={t.id}>{templateLabel(t)}</option>
            ))}
          </select>
          {template?.variables.map((v, i) => (
            <label key={v.key} className="block">
              <span className="mb-1 block font-label text-[9px] font-black uppercase tracking-wider text-[#94a3b8]">
                {`{{${v.key}}}`} · {v.role ? VARIABLE_LABEL[v.role] : "Fill this in"}
              </span>
              <input
                value={values[i] ?? ""}
                onChange={(e) => setValues((prev) => prev.map((x, j) => (j === i ? e.target.value : x)))}
                className={`w-full rounded-lg border px-2.5 py-1.5 font-body text-xs focus:outline-none focus:ring-2 focus:ring-emerald-300 ${
                  (values[i] ?? "").trim() ? "border-[#e2e8f0] bg-white" : "border-amber-300 bg-amber-50/50"
                }`}
              />
            </label>
          ))}
          {template && (
            <div className="whitespace-pre-wrap rounded-xl border border-primary-100 bg-primary-50 p-3 font-body text-[11px] leading-relaxed text-[#13284A]">
              {renderTemplate(template.body_text, values)}
            </div>
          )}
          <button
            type="button"
            disabled={readOnly || sending || !template || blanks > 0}
            onClick={() => template && onSendTemplate(template, values)}
            className={SEND}
          >
            {sending ? <RefreshCw size={12} className="animate-spin" /> : <Send size={12} />}
            {blanks > 0 ? `Fill ${blanks} blank${blanks === 1 ? "" : "s"}` : "Send template"}
          </button>
        </>
      )}
      <p className="font-label text-[10px] text-[#94a3b8]">Sends from your business number and shows in Conversations.</p>
    </div>
  );
}

// Last answer per lead, so reopening a lead shows the card at once while it refreshes.
const contextCache = new Map<string, SendDetailsContext>();

/** Holds the card's space while the first answer loads, so Quick Note doesn't jump. */
function SendDetailsSkeleton() {
  return (
    <div aria-hidden className="flex min-w-0 flex-1 animate-pulse flex-col gap-3 rounded-2xl border border-[#e2e8f0] bg-white p-4 shadow-sm">
      <div className="h-3 w-40 rounded bg-[#f0ece6]" />
      <div className="h-4 w-56 rounded-full bg-[#f5f2ed]" />
      <div className="min-h-[120px] flex-1 rounded-xl bg-[#f8fafc]" />
      <div className="h-8 rounded-xl bg-[#f0ece6]" />
    </div>
  );
}

/** Lead page card. Hidden when the tenant has no WhatsApp or the lead opted out. */
export default function SendDetailsCard({ leadId, readOnly = false }: { leadId: string; readOnly?: boolean }) {
  const [context, setContext] = useState<SendDetailsContext | null>(() => contextCache.get(leadId) ?? null);
  const [sending, setSending] = useState(false);

  const load = useCallback((force = false) => {
    api.leads.sendDetailsContext(leadId)
      .then((next) => {
        const cached = contextCache.get(leadId);
        // An unchanged refresh keeps the old object: a new one resets any draft being typed.
        if (!force && cached && JSON.stringify(cached) === JSON.stringify(next)) return setContext(cached);
        contextCache.set(leadId, next);
        setContext(next);
      })
      .catch(() => setContext({ available: false }));
  }, [leadId]);

  useEffect(() => {
    setContext(contextCache.get(leadId) ?? null);
    load();
  }, [leadId, load]);

  if (!context) return <SendDetailsSkeleton />;
  if (!context.available) return null;

  async function send(body: { text: string } | { template_id: string; variables: string[] }) {
    setSending(true);
    try {
      await api.leads.sendDetails(leadId, body);
      toast.success("Sent on WhatsApp. It's in Conversations.");
      load(true);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "WhatsApp didn't send it");
    } finally {
      setSending(false);
    }
  }

  return (
    <SendDetailsView
      key={leadId}
      context={context}
      sending={sending}
      readOnly={readOnly}
      onSendText={(text) => void send({ text })}
      onSendTemplate={(template, values) => void send({ template_id: template.id, variables: values })}
    />
  );
}
