"use client";
import { AlertTriangle, BarChart2 } from "lucide-react";
import { capUsagePercent, formatCount, usedTowardCap } from "@/lib/operator";
import type { PrivateSendUsage } from "../types";

const NEAR_CAP_PERCENT = 90;

function barTone(percent: number): string {
  if (percent >= 100) return "bg-danger";
  if (percent >= NEAR_CAP_PERCENT) return "bg-warning";
  return "bg-primary";
}

function Figure({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <p className="text-[11px] font-medium uppercase tracking-wider text-ink-muted">{label}</p>
      <p className="mt-0.5 truncate text-xl font-bold text-ink">{value}</p>
    </div>
  );
}

export function PrivateSendUsagePanel({ usage, cap }: { usage: PrivateSendUsage; cap: number | null }) {
  const percent = capUsagePercent(usedTowardCap(usage.reported_sent, usage.meta_volume), cap);
  return (
    <div>
      <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-ink">
        <BarChart2 size={16} className="text-ink-muted" />
        Usage this month
        <span className="font-normal text-ink-muted">({usage.period})</span>
      </h3>
      <div className="space-y-4 rounded-card border border-border bg-white p-4 shadow-sm">
        <div className="grid grid-cols-3 gap-4">
          <Figure label="Reported" value={usage.reported_sent.toLocaleString()} />
          <Figure label="Meta count" value={usage.meta_volume.toLocaleString()} />
          <Figure label="Cap" value={cap === null ? "No cap" : cap.toLocaleString()} />
        </div>

        {cap !== null && (
          <div>
            <div
              role="progressbar"
              aria-valuenow={percent}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-label="Usage against monthly cap"
              className="h-2 overflow-hidden rounded-full bg-surface-mid"
            >
              <div className={`h-full rounded-full transition-all ${barTone(percent)}`} style={{ width: `${percent}%` }} />
            </div>
            <p className="mt-1.5 text-xs text-ink-muted">{percent}% of this month&apos;s cap used</p>
          </div>
        )}

        {usage.mismatch && (
          <div className="flex items-start gap-2 rounded-xl border border-warning/30 bg-warning/10 p-3 text-xs text-warning">
            <AlertTriangle size={14} className="mt-0.5 shrink-0" />
            <p>What the plug-in reported doesn&apos;t match what Meta counted. Check that the client&apos;s server is reporting every send.</p>
          </div>
        )}

        {usage.days.length > 0 && (
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-surface-mid text-left">
                <th className="px-3 py-2 text-xs font-semibold uppercase tracking-wider text-ink-muted">Day</th>
                <th className="px-3 py-2 text-right text-xs font-semibold uppercase tracking-wider text-ink-muted">Reported</th>
                <th className="px-3 py-2 text-right text-xs font-semibold uppercase tracking-wider text-ink-muted">Meta</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border-subtle">
              {usage.days.map((d) => (
                <tr key={d.day}>
                  <td className="px-3 py-2 font-mono text-xs text-ink">{d.day}</td>
                  <td className="px-3 py-2 text-right text-ink">{formatCount(d.reported_sent)}</td>
                  <td className="px-3 py-2 text-right text-ink-secondary">{formatCount(d.meta_volume)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
