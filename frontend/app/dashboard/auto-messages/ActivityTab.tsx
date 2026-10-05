"use client";
import { useCallback, useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import { api, type AutoMessageSend } from "@/lib/api";
import { EVENT_LABEL, SOURCE_LABEL, STATUS_STYLE, formatWhen, ghostBtn, reasonText } from "./shared";

const FILTERS: { id: string; label: string }[] = [
  { id: "", label: "All" },
  { id: "sent", label: "Sent" },
  { id: "queued", label: "Scheduled" },
  { id: "skipped", label: "Not sent" },
  { id: "failed", label: "Failed" },
];

export function ActivityTab() {
  const [status, setStatus] = useState("");
  const [rows, setRows] = useState<AutoMessageSend[] | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setRows((await api.autoMessages.sends(status || undefined)).sends);
    } catch {
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [status]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <section className="rounded-[24px] border border-border-subtle bg-white">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border-subtle px-5 py-4">
        <div className="flex flex-wrap gap-1">
          {FILTERS.map((f) => (
            <button
              key={f.id}
              type="button"
              onClick={() => setStatus(f.id)}
              className={`rounded-full px-3 py-1 font-label text-xs font-semibold transition-all ${
                status === f.id ? "bg-ink text-white" : "text-ink-secondary hover:bg-surface-subtle hover:text-ink"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
        <button type="button" onClick={load} disabled={loading} className={ghostBtn}>
          <RefreshCw size={12} className={loading ? "animate-spin" : ""} /> Refresh
        </button>
      </div>

      {rows === null ? (
        <div className="space-y-2 p-5">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="h-12 animate-pulse rounded-xl bg-border-subtle" />
          ))}
        </div>
      ) : rows.length === 0 ? (
        <p className="px-5 py-14 text-center font-body text-sm text-ink-muted">
          Nothing here yet. Every customer that comes in through your form, apps or the counter shows up here.
        </p>
      ) : (
        <ul className="divide-y divide-border-subtle">
          {rows.map((s) => {
            const style = STATUS_STYLE[s.status];
            const why = reasonText(s.status, s.reason);
            return (
              <li key={s.id} className="grid gap-2 px-5 py-3.5 sm:grid-cols-[1.2fr_1.4fr_auto] sm:items-center sm:gap-4">
                <div className="min-w-0">
                  <p className="truncate font-body text-sm font-semibold text-ink">{s.name || s.phone}</p>
                  <p className="truncate font-body text-xs text-ink-muted">
                    {s.name ? `${s.phone} · ` : ""}
                    {SOURCE_LABEL[s.source]} · {formatWhen(s.created_at)}
                  </p>
                </div>
                <div className="min-w-0 font-body text-xs text-ink-secondary">
                  <p className="truncate">
                    <span className="font-semibold text-ink">{EVENT_LABEL[s.event]}</span>
                  </p>
                  <p className="truncate text-ink-muted">
                    {why ?? (s.template_name ? <span className="font-mono text-[11px]">{s.template_name}</span> : null)}
                    {s.status === "queued" && ` · goes at ${formatWhen(s.send_at)}`}
                  </p>
                </div>
                <span className={`justify-self-start rounded-full border px-2.5 py-0.5 font-label text-[10px] font-bold sm:justify-self-end ${style.cls}`}>
                  {style.label}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
