import { MessageSquare, TrendingUp, CheckCircle2 } from "lucide-react";
import { AnalyticsOverview } from "@/lib/api";
import { TrendBadge } from "./TrendBadge";
import { HeroSparkline } from "./HeroSparkline";

interface HeroCardProps {
  icon: React.ReactNode;
  iconGradient: string;
  glowColor: string;
  label: string;
  value: number;
  sparklineData: { day: string; count: number }[];
  sparklineColor: string;
  gradientId: string;
  trendPct: number | null;
  trendLabel: string;
}

function HeroCard({
  icon, iconGradient, glowColor, label, value,
  sparklineData, sparklineColor, gradientId, trendPct, trendLabel,
}: HeroCardProps) {
  return (
    <div className="group relative overflow-hidden card rounded-[32px] p-8 flex flex-col justify-between hover:-translate-y-1 hover:shadow-md transition-all duration-300">
      <div className={`absolute top-0 right-0 -mt-4 -mr-4 w-32 h-32 rounded-full ${glowColor} blur-2xl transition-all duration-300`} />
      <div>
        <div className="flex items-center justify-between mb-6">
          <div className={`w-11 h-11 rounded-full ${iconGradient} text-white flex items-center justify-center shadow-md`}>
            {icon}
          </div>
          <HeroSparkline data={sparklineData} color={sparklineColor} gradientId={gradientId} />
        </div>
        <div className="text-xs font-semibold text-ink-muted uppercase tracking-wider">{label}</div>
        <div className="font-mono font-bold text-[40px] text-ink tracking-tight leading-none mt-2">
          {value}
        </div>
      </div>
      <TrendBadge pct={trendPct} label={trendLabel} />
    </div>
  );
}

// Same-day counts swing a lot on their own; "vs yesterday" (not "vs last
// week") is the only fair comparison for a number that resets every morning.
function pctVsYesterday(series: { day: string; count: number }[]): number | null {
  if (series.length < 2) return null;
  const today = series[series.length - 1].count;
  const yesterday = series[series.length - 2].count;
  if (yesterday === 0) return null;
  return Math.round(((today - yesterday) / yesterday) * 100);
}

export function PipelinePulse({ overview }: { overview: AnalyticsOverview }) {
  const newLeadsToday = overview.daily_leads[overview.daily_leads.length - 1]?.count ?? 0;
  const newHotLeadsToday = overview.new_hot_leads_7d_daily[overview.new_hot_leads_7d_daily.length - 1]?.count ?? 0;

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <HeroCard
          icon={<MessageSquare size={18} />}
          iconGradient="bg-gradient-to-tr from-emerald-500 to-teal-400"
          glowColor="bg-emerald-500/5 group-hover:bg-emerald-500/10"
          label="New Leads Today"
          value={newLeadsToday}
          sparklineData={overview.daily_leads}
          sparklineColor="#10b981"
          gradientId="totalLeadsGrad"
          trendPct={pctVsYesterday(overview.daily_leads)}
          trendLabel="vs yesterday"
        />
        <HeroCard
          icon={<TrendingUp size={18} />}
          iconGradient="bg-gradient-to-tr from-amber-500 to-orange-500"
          glowColor="bg-amber-500/5 group-hover:bg-amber-500/10"
          label="New Hot Leads Today"
          value={newHotLeadsToday}
          sparklineData={overview.new_hot_leads_7d_daily}
          sparklineColor="#f59e0b"
          gradientId="hotLeadsGrad"
          trendPct={pctVsYesterday(overview.new_hot_leads_7d_daily)}
          trendLabel="vs yesterday"
        />
        <HeroCard
          icon={<CheckCircle2 size={18} />}
          iconGradient="bg-gradient-to-tr from-violet-600 to-purple-500"
          glowColor="bg-violet-500/5 group-hover:bg-violet-500/10"
          label="Conversions Today"
          value={overview.converted_today}
          sparklineData={[]}
          sparklineColor="#5b21b6"
          gradientId="conversionsGrad"
          trendPct={null}
          trendLabel=""
        />
      </div>
      <p className="pl-1 font-label text-xs font-medium text-ink-muted">
        {overview.total_leads.toLocaleString()} total leads all-time
      </p>
    </div>
  );
}
