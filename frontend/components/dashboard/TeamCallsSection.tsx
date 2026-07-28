"use client";
import { useEffect, useState } from "react";
import { api, TelecallingAnalytics } from "@/lib/api";

export function TeamCallsSection() {
  const [data, setData] = useState<TelecallingAnalytics | null>(null);

  useEffect(() => {
    let active = true;
    api.analytics.telecalling().then(res => { if (active) setData(res); }).catch(() => {});
    return () => { active = false; };
  }, []);

  if (!data) return null;

  return (
    <div className="card rounded-[32px] p-8">
      <h2 className="font-display font-bold text-ink mb-6 text-[18px]">Team &amp; Calls</h2>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-6 divide-x divide-[#f0ece4]">
        <div>
          <div className="text-xs font-semibold text-ink-muted uppercase tracking-wider">Calls Today</div>
          <div className="font-display font-bold text-[32px] text-ink tracking-tight mt-2">{data.calls_today}</div>
        </div>
        <div className="pl-6">
          <div className="text-xs font-semibold text-ink-muted uppercase tracking-wider">Calls This Week</div>
          <div className="font-display font-bold text-[32px] text-ink tracking-tight mt-2">{data.calls_this_week}</div>
        </div>
        <div className="pl-6">
          <div className="text-xs font-semibold text-ink-muted uppercase tracking-wider">Converted</div>
          <div className="font-display font-bold text-[32px] text-ink tracking-tight mt-2">{data.outcome_breakdown.converted}</div>
        </div>
        <div className="pl-6">
          <div className="text-xs font-semibold text-ink-muted uppercase tracking-wider">Callback</div>
          <div className="font-display font-bold text-[32px] text-ink tracking-tight mt-2">{data.outcome_breakdown.callback}</div>
        </div>
      </div>
    </div>
  );
}
