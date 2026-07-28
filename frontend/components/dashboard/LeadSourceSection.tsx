import { AnalyticsOverview } from "@/lib/api";

const CHANNEL_LABELS: Record<string, string> = {
  whatsapp: "WhatsApp",
  instagram: "Instagram",
  facebook: "Facebook",
  telegram: "Telegram",
  upload: "Upload",
  manual: "Manual",
};

export function LeadSourceSection({ overview }: { overview: AnalyticsOverview }) {
  const breakdown = overview.channel_breakdown;
  const total = Object.values(breakdown).reduce((a, b) => a + b, 0);
  const entries = (Object.entries(breakdown) as [string, number][])
    .filter(([, count]) => count > 0)
    .sort((a, b) => b[1] - a[1]);

  const adAttributedPct = overview.total_leads > 0
    ? Math.round((overview.ad_attributed_leads / overview.total_leads) * 100)
    : 0;

  if (total === 0) {
    return (
      <div className="card rounded-[32px] p-8">
        <h2 className="font-display font-bold text-ink mb-2 text-[18px]">Where are leads coming from?</h2>
        <p className="text-sm text-ink-muted">No leads yet.</p>
      </div>
    );
  }

  return (
    <div className="card rounded-[32px] p-8">
      <h2 className="font-display font-bold text-ink mb-6 text-[18px]">Where are leads coming from?</h2>
      <div className="space-y-3">
        {entries.map(([channel, count]) => {
          const pct = total ? Math.round((count / total) * 100) : 0;
          return (
            <div key={channel} className="flex items-center gap-3">
              <div className="w-24 text-xs font-semibold text-ink-secondary">{CHANNEL_LABELS[channel] ?? channel}</div>
              <div className="flex-1 h-2 rounded-full bg-surface-mid overflow-hidden">
                <div className="h-full bg-[#5b21b6]" style={{ width: `${pct}%` }} />
              </div>
              <div className="w-16 text-right text-xs font-mono text-ink-muted">{count} · {pct}%</div>
            </div>
          );
        })}
      </div>
      <div className="mt-5 pt-5 border-t border-[#f0ece4] flex items-center justify-between">
        <span className="text-xs font-semibold text-ink-muted uppercase tracking-wider">Ad-attributed</span>
        <span className="text-sm font-mono font-semibold text-ink">
          {overview.ad_attributed_leads} of {overview.total_leads} ({adAttributedPct}%)
        </span>
      </div>
    </div>
  );
}
