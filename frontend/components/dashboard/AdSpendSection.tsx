"use client";
import { useEffect, useState } from "react";
import { api, AdPerformanceSummary } from "@/lib/api";

export function AdSpendSection() {
  const [data, setData] = useState<AdPerformanceSummary | null>(null);

  useEffect(() => {
    let active = true;
    api.analytics.adPerformance().then(res => { if (active) setData(res); }).catch(() => {});
    return () => { active = false; };
  }, []);

  if (!data || data.campaigns.length === 0) return null;

  return (
    <div className="card rounded-[32px] p-8">
      <h2 className="font-display font-bold text-ink mb-6 text-[18px]">Ad Spend</h2>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-6 divide-x divide-[#f0ece4]">
        <div>
          <div className="text-xs font-semibold text-ink-muted uppercase tracking-wider">Campaigns</div>
          <div className="font-display font-bold text-[32px] text-ink tracking-tight mt-2">{data.totals.campaigns}</div>
        </div>
        <div className="pl-6">
          <div className="text-xs font-semibold text-ink-muted uppercase tracking-wider">Tracked Leads</div>
          <div className="font-display font-bold text-[32px] text-ink tracking-tight mt-2">{data.totals.tracked_leads}</div>
        </div>
        <div className="pl-6">
          <div className="text-xs font-semibold text-ink-muted uppercase tracking-wider">Conversion Rate</div>
          <div className="font-display font-bold text-[32px] text-ink tracking-tight mt-2">{Math.round(data.totals.conversion_rate * 100)}%</div>
        </div>
        <div className="pl-6">
          <div className="text-xs font-semibold text-ink-muted uppercase tracking-wider">Progressive Rate</div>
          <div className="font-display font-bold text-[32px] text-ink tracking-tight mt-2">{Math.round(data.totals.progressive_rate * 100)}%</div>
        </div>
      </div>
    </div>
  );
}
