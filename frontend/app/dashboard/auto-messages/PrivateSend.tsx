"use client";
import { useEffect, useState } from "react";
import { api, type PrivateSendStatus } from "@/lib/api";
import { EVENT_LABEL } from "./shared";

/** Private Send status for this tenant; null while loading or if the call fails (treated as "not enabled"). */
export function usePrivateSend(): PrivateSendStatus | null {
  const [status, setStatus] = useState<PrivateSendStatus | null>(null);
  useEffect(() => {
    let live = true;
    api.autoMessages
      .privateSend()
      .then((s) => live && setStatus(s))
      .catch(() => live && setStatus(null));
    return () => {
      live = false;
    };
  }, []);
  return status?.enabled ? status : null;
}

const TH = "px-4 py-2 font-label text-[10px] font-bold uppercase tracking-wide text-ink-muted";

export function PrivateSendDailyTable({ status }: { status: PrivateSendStatus }) {
  return (
    <section className="rounded-[24px] border border-border-subtle bg-white">
      <div className="border-b border-border-subtle px-5 py-4">
        <h3 className="font-display text-base font-bold text-ink">Private Send — daily counts</h3>
        <p className="mt-0.5 font-body text-xs text-ink-secondary">
          Sent from your own server. Anril only receives these counts, never names or numbers.
        </p>
      </div>
      {status.days.length === 0 ? (
        <p className="px-5 py-10 text-center font-body text-sm text-ink-muted">No Private Send messages in the last 30 days.</p>
      ) : (
        <table className="w-full font-body text-xs">
          <thead>
            <tr className="text-left">
              <th className={TH}>Day</th>
              <th className={TH}>Event</th>
              <th className={`${TH} hidden sm:table-cell`}>Template</th>
              <th className={`${TH} text-right`}>Sent</th>
              <th className={`${TH} text-right`}>Failed</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border-subtle">
            {status.days.map((d) => (
              <tr key={`${d.day}-${d.event}-${d.template_id ?? ""}`}>
                <td className="px-4 py-2.5 font-mono text-[11px] text-ink">{d.day}</td>
                <td className="px-4 py-2.5 text-ink">
                  {EVENT_LABEL[d.event as keyof typeof EVENT_LABEL] ?? d.event}
                  <span className="block max-w-[140px] truncate font-mono text-[11px] text-ink-muted sm:hidden">{d.template_name ?? "—"}</span>
                </td>
                <td className="hidden max-w-[220px] truncate px-4 py-2.5 font-mono text-[11px] text-ink-secondary sm:table-cell">{d.template_name ?? "—"}</td>
                <td className="px-4 py-2.5 text-right font-semibold text-ink">{d.sent.toLocaleString()}</td>
                <td className={`px-4 py-2.5 text-right ${d.failed > 0 ? "font-semibold text-danger" : "text-ink-muted"}`}>{d.failed.toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
