"use client";
import { useMemo, useState } from "react";
import { api, MetaAdsPerfRow } from "@/lib/api";
import { useMetaAdsPerformance } from "@/hooks/useApi";
import { RefreshCw, Megaphone } from "lucide-react";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

type Props = {
  dateFrom: string; dateTo: string;
  setDateFrom: (v: string) => void; setDateTo: (v: string) => void;
};

function money(n: number | null | undefined) {
  if (n == null) return "—";
  return "₹" + Math.round(n).toLocaleString("en-IN");
}

function StatusBadge({ status }: { status: string | null }) {
  if (!status) return <span className="text-on-surface-muted">—</span>;
  const s = status.toUpperCase();
  const map: Record<string, { label: string; cls: string }> = {
    ACTIVE: { label: "Active", cls: "bg-emerald-50 text-emerald-700" },
    PAUSED: { label: "Paused", cls: "bg-surface-low text-on-surface-muted" },
    IN_PROCESS: { label: "In review", cls: "bg-amber-50 text-amber-700" },
    PENDING_REVIEW: { label: "In review", cls: "bg-amber-50 text-amber-700" },
    DISAPPROVED: { label: "Rejected", cls: "bg-red-50 text-red-600" },
    WITH_ISSUES: { label: "Issues", cls: "bg-red-50 text-red-600" },
  };
  const m = map[s] ?? { label: status, cls: "bg-surface-low text-on-surface-muted" };
  return <span className={cn("px-2 py-0.5 rounded-full text-[11px] font-bold", m.cls)}>{m.label}</span>;
}

const LEVELS: { key: string; label: string }[] = [
  { key: "campaign", label: "Campaign" },
  { key: "adset", label: "Ad set" },
  { key: "ad", label: "Ad" },
];

