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

export function AnalyticsView({ tenantId }: { tenantId: string }) {
  const [data, setData] = useState<AnalyticsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dailyMessages, setDailyMessages] = useState<DailyMessageStat[] | null>(null);

  useEffect(() => {
    setLoading(true);
    apiFetch<AnalyticsData>(`/api/v1/operator/clients/${tenantId}/dashboard/analytics`)
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, [tenantId]);

  useEffect(() => {
    setDailyMessages(null);
    apiFetch<{ daily_messages: DailyMessageStat[] }>(
      `/api/v1/operator/clients/${tenantId}/dashboard/daily-messages`,
    )
      .then((res) => setDailyMessages(res.daily_messages))
      .catch(() => setDailyMessages([]));
  }, [tenantId]);

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
        <h3 className="text-xs font-medium uppercase tracking-wider font-label text-ink-muted mb-4">
          Daily Activity
        </h3>
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
