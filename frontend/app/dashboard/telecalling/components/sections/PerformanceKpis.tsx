"use client";

import { Phone, TrendingUp, Clock, Coffee, Award, BarChart2, Loader2 } from "lucide-react";
import type { TelecallingAnalyticsExtended } from "@/lib/api";
import {
  formatTalk, formatPct, formatMinutes,
  computeDelta, deltaColor, deltaLabel, type Delta,
} from "./performance-format";

type PerCaller = TelecallingAnalyticsExtended["per_caller"][number];

interface PerformanceKpisProps {
  stats: TelecallingAnalyticsExtended | null;
  callerStats: PerCaller | null | undefined;
  selectedCallerId: string | null;
  loading: boolean;
  // Deltas compare against real yesterday / trailing-7d, so only show them when
  // the KPI values themselves cover "today" (no custom from/to range applied).
  showDeltas: boolean;
}

interface TileDeltas {
  yesterday: Delta | null;
  avg7d: Delta | null;
}

function DeltaRow({ deltas, asPct, unit }: { deltas: TileDeltas; asPct?: boolean; unit?: string }) {
  if (!deltas.yesterday && !deltas.avg7d) return null;
  return (
    <div className="mt-2 flex flex-col gap-0.5 text-[10px] font-bold">
      {deltas.yesterday && (
        <span className={deltaColor(deltas.yesterday)}>
          {deltaLabel(deltas.yesterday, { asPct, unit })} <span className="text-[#a8a29e] font-medium">vs yesterday</span>
        </span>
      )}
      {deltas.avg7d && (
        <span className={deltaColor(deltas.avg7d)}>
          {deltaLabel(deltas.avg7d, { asPct, unit })} <span className="text-[#a8a29e] font-medium">vs 7-day avg</span>
        </span>
      )}
    </div>
  );
}

interface TileProps {
  icon: React.ReactNode;
  iconClass: string;
  value: string;
  label: string;
  tooltip: string;
  loading: boolean;
  deltas?: TileDeltas;
  deltaOpts?: { asPct?: boolean; unit?: string };
}

function Tile({ icon, iconClass, value, label, tooltip, loading, deltas, deltaOpts }: TileProps) {
  return (
    <div className="bg-surface rounded-card p-4 shadow-card ring-1 ring-[#c4c7c7]/15" title={tooltip}>
      <div className={`p-2 rounded-lg w-fit mb-2 ${iconClass}`}>{icon}</div>
      <span className="block text-2xl font-display font-black text-[#292524]">
        {loading ? <Loader2 className="animate-spin text-[#a8a29e]" size={20} /> : value}
      </span>
      <span className="text-[#a8a29e] font-label text-[10px] uppercase font-bold tracking-wider mt-1 block">{label}</span>
      {!loading && deltas && <DeltaRow deltas={deltas} asPct={deltaOpts?.asPct} unit={deltaOpts?.unit} />}
    </div>
  );
}

