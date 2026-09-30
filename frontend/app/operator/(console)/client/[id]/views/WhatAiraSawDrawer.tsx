"use client";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { AlertTriangle, ChevronDown, Info, Loader2, X } from "lucide-react";
import {
  RECONSTRUCTION_BANNER,
  RETRIEVAL_COST_NOTE,
  blockingGates,
  isWhatAiraSaw,
  noticeGates,
  paiseToRupees,
  verdictLine,
  type WhatAiraSaw,
} from "@/components/brain/whatAiraSaw";
import { operatorFetch, relTime } from "@/lib/operator";

interface DrawerProps {
  tenantId: string;
  leadId: string;
  leadName: string | null;
  onClose: () => void;
}

function Section({ title, children, defaultOpen = false }: { title: string; children: ReactNode; defaultOpen?: boolean }) {
  return (
    <details open={defaultOpen} className="group rounded-xl border border-border bg-white">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-4 py-3 font-display text-sm font-extrabold text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40">
        {title}
        <ChevronDown size={16} className="shrink-0 text-ink-secondary transition-transform group-open:rotate-180" aria-hidden />
      </summary>
      <div className="border-t border-border-subtle px-4 py-3 font-body text-sm text-ink">{children}</div>
    </details>
  );
}

function Muted({ children }: { children: ReactNode }) {
  return <p className="font-body text-sm text-ink-secondary">{children}</p>;
}

function Verdict({ saw }: { saw: WhatAiraSaw }) {
  const notices = noticeGates(saw.gates);
  return (
    <div className="space-y-2">
      <p className={`font-semibold ${saw.would_reply ? "text-success" : "text-danger"}`}>{verdictLine(saw)}</p>
      <ul className="space-y-1">
        {saw.gates.map((g) => (
          <li key={g.key} className="flex items-start gap-2 text-xs">
            <span className={`mt-0.5 shrink-0 rounded-full px-2 py-0.5 font-label font-bold ${g.active ? (g.blocks_reply ? "bg-rose-50 text-danger" : "bg-amber-50 text-warning") : "bg-surface-mid text-ink-secondary"}`}>
              {g.active ? "On" : "Off"}
            </span>
            <span><span className="font-semibold">{g.label}.</span> <span className="text-ink-secondary">{g.detail}</span></span>
          </li>
        ))}
      </ul>
      {blockingGates(saw.gates).length === 0 && notices.length > 0 && (
        <p className="text-xs text-ink-secondary">Amber gates change how Aira replies but do not stop it.</p>
      )}
    </div>
  );
}

function Messages({ saw }: { saw: WhatAiraSaw }) {
  if (saw.recent_messages.length === 0) return <Muted>No messages yet.</Muted>;
  return (
    <ol className="space-y-2">
      {saw.recent_messages.map((m, i) => (
        <li key={`${m.at}-${i}`} className="rounded-lg bg-surface-mid/60 px-3 py-2">
          <p className="font-label text-[11px] font-bold uppercase tracking-wide text-ink-secondary">
            {m.direction === "inbound" ? "Lead" : m.is_ai ? "Aira" : "Person"} · {relTime(m.at)}
          </p>
          <p className="mt-0.5 whitespace-pre-wrap break-words">{m.text || "—"}</p>
        </li>
      ))}
    </ol>
  );
}

function Deal({ saw }: { saw: WhatAiraSaw }) {
  const { session, selling_enabled } = saw.deal_state;
  if (!selling_enabled && !session) return <Muted>Selling is not set up for this business.</Muted>;
  if (!session) return <Muted>No sale in progress for this lead.</Muted>;
  return (
    <div className="space-y-1">
      <p>Status: <span className="font-semibold">{session.status ?? "—"}</span></p>
      <pre className="overflow-x-auto whitespace-pre-wrap break-words rounded-lg bg-surface-mid/60 p-2 text-xs">{JSON.stringify(session.collected_data, null, 2)}</pre>
    </div>
  );
}

function Orders({ saw }: { saw: WhatAiraSaw }) {
  if (saw.orders.length === 0) return <Muted>No orders.</Muted>;
  return (
    <ul className="space-y-1">
      {saw.orders.map((o, i) => (
        <li key={`${o.deal_number}-${i}`}>
          #{o.deal_number ?? "—"} · {o.stage ?? "—"} · {paiseToRupees(o.total_paise)}
          <span className="text-ink-secondary"> — {o.items.map((it) => `${it.name ?? "item"} x${it.qty ?? 1}`).join(", ") || "no lines"}</span>
        </li>
      ))}
    </ul>
  );
}

function Calls({ saw }: { saw: WhatAiraSaw }) {
  if (saw.call_summaries.length === 0) return <Muted>No analysed calls.</Muted>;
  return (
    <ul className="space-y-2">
      {saw.call_summaries.map((c, i) => (
        <li key={`${c.at}-${i}`}>
          <p className="font-label text-[11px] font-bold uppercase tracking-wide text-ink-secondary">{relTime(c.at)} · {c.manual_status ?? c.outcome ?? "call"}</p>
          <p className="whitespace-pre-wrap break-words">{c.summary}</p>
        </li>
      ))}
    </ul>
  );
}

