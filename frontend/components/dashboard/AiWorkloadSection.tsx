"use client";
import { useEffect, useState } from "react";
import { api, AnalyticsOverview } from "@/lib/api";

export function AiWorkloadSection({ overview }: { overview: AnalyticsOverview }) {
  const [escalations, setEscalations] = useState<number | null>(null);

  useEffect(() => {
    let active = true;
    api.chatHandovers.count(true)
      .then(res => { if (active) setEscalations(res.count); })
      .catch(() => { if (active) setEscalations(null); });
    return () => { active = false; };
  }, []);

  const today = overview.daily_messages[overview.daily_messages.length - 1];
  const totalRepliesToday = (today?.ai ?? 0) + (today?.human ?? 0);
  const aiPct = totalRepliesToday > 0 ? Math.round(((today?.ai ?? 0) / totalRepliesToday) * 100) : 0;

  return (
    <div className="card rounded-[32px] p-8">
      <h2 className="font-display font-bold text-ink mb-6 text-[18px]">
        Is my AI carrying its weight?
      </h2>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-6 gap-y-8">
        <div>
          <div className="text-xs font-semibold text-ink-muted uppercase tracking-wider">AI Auto-Reply Share Today</div>
          <div className="font-display font-bold text-[32px] text-ink tracking-tight mt-2">{aiPct}%</div>
          <div className="text-xs text-ink-muted mt-1 font-medium">
            {today?.ai ?? 0} AI · {today?.human ?? 0} human
          </div>
        </div>
        <div>
          <div className="text-xs font-semibold text-ink-muted uppercase tracking-wider">Inbound Today</div>
          <div className="font-display font-bold text-[32px] text-ink tracking-tight mt-2">{today?.inbound ?? 0}</div>
        </div>
        <div>
          <div className="text-xs font-semibold text-ink-muted uppercase tracking-wider">Outbound Today</div>
          <div className="font-display font-bold text-[32px] text-ink tracking-tight mt-2">{today?.outbound ?? 0}</div>
        </div>
        <div>
          <div className="text-xs font-semibold text-ink-muted uppercase tracking-wider">Awaiting Response</div>
          <div className={`font-display font-bold text-[32px] tracking-tight mt-2 ${overview.unreplied_24h > 0 ? "text-rose-600" : "text-ink"}`}>
            {overview.unreplied_24h}
          </div>
        </div>
        <div>
          <div className="text-xs font-semibold text-ink-muted uppercase tracking-wider">Escalations</div>
          <div className={`font-display font-bold text-[32px] tracking-tight mt-2 ${(escalations ?? 0) > 0 ? "text-rose-600" : "text-ink"}`}>
            {escalations ?? "—"}
          </div>
        </div>
      </div>
    </div>
  );
}
