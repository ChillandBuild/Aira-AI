"use client";
import { useEffect, useState } from "react";
import { TrendingUp, Target, Phone, Percent } from "lucide-react";
import { API_URL, getAuthHeaders } from "@/lib/api";
import { DayStrip, type DailyMessageStat } from "@/components/DayStrip";
import { StatCard } from "../components/stat-card";
import { SkeletonCard } from "../components/skeleton";

async function apiFetch<T>(path: string): Promise<T> {
  const auth = await getAuthHeaders();
  const res = await fetch(`${API_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...auth },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail || "Request failed");
  }
  return res.json() as Promise<T>;
}

interface AnalyticsData {
  delivery_rate: number | null;
  avg_score: number | null;
  total_calls?: number;
  connect_rate?: number;
}

type Range = "7" | "30" | "90" | "all" | "custom";

function isoDaysAgo(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString().slice(0, 10);
}

export function AnalyticsView({ tenantId }: { tenantId: string }) {
  const [data, setData] = useState<AnalyticsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dailyMessages, setDailyMessages] = useState<DailyMessageStat[] | null>(null);
  const [range, setRange] = useState<Range>("7");
  const [fromDate, setFromDate] = useState(() => isoDaysAgo(30));
  const [toDate, setToDate] = useState(() => isoDaysAgo(0));

  const customRangeInvalid = range === "custom" && (!fromDate || !toDate || fromDate > toDate);

  useEffect(() => {
    setLoading(true);
    apiFetch<AnalyticsData>(`/api/v1/operator/clients/${tenantId}/dashboard/analytics`)
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, [tenantId]);

  useEffect(() => {
    if (customRangeInvalid) return;
    setDailyMessages(null);
    const query =
      range === "all" ? "all_time=true"
      : range === "custom" ? `from_date=${fromDate}&to_date=${toDate}`
      : `range_days=${range}`;
    apiFetch<{ daily_messages: DailyMessageStat[] }>(
      `/api/v1/operator/clients/${tenantId}/dashboard/daily-messages?${query}`,
    )
      .then((res) => setDailyMessages(res.daily_messages))
      .catch(() => setDailyMessages([]));
  }, [tenantId, range, fromDate, toDate, customRangeInvalid]);

  if (loading) {
    return (
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
        <SkeletonCard /><SkeletonCard /><SkeletonCard />
        <SkeletonCard /><SkeletonCard />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 bg-red-50 border border-danger/20 rounded-xl text-sm text-danger">
        {error}
      </div>
    );
  }

  if (!data) return null;

  const hasTelecalling = typeof data.total_calls === "number";

  return (
    <div className="space-y-6">
      <div className="bg-white rounded-card border border-border p-5 shadow-sm">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <h3 className="text-xs font-medium uppercase tracking-wider font-label text-ink-muted">
            Daily Activity
          </h3>
          <div className="flex flex-col items-end gap-2">
            <div className="inline-flex rounded-lg bg-surface-mid p-0.5">
              {(["7", "30", "90", "all", "custom"] as Range[]).map(r => (
                <button
                  key={r}
                  onClick={() => setRange(r)}
                  className={`rounded-md px-2.5 py-1 text-xs font-semibold transition ${
                    range === r ? "bg-white text-ink shadow-sm" : "text-ink-secondary"
                  }`}
                >
                  {r === "7" ? "7 days" : r === "30" ? "30 days" : r === "90" ? "90 days" : r === "all" ? "All time" : "Custom"}
                </button>
              ))}
            </div>
            {range === "custom" && (
              <div className="flex items-center gap-2">
                <input
                  type="date"
                  value={fromDate}
                  max={toDate}
                  onChange={e => setFromDate(e.target.value)}
                  className="rounded-md border border-border px-2 py-1 text-xs font-mono focus:border-primary focus:outline-none"
                />
                <span className="text-xs text-ink-muted">to</span>
                <input
                  type="date"
                  value={toDate}
                  min={fromDate}
                  max={isoDaysAgo(0)}
                  onChange={e => setToDate(e.target.value)}
                  className="rounded-md border border-border px-2 py-1 text-xs font-mono focus:border-primary focus:outline-none"
                />
              </div>
            )}
            {customRangeInvalid && (
              <p className="text-[11px] text-danger">Pick a &ldquo;to&rdquo; date on or after &ldquo;from&rdquo;.</p>
            )}
          </div>
        </div>
        {dailyMessages === null ? (
          <SkeletonCard />
        ) : (
          <DayStrip data={dailyMessages} />
        )}
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
        <StatCard
          icon={<TrendingUp size={18} />}
          label="Delivery Rate"
          value={data.delivery_rate != null ? `${data.delivery_rate.toFixed(1)}%` : "—"}
        />
        <StatCard
          icon={<Target size={18} />}
          label="Avg Score"
          value={data.avg_score != null ? data.avg_score.toFixed(1) : "—"}
        />
        {hasTelecalling && (
          <>
            <StatCard
              icon={<Phone size={18} />}
              label="Total Calls"
              value={data.total_calls!}
            />
            <StatCard
              icon={<Percent size={18} />}
              label="Connect Rate"
              value={data.connect_rate != null ? `${data.connect_rate.toFixed(1)}%` : "—"}
            />
          </>
        )}
      </div>
    </div>
  );
}
