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

export function PipelinePulse({ overview }: { overview: AnalyticsOverview }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
      <HeroCard
        icon={<MessageSquare size={18} />}
        iconGradient="bg-gradient-to-tr from-emerald-500 to-teal-400"
        glowColor="bg-emerald-500/5 group-hover:bg-emerald-500/10"
        label="Total Leads"
        value={overview.total_leads}
        sparklineData={overview.daily_leads}
        sparklineColor="#10b981"
        gradientId="totalLeadsGrad"
        trendPct={overview.daily_leads_trend_pct}
        trendLabel="new leads vs last week"
      />
      <HeroCard
        icon={<TrendingUp size={18} />}
        iconGradient="bg-gradient-to-tr from-amber-500 to-orange-500"
        glowColor="bg-amber-500/5 group-hover:bg-amber-500/10"
        label="New Hot Leads (7d)"
        value={overview.new_hot_leads_7d}
        sparklineData={overview.new_hot_leads_7d_daily}
        sparklineColor="#f59e0b"
        gradientId="hotLeadsGrad"
        trendPct={overview.new_hot_leads_7d_trend_pct}
        trendLabel="vs last week"
      />
      <HeroCard
        icon={<CheckCircle2 size={18} />}
        iconGradient="bg-gradient-to-tr from-violet-600 to-purple-500"
        glowColor="bg-violet-500/5 group-hover:bg-violet-500/10"
        label="Conversions (7d)"
        value={overview.converted_7d}
        sparklineData={[]}
        sparklineColor="#5b21b6"
        gradientId="conversionsGrad"
        trendPct={overview.converted_7d_trend_pct}
        trendLabel="vs last week"
      />
    </div>
  );
}
