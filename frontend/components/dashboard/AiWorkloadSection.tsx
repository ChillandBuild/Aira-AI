"use client";
import { useEffect, useState } from "react";
import { api, AnalyticsOverview } from "@/lib/api";

export function AiWorkloadSection({ overview }: { overview: AnalyticsOverview }) {
  const [escalations, setEscalations] = useState<number | null>(null);

  useEffect(() => {
    let active = true;
    api.chatHandovers.count()
      .then(res => { if (active) setEscalations(res.count); })
      .catch(() => { if (active) setEscalations(null); });
    return () => { active = false; };
  }, []);

  const totalReplies = overview.ai_vs_human.ai + overview.ai_vs_human.human;
  const aiPct = totalReplies > 0 ? Math.round((overview.ai_vs_human.ai / totalReplies) * 100) : 0;
  const today = overview.daily_messages[overview.daily_messages.length - 1];

  return (
    <div className="card rounded-[32px] p-8">
      <h2 className="font-display font-bold text-ink mb-6 text-[18px]">
        Is my AI carrying its weight?
      </h2>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-6 gap-y-8">
        <div>
          <div className="text-xs font-semibold text-ink-muted uppercase tracking-wider">AI Auto-Reply Share</div>
          <div className="font-display font-bold text-[32px] text-ink tracking-tight mt-2">{aiPct}%</div>
          <div className="text-xs text-ink-muted mt-1 font-medium">
            {overview.ai_vs_human.ai} AI · {overview.ai_vs_human.human} human
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