export default function PerformanceKpis({ stats, callerStats, selectedCallerId, loading, showDeltas }: PerformanceKpisProps) {
  const isTeam = !selectedCallerId;
  // Deltas only at team level (comparison is team-wide) AND only on the today view.
  const comp = isTeam && showDeltas ? stats?.comparison : undefined;

  const callsVal = selectedCallerId ? (callerStats?.calls_today ?? 0) : (stats?.calls_today ?? 0);
  const connectRate = selectedCallerId ? (callerStats?.connect_rate ?? 0) : (stats?.connect_rate ?? 0);
  const avgTalk = selectedCallerId ? (callerStats?.avg_talk_seconds ?? 0) : (stats?.avg_talk_seconds ?? 0);
  const idle = selectedCallerId ? (callerStats?.idle_minutes_today ?? 0) : (stats?.idle_minutes_today ?? 0);
  const conversions = stats?.conversions_today ?? stats?.outcome_breakdown?.converted ?? 0;
  const convRate = selectedCallerId
    ? (callerStats?.conversion_rate ?? 0)
    : (callsVal > 0 ? conversions / callsVal : 0);
  const quality = callerStats?.overall_score;

  const compConvRate = (m: { conversions: number; calls: number }) => (m.calls > 0 ? (m.conversions / m.calls) * 100 : 0);

  // Deltas only meaningful at team level (comparison is team-wide, no per-caller history).
  const callsDeltas: TileDeltas = {
    yesterday: comp ? computeDelta(callsVal, comp.yesterday.calls) : null,
    avg7d: comp ? computeDelta(callsVal, comp.avg_7d.calls) : null,
  };
  const connectDeltas: TileDeltas = {
    yesterday: comp ? computeDelta(connectRate * 100, comp.yesterday.connect_rate * 100) : null,
    avg7d: comp ? computeDelta(connectRate * 100, comp.avg_7d.connect_rate * 100) : null,
  };
  const talkDeltas: TileDeltas = {
    yesterday: comp ? computeDelta(avgTalk, comp.yesterday.avg_talk_seconds) : null,
    avg7d: comp ? computeDelta(avgTalk, comp.avg_7d.avg_talk_seconds) : null,
  };
  const idleDeltas: TileDeltas = {
    yesterday: comp ? computeDelta(idle, comp.yesterday.idle_minutes, true) : null,
    avg7d: comp ? computeDelta(idle, comp.avg_7d.idle_minutes, true) : null,
  };
  const convDeltas: TileDeltas = {
    yesterday: comp ? computeDelta(conversions, comp.yesterday.conversions) : null,
    avg7d: comp ? computeDelta(conversions, comp.avg_7d.conversions) : null,
  };
  const convRateDeltas: TileDeltas = {
    yesterday: comp ? computeDelta(convRate * 100, compConvRate(comp.yesterday)) : null,
    avg7d: comp ? computeDelta(convRate * 100, compConvRate(comp.avg_7d)) : null,
  };

  const teamOnly = isTeam ? undefined : { yesterday: null, avg7d: null };

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
      <Tile
        loading={loading}
        icon={<Phone size={16} />}
        iconClass="bg-primary-light text-primary"
        value={formatPct(connectRate)}
        label="Connection Rate"
        tooltip="Connect Rate = answered ÷ dialed"
        deltas={isTeam ? connectDeltas : teamOnly}
        deltaOpts={{ unit: "pts" }}
      />
      <Tile
        loading={loading}
        icon={<Clock size={16} />}
        iconClass="bg-sky-50 text-sky-600"
        value={formatTalk(avgTalk)}
        label="Avg Talk Time"
        tooltip="Avg Talk Time = total talk seconds ÷ calls"
        deltas={isTeam ? talkDeltas : teamOnly}
        deltaOpts={{ asPct: true }}
      />
      <Tile
        loading={loading}
        icon={<Coffee size={16} />}
        iconClass="bg-amber-50 text-amber-600"
        value={formatMinutes(idle)}
        label={selectedCallerId ? "Idle Minutes" : "Total Team Idle"}
        tooltip="Idle = active (logged-in) minutes minus talk minutes. Lower is better."
        deltas={isTeam ? idleDeltas : teamOnly}
        deltaOpts={{ unit: "min" }}
      />
      <Tile
        loading={loading}
        icon={<TrendingUp size={16} />}
        iconClass="bg-emerald-50 text-emerald-600"
        value={String(conversions)}
        label="Conversions"
        tooltip="Conversions = calls with a 'converted' outcome today"
        deltas={isTeam ? convDeltas : teamOnly}
      />
      <Tile
        loading={loading}
        icon={<TrendingUp size={16} />}
        iconClass="bg-teal-50 text-teal-600"
        value={formatPct(convRate)}
        label="Conversion Rate"
        tooltip="Conversion Rate = converted ÷ calls"
        deltas={isTeam ? convRateDeltas : teamOnly}
        deltaOpts={{ unit: "pts" }}
      />
      {!isTeam && (
        <Tile
          loading={loading}
          icon={<Award size={16} />}
          iconClass="bg-purple-50 text-purple-600"
          value={quality ? `${quality.toFixed(1)}/10` : "—"}
          label="Overall Score"
          tooltip="Rolling average of last 10 calls (outcome + AI eval)"
        />
      )}
      <Tile
        loading={loading}
        icon={<BarChart2 size={16} />}
        iconClass="bg-rose-50 text-rose-600"
        value={String(callsVal)}
        label="Total Calls Today"
        tooltip="Total dialed calls in the selected window"
        deltas={isTeam ? callsDeltas : teamOnly}
      />
    </div>
  );
}