function Knowledge({ saw, loading, onLoad }: { saw: WhatAiraSaw; loading: boolean; onLoad: () => void }) {
  if (saw.knowledge.text !== null) {
    return saw.knowledge.text
      ? <pre className="whitespace-pre-wrap break-words text-xs">{saw.knowledge.text}</pre>
      : <Muted>{saw.knowledge.note ?? "Nothing retrieved."}</Muted>;
  }
  return (
    <div className="space-y-2">
      <Muted>{saw.knowledge.note}</Muted>
      <button
        type="button"
        onClick={onLoad}
        disabled={loading}
        aria-describedby="saw-retrieval-cost"
        className="inline-flex items-center gap-2 rounded-lg border border-primary/30 px-3 py-1.5 font-label text-xs font-bold text-primary hover:bg-primary/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 disabled:opacity-60"
      >
        {loading && <Loader2 size={14} className="animate-spin" aria-hidden />}
        Show retrieved knowledge
      </button>
      <p id="saw-retrieval-cost" className="text-xs text-ink-secondary">{RETRIEVAL_COST_NOTE}</p>
    </div>
  );
}

function Body({ saw, loading, onLoadKnowledge }: { saw: WhatAiraSaw; loading: boolean; onLoadKnowledge: () => void }) {
  return (
    <div className="space-y-3">
      <Section title="Would Aira reply?" defaultOpen><Verdict saw={saw} /></Section>
      <Section title="Message it answers">
        <p className="whitespace-pre-wrap break-words">{saw.message_used.text || "—"}</p>
        {saw.message_used.note && <p className="mt-1 text-xs text-ink-secondary">{saw.message_used.note}</p>}
      </Section>
      <Section title={`Recent messages (${saw.recent_messages.length})`}><Messages saw={saw} /></Section>
      <Section title="Conversation summary">{saw.conversation_summary ? <p className="whitespace-pre-wrap">{saw.conversation_summary}</p> : <Muted>No summary yet.</Muted>}</Section>
      <Section title="Campaign">{saw.campaign ? <p>{saw.campaign.name}</p> : <Muted>Not from a campaign.</Muted>}</Section>
      <Section title="Deal state"><Deal saw={saw} /></Section>
      <Section title={`Orders (${saw.orders.length})`}><Orders saw={saw} /></Section>
      <Section title={`Call summaries (${saw.call_summaries.length})`}><Calls saw={saw} /></Section>
      <Section title="Retrieved knowledge"><Knowledge saw={saw} loading={loading} onLoad={onLoadKnowledge} /></Section>
      <Section title={`System prompt${saw.reply_language_mode ? ` (language mode: ${saw.reply_language_mode})` : ""}`}>
        {saw.system_prompt
          ? <pre className="max-h-[60vh] overflow-auto whitespace-pre-wrap break-words text-xs">{saw.system_prompt}</pre>
          : <p className="text-danger">{saw.prompt_error ?? "No prompt."}</p>}
      </Section>
    </div>
  );
}

export function WhatAiraSawDrawer({ tenantId, leadId, leadName, onClose }: DrawerProps) {
  const [saw, setSaw] = useState<WhatAiraSaw | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  const load = useCallback(async (retrieval: boolean) => {
    setLoading(true);
    try {
      const path = `/api/v1/operator/clients/${tenantId}/leads/${leadId}/what-aira-saw${retrieval ? "?retrieval=true" : ""}`;
      const body: unknown = await operatorFetch<unknown>(path);
      if (!isWhatAiraSaw(body)) throw new Error("Aira sent an unexpected response.");
      setSaw(body);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, [tenantId, leadId]);

  useEffect(() => { void load(false); }, [load]);
  useEffect(() => { closeRef.current?.focus(); }, []);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-dialog flex justify-end bg-black/40" onClick={onClose}>
      <aside
        role="dialog"
        aria-modal="true"
        aria-label="What Aira saw"
        className="flex h-full w-full max-w-2xl flex-col overflow-hidden bg-surface shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-start justify-between gap-4 border-b border-border px-4 py-3 sm:px-5">
          <div className="min-w-0">
            <p className="font-label text-[11px] font-bold uppercase tracking-wider text-primary">What Aira saw</p>
            <h2 className="truncate font-display text-lg font-bold text-ink">{leadName || "Unknown lead"}</h2>
            {saw && <p className="font-body text-xs text-ink-secondary">Generated {relTime(saw.generated_at)}</p>}
          </div>
          <button ref={closeRef} type="button" onClick={onClose} aria-label="Close" className="rounded-lg p-1.5 text-ink-secondary hover:bg-surface-mid focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40">
            <X size={18} />
          </button>
        </header>
        <div className="flex items-start gap-2 border-b border-amber-200 bg-amber-50 px-4 py-2 font-body text-xs text-warning sm:px-5">
          <Info size={14} className="mt-0.5 shrink-0" aria-hidden />
          <p>{RECONSTRUCTION_BANNER}</p>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-4 sm:p-5">
          {loading && !saw && (
            <div className="flex items-center justify-center gap-2 py-16 font-body text-sm text-ink-secondary">
              <Loader2 size={18} className="animate-spin text-primary" aria-hidden /> Loading…
            </div>
          )}
          {error && (
            <div role="alert" className="mb-3 flex items-center gap-2 rounded-xl border border-danger/20 bg-red-50 p-3 font-body text-sm text-danger">
              <AlertTriangle size={14} aria-hidden /> {error}
            </div>
          )}
          {saw && <Body saw={saw} loading={loading} onLoadKnowledge={() => void load(true)} />}
        </div>
      </aside>
    </div>
  );
}