export function MetaAdsPerformanceTab({ dateFrom, dateTo, setDateFrom, setDateTo }: Props) {
  const [level, setLevel] = useState("campaign");
  const params = { level, date_from: dateFrom || undefined, date_to: dateTo || undefined };
  const { data, isValidating, mutate } = useMetaAdsPerformance(params);
  const rows: MetaAdsPerfRow[] = useMemo(() => data?.data ?? [], [data]);
  const [busy, setBusy] = useState<Record<string, boolean>>({});

  async function toggleStatus(row: MetaAdsPerfRow) {
    if (level !== "campaign") return;
    const active = (row.status ?? "").toUpperCase() !== "ACTIVE";
    setBusy((b) => ({ ...b, [row.group_id]: true }));
    try {
      const res = await api.metaAds.setStatus(row.group_id, active);
      if (res.ok) { toast.success(active ? "Campaign activated" : "Campaign paused"); mutate(); }
      else toast.error(res.error ?? "Status change failed");
    } finally {
      setBusy((b) => ({ ...b, [row.group_id]: false }));
    }
  }

  async function editBudget(row: MetaAdsPerfRow) {
    const raw = window.prompt(`New daily budget in ₹ for "${row.name}" (shared across the whole campaign):`);
    if (!raw) return;
    const val = Number(raw);
    if (!val || val <= 0) { toast.error("Enter a valid amount"); return; }
    const res = await api.metaAds.updateBudget(row.group_id, { daily_budget_inr: val });
    if (res.ok) { toast.success("Budget updated"); mutate(); }
    else toast.error(res.error ?? "Budget update failed");
  }

  const headers = ["Name", "Status", "Budget", "Spend", "Impr.", "Reach", "Results",
    "Cost/Result", "Clicks", "Messages", "No message", "Qualified", "Hot"];

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-end gap-2.5">
        <div className="flex gap-1 rounded-full bg-surface-low/60 p-1">
          {LEVELS.map((l) => (
            <button key={l.key} onClick={() => setLevel(l.key)}
              className={cn("px-3 py-1.5 rounded-full text-xs font-bold transition-all",
                level === l.key ? "bg-white shadow-sm text-primary" : "text-on-surface-muted")}>
              {l.label}
            </button>
          ))}
        </div>
        <div className="w-[140px]">
          <label className="mb-1 block font-label text-[9px] font-bold uppercase tracking-wider text-on-surface-muted">From</label>
          <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)}
            className="h-9 w-full rounded-xl border border-surface-mid bg-white px-3 font-body text-xs font-semibold text-on-surface focus:outline-none focus:ring-2 focus:ring-violet-200" />
        </div>
        <div className="w-[140px]">
          <label className="mb-1 block font-label text-[9px] font-bold uppercase tracking-wider text-on-surface-muted">To</label>
          <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)}
            className="h-9 w-full rounded-xl border border-surface-mid bg-white px-3 font-body text-xs font-semibold text-on-surface focus:outline-none focus:ring-2 focus:ring-violet-200" />
        </div>
        <button onClick={() => mutate()} disabled={isValidating}
          className="flex items-center justify-center gap-2 px-3 py-2 rounded-xl bg-white border border-[#e8e3db] hover:bg-[#f0ece4] text-[#1c1917] font-label text-xs font-bold transition-all disabled:opacity-40 shadow-sm">
          <RefreshCw size={12} className={isValidating ? "animate-spin" : ""} /> Refresh
        </button>
      </div>

      <div className="card rounded-2xl overflow-hidden">
        {rows.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-center px-4">
            <div className="w-14 h-14 rounded-2xl bg-violet-50 flex items-center justify-center mb-3">
              <Megaphone size={24} className="text-violet-400" />
            </div>
            <h3 className="font-bold text-[#44403c] text-base mb-1">No ad data yet</h3>
            <p className="text-sm text-[#a8a29e] max-w-sm leading-relaxed">
              Once your Meta ads deliver and the daily sync runs, campaigns appear here with
              spend, results and lead-quality breakdown.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[1000px]">
              <thead>
                <tr className="border-b border-surface-mid bg-surface-low/60">
                  <th className="px-3 py-3 font-label text-[10px] font-bold text-on-surface-muted uppercase tracking-wider">On</th>
                  {headers.map((h, i) => (
                    <th key={h} className={cn(
                      "px-4 py-3 font-label text-[10px] font-bold text-on-surface-muted uppercase tracking-wider whitespace-nowrap",
                      i === 0 ? "text-left" : i === 1 ? "text-center" : "text-right")}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-mid/50">
                {rows.map((r) => (
                  <tr key={r.group_id} className="hover:bg-surface-low/60 transition-colors">
                    <td className="px-3 py-3">
                      {level === "campaign" ? (
                        <button onClick={() => toggleStatus(r)} disabled={busy[r.group_id]}
                          className={cn("relative h-5 w-9 rounded-full transition-colors disabled:opacity-50",
                            (r.status ?? "").toUpperCase() === "ACTIVE" ? "bg-emerald-500" : "bg-surface-mid")}>
                          <span className={cn("absolute top-0.5 h-4 w-4 rounded-full bg-white transition-transform",
                            (r.status ?? "").toUpperCase() === "ACTIVE" ? "translate-x-4" : "translate-x-0.5")} />
                        </button>
                      ) : <span className="text-on-surface-muted">—</span>}
                    </td>
                    <td className="px-4 py-3"><span className="font-label text-sm font-semibold text-on-surface">{r.name}</span></td>
                    <td className="px-4 py-3 text-center"><StatusBadge status={r.status} /></td>
                    <td className="px-4 py-3 text-right text-xs whitespace-nowrap">
                      {level === "campaign" ? (
                        <button onClick={() => editBudget(r)} className="text-primary hover:underline">
                          {r.budget_label ?? "Set"} ✎
                        </button>
                      ) : <span className="text-on-surface-muted">{r.budget_label ?? "—"}</span>}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums">{money(r.spend)}</td>
                    <td className="px-4 py-3 text-right tabular-nums text-on-surface-muted">{r.impressions.toLocaleString("en-IN")}</td>
                    <td className="px-4 py-3 text-right tabular-nums text-on-surface-muted">{r.reach.toLocaleString("en-IN")}</td>
                    <td className="px-4 py-3 text-right tabular-nums font-semibold text-on-surface" title={r.result_label}>{r.results.toLocaleString("en-IN")}</td>
                    <td className="px-4 py-3 text-right tabular-nums">{money(r.cost_per_result)}</td>
                    <td className="px-4 py-3 text-right tabular-nums text-violet-700">{r.clicks.toLocaleString("en-IN")}</td>
                    <td className="px-4 py-3 text-right tabular-nums font-bold">{r.messages.toLocaleString("en-IN")}</td>
                    <td className="px-4 py-3 text-right tabular-nums text-on-surface-muted">{r.clicked_no_message.toLocaleString("en-IN")}</td>
                    <td className="px-4 py-3 text-right tabular-nums text-on-surface-muted">{r.qualified}</td>
                    <td className="px-4 py-3 text-right tabular-nums font-semibold text-emerald-700">{r.hot}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
