"use client";
import { useCallback, useEffect, useState } from "react";
import { RefreshCw, CheckCircle2, AlertTriangle, XCircle, Clock } from "lucide-react";
import { API_URL, getAuthHeaders } from "@/lib/api";

interface JobHealth {
  id: string;
  next_run: string | null;
  last_status: "success" | "error" | "missed" | null;
  last_run: string | null;
  last_lateness_ms: number | null;
  last_error: string | null;
  errors_24h: number;
}

interface SchedulerHealth {
  jobs: JobHealth[];
  recent_failures: { job_id: string; status: string; ran_at: string; error: string | null }[];
  server_time: string;
}

const JOB_LABELS: Record<string, { name: string; every: string }> = {
  "scheduled-broadcasts": { name: "Scheduled Broadcasts", every: "1 min" },
  "broadcast-retries": { name: "Broadcast Auto-Retry", every: "5 min" },
  "token-health-check": { name: "Meta Token Health", every: "24 h" },
  "number-quality-sync": { name: "Number Quality Sync", every: "24 h" },
  "engagement-decay": { name: "Engagement Decay", every: "6 h" },
  "reengagement-rules": { name: "Re-engagement Rules", every: "1 min" },
  "assignment-sweep": { name: "Unassigned-Lead Sweep", every: "2 min" },
  "recycle-contacts": { name: "Contact Recycling", every: "30 min" },
  "callback-reassignment": { name: "Callback Reassignment", every: "1 min" },
  "daily-digest": { name: "Daily Caller Digest", every: "18:30 IST" },
};

function relTime(iso: string | null): string {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso).getTime();
  const ahead = diff < 0;
  const s = Math.abs(diff) / 1000;
  const fmt = s < 60 ? `${Math.round(s)}s` : s < 3600 ? `${Math.round(s / 60)}m` : `${Math.round(s / 3600)}h`;
  return ahead ? `in ${fmt}` : `${fmt} ago`;
}

type Health = "healthy" | "warn" | "down" | "pending";

function jobHealth(j: JobHealth): Health {
  if (j.errors_24h > 0 || j.last_status === "error") return "down";
  if (!j.last_status) return j.next_run ? "pending" : "warn";
  if (j.last_status === "missed") return "warn";
  return "healthy";
}

const HEALTH_STYLE: Record<Health, { ring: string; badge: string; label: string; Icon: typeof CheckCircle2 }> = {
  healthy: { ring: "border-emerald-200", badge: "bg-emerald-50 text-emerald-700", label: "Healthy", Icon: CheckCircle2 },
  warn: { ring: "border-amber-200", badge: "bg-amber-50 text-amber-700", label: "Late", Icon: AlertTriangle },
  down: { ring: "border-rose-200", badge: "bg-rose-50 text-rose-700", label: "Failing", Icon: XCircle },
  pending: { ring: "border-gray-200", badge: "bg-gray-100 text-gray-500", label: "Awaiting first run", Icon: Clock },
};

export default function SchedulerHealthPage() {
  const [data, setData] = useState<SchedulerHealth | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const auth = await getAuthHeaders();
      const res = await fetch(`${API_URL}/api/v1/operator/scheduler-health`, {
        headers: { ...auth },
        cache: "no-store",
      });
      if (!res.ok) throw new Error(`Request failed (${res.status})`);
      setData(await res.json());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 30_000);
    return () => clearInterval(id);
  }, [load]);

  return (
    <div className="max-w-6xl mx-auto px-8 py-8">
      <div className="flex items-center justify-between mb-2">
        <h1 className="text-2xl font-bold text-gray-900">Scheduler Health</h1>
        <button
          onClick={load}
          className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-800"
        >
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} /> Refresh
        </button>
      </div>
      <p className="text-sm text-gray-500 mb-6">
        Platform-wide background jobs (run once for all tenants). Auto-refreshes every 30s.
      </p>

      {error && (
        <div className="mb-4 p-3 rounded-lg bg-rose-50 text-rose-700 text-sm">{error}</div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {(data?.jobs ?? []).map((j) => {
          const health = jobHealth(j);
          const style = HEALTH_STYLE[health];
          const meta = JOB_LABELS[j.id] ?? { name: j.id, every: "—" };
          const lateSec = j.last_lateness_ms != null ? Math.round(j.last_lateness_ms / 1000) : null;
          return (
            <div key={j.id} className={`bg-white rounded-2xl border ${style.ring} p-5 shadow-sm`}>
              <div className="flex items-start justify-between gap-2 mb-3">
                <div>
                  <p className="font-semibold text-gray-900 text-sm">{meta.name}</p>
                  <p className="text-[11px] text-gray-400 font-mono">{j.id} · every {meta.every}</p>
                </div>
                <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold ${style.badge}`}>
                  <style.Icon size={11} /> {style.label}
                </span>
              </div>
              <dl className="space-y-1.5 text-xs">
                <div className="flex justify-between">
                  <dt className="text-gray-400">Next run</dt>
                  <dd className="text-gray-700 font-medium">{relTime(j.next_run)}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-gray-400">Last run</dt>
                  <dd className="text-gray-700 font-medium">
                    {relTime(j.last_run)}
                    {lateSec != null && lateSec > 1 && (
                      <span className="text-amber-600"> (+{lateSec}s late)</span>
                    )}
                  </dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-gray-400">Errors (24h)</dt>
                  <dd className={j.errors_24h > 0 ? "text-rose-600 font-bold" : "text-gray-700 font-medium"}>
                    {j.errors_24h}
                  </dd>
                </div>
              </dl>
              {j.last_error && (
                <p className="mt-3 text-[11px] text-rose-600 bg-rose-50 rounded-lg p-2 break-words line-clamp-3">
                  {j.last_error}
                </p>
              )}
            </div>
          );
        })}
      </div>

      {!loading && (data?.jobs?.length ?? 0) === 0 && (
        <p className="text-sm text-gray-400 py-12 text-center">No jobs reported.</p>
      )}

      {(data?.recent_failures?.length ?? 0) > 0 && (
        <div className="mt-8">
          <h2 className="text-sm font-bold text-gray-700 mb-3">Recent failures</h2>
          <div className="bg-white rounded-2xl border border-gray-200 divide-y divide-gray-100">
            {data!.recent_failures.map((f, i) => (
              <div key={i} className="px-4 py-3 flex items-start justify-between gap-4 text-xs">
                <div className="min-w-0">
                  <span className="font-mono text-gray-700">{f.job_id}</span>
                  <span className={`ml-2 font-semibold ${f.status === "error" ? "text-rose-600" : "text-amber-600"}`}>
                    {f.status}
                  </span>
                  {f.error && <p className="text-gray-400 truncate mt-0.5">{f.error}</p>}
                </div>
                <span className="text-gray-400 whitespace-nowrap shrink-0">{relTime(f.ran_at)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
