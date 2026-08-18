"use client";
import { useCallback, useEffect, useState } from "react";
import { BarChart3, CheckCircle2, Clock, CreditCard, IndianRupee, MessageSquare } from "lucide-react";
import { api, IntakeStats } from "@/lib/api";
import { usePolling } from "@/hooks/usePolling";

/* Mirrors the adminweb "Aira Customers" stats so both teams read the same
   numbers: messages = paid consultations, answered = the astrologer's reply
   came back over the bridge, pending = paid but not yet answered. */
export function IntakeDashboard() {
  const [stats, setStats] = useState<IntakeStats | null>(null);
  const [error, setError] = useState(false);

  const load = useCallback(async () => {
    try {
      setStats(await api.intake.stats());
      setError(false);
    } catch {
      setError(true);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);
  usePolling(load, 30000);

  if (!stats) {
    return (
      <div className="p-6 grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="h-28 rounded-2xl bg-border-subtle animate-pulse" />
        ))}
      </div>
    );
  }

  const t = stats.totals;
  const replyRate = t.messages > 0 ? Math.round((t.answered / t.messages) * 100) : 0;
  const maxDay = Math.max(1, ...stats.daily.map((d) => d.count));

  const cards = [
    {
      label: "Messages Received",
      value: t.messages,
      sub: "paid consultations",
      icon: MessageSquare,
      tone: "text-indigo-600 bg-indigo-50",
    },
    {
      label: "Pending Answer",
      value: t.pending,
      sub: "waiting on the astrologer",
      icon: Clock,
      tone: t.pending > 0 ? "text-amber-600 bg-amber-50" : "text-ink-muted bg-surface-subtle",
    },
    {
      label: "Answered",
      value: t.answered,
      sub: "reply reached the customer",
      icon: CheckCircle2,
      tone: "text-emerald-600 bg-emerald-50",
    },
    {
      label: "Revenue",
      value: `₹${t.revenue_inr}`,
      sub: "collected via consultations",
      icon: IndianRupee,
      tone: "text-violet-600 bg-violet-50",
    },
  ];

  return (
    <div className="p-6 space-y-6 max-w-5xl">
      {error && (
        <p className="font-body text-xs text-amber-600">
          Could not refresh just now — showing the last loaded numbers.
        </p>
      )}

      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {cards.map((c) => (
          <div key={c.label} className="rounded-2xl border border-border bg-white p-4">
            <div className={`w-9 h-9 rounded-xl flex items-center justify-center ${c.tone}`}>
              <c.icon size={16} />
            </div>
            <p className="font-display text-2xl font-bold text-ink mt-3 leading-none">{c.value}</p>
            <p className="font-label text-xs font-semibold text-ink mt-1.5">{c.label}</p>
            <p className="font-body text-[11px] text-ink-muted">{c.sub}</p>
          </div>
        ))}
      </div>

      {/* Awaiting payment + reply rate */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="rounded-2xl border border-border bg-white p-4 flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-surface-subtle flex items-center justify-center text-ink-muted">
            <CreditCard size={16} />
          </div>
          <div>
            <p className="font-display text-lg font-bold text-ink leading-none">{t.awaiting_payment}</p>
            <p className="font-body text-[11px] text-ink-muted mt-1">
              leads still on the payment step — not yet consultations
            </p>
          </div>
        </div>
        <div className="rounded-2xl border border-border bg-white p-4">
          <div className="flex items-center justify-between mb-2">
            <p className="font-label text-xs font-semibold text-ink">Reply rate</p>
            <p className="font-display text-sm font-bold text-ink">{replyRate}%</p>
          </div>
          <div className="h-2 rounded-full bg-border-subtle overflow-hidden">
            <div
              className={`h-full rounded-full ${replyRate >= 80 ? "bg-emerald-500" : replyRate >= 50 ? "bg-amber-500" : "bg-red-400"}`}
              style={{ width: `${replyRate}%` }}
            />
          </div>
          <p className="font-body text-[11px] text-ink-muted mt-2">
            {t.answered} of {t.messages} paid messages answered
          </p>
        </div>
      </div>

      {/* 14-day trend */}
      <div className="rounded-2xl border border-border bg-white p-4">
        <div className="flex items-center gap-2 mb-4">
          <BarChart3 size={14} className="text-ink-muted" />
          <p className="font-label text-xs font-semibold text-ink">Paid consultations — last 14 days</p>
        </div>
        <div className="flex items-end gap-1.5 h-28">
          {stats.daily.map((d) => (
            <div key={d.date} className="flex-1 flex flex-col items-center gap-1 min-w-0" title={`${d.date}: ${d.count}`}>
              <span className={`font-body text-[10px] leading-none ${d.count > 0 ? "text-ink" : "text-transparent"}`}>
                {d.count}
              </span>
              <div
                className={`w-full rounded-t-md ${d.count > 0 ? "bg-indigo-500" : "bg-border-subtle"}`}
                style={{ height: `${Math.max(4, (d.count / maxDay) * 88)}px` }}
              />
              <span className="font-body text-[9px] text-ink-muted">{d.date.slice(8)}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
