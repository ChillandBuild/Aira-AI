"use client";

import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid } from "recharts";
import type { TelecallingAnalyticsExtended } from "@/lib/api";

export default function CallsPerHour({ stats }: { stats: TelecallingAnalyticsExtended | null }) {
  const data = stats?.calls_per_hour ?? [];
  const hasCalls = data.some((d) => d.count > 0);

  return (
    <div className="bg-surface rounded-card p-6 shadow-card ring-1 ring-[#c4c7c7]/15">
      <h2 className="font-display text-base font-bold text-tertiary mb-1">Calls Per Hour</h2>
      <p className="font-label text-xs text-on-surface-muted mb-5">Team call volume across the day.</p>

      {!hasCalls ? (
        <p className="font-body text-sm text-on-surface-muted text-center py-6">No calls in this window.</p>
      ) : (
        <div role="img" aria-label="Calls per hour chart">
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0ece4" />
              <XAxis dataKey="label" tick={{ fontSize: 10, fill: "#a8a29e" }} />
              <YAxis tick={{ fontSize: 10, fill: "#a8a29e" }} allowDecimals={false} />
              <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e8e3db" }} />
              <Bar dataKey="count" radius={[4, 4, 0, 0]} name="Calls" fill="#6366f1" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
