"use client";
import { useCallback, useEffect, useState } from "react";
import { RefreshCw, CheckCircle2, AlertTriangle, XCircle, Clock, Pause, Play, Check, Activity, HardDrive, Cpu } from "lucide-react";
import { API_URL, getAuthHeaders } from "@/lib/api";
import { relTime, operatorFetch } from "@/lib/operator";
import { ConfirmModal } from "../components/confirm-modal";
import { OperatorToggle } from "../components/operator-toggle";

interface SystemHealth {
  status: "healthy" | "unhealthy";
  uptime_seconds: number;
  uptime_human: string;
  started_at: string;
  server_time: string;
  details: {
    database: string;
    scheduler_jobs: Record<string, { status: string; last_heartbeat: string | null }>;
  };
}

interface OperatorHealth {
  status: string;
  uptime_seconds: number;
  uptime_human: string;
  memory_mb: number;
  cpu_percent: number;
  python_version: string;
  server_time: string;
  started_at: string;
}

function SystemHealthCard({ health, operatorHealth, loading }: { health: SystemHealth | null; operatorHealth: OperatorHealth | null; loading: boolean }) {
  if (loading) {
    return (
      <div className="mb-6 p-4 bg-white rounded-card border border-border animate-pulse">
        <div className="h-5 bg-surface-mid rounded w-32 mb-3" />
        <div className="flex gap-6">
          <div className="h-4 bg-surface-mid rounded w-24" />
          <div className="h-4 bg-surface-mid rounded w-24" />
          <div className="h-4 bg-surface-mid rounded w-24" />
        </div>
      </div>
    );
  }

  const isHealthy = health?.status === "healthy";
  const dbOk = health?.details?.database === "ok";
  const uptime = operatorHealth?.uptime_human || health?.uptime_human || "—";
  const memoryMb = operatorHealth?.memory_mb;
  const cpuPercent = operatorHealth?.cpu_percent;

  return (
    <div className={`mb-6 rounded-card border shadow-card overflow-hidden ${
      isHealthy ? "bg-white border-border" : "bg-red-50 border-danger/30"
    }`}>
      <div className="px-5 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className={`w-2.5 h-2.5 rounded-full ${isHealthy ? "bg-emerald-500 animate-pulse" : "bg-red-500"}`} />
          <span className="text-sm font-semibold text-ink">
            Render Backend
          </span>
          <span className={`px-2 py-0.5 rounded-full text-[11px] font-medium ${
            isHealthy ? "bg-emerald-50 text-emerald-700" : "bg-red-100 text-red-700"
          }`}>
            {isHealthy ? "LIVE" : "UNHEALTHY"}
          </span>
        </div>
        <div className="flex items-center gap-5 text-xs text-ink-muted">
          <div className="flex items-center gap-1.5" title="Uptime since last deploy">
            <Clock size={12} className="opacity-60" />
            <span className="font-mono">{uptime}</span>
          </div>
          {memoryMb != null && (
            <div className="flex items-center gap-1.5" title="Memory usage">
              <HardDrive size={12} className="opacity-60" />
              <span className="font-mono">{memoryMb} MB</span>
            </div>
          )}
          {cpuPercent != null && (
            <div className="flex items-center gap-1.5" title="CPU usage">
              <Cpu size={12} className="opacity-60" />
              <span className="font-mono">{cpuPercent.toFixed(1)}%</span>
            </div>
          )}
          <div className="flex items-center gap-1.5" title="Database">
            <Activity size={12} className="opacity-60" />
            <span className={`font-medium ${dbOk ? "text-emerald-600" : "text-red-600"}`}>
              DB {dbOk ? "OK" : "ERR"}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

interface JobHealth {
  id: string;
  next_run: string | null;
  last_status: "success" | "error" | "missed" | null;
  last_run: string | null;
  last_lateness_ms: number | null;
  last_error: string | null;
  errors_24h: number;
  paused: boolean;
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

const CRITICAL_JOB_IDS = new Set([
  "scheduled-broadcasts",
  "broadcast-retries",
  "reengagement-rules",
  "assignment-sweep",
  "callback-reassignment",
]);

type Health = "healthy" | "warn" | "down" | "pending" | "paused";

function jobHealth(j: JobHealth): Health {
  if (j.paused) return "paused";
  if (j.errors_24h > 0 || j.last_status === "error") return "down";
  if (!j.last_status) return j.next_run ? "pending" : "warn";
  if (j.last_status === "missed") return "warn";
  return "healthy";
}

const HEALTH_STYLE: Record<Health, { ring: string; badge: string; label: string; Icon: typeof CheckCircle2 }> = {
  healthy: { ring: "border-emerald-200", badge: "bg-emerald-50 text-emerald-700", label: "Healthy", Icon: CheckCircle2 },
  warn: { ring: "border-amber-200", badge: "bg-amber-50 text-amber-700", label: "Late", Icon: AlertTriangle },
  down: { ring: "border-rose-200", badge: "bg-rose-50 text-rose-700", label: "Failing", Icon: XCircle },
  pending: { ring: "border-border", badge: "bg-surface-mid text-ink-muted", label: "Awaiting first run", Icon: Clock },
  paused: { ring: "border-border", badge: "bg-surface-mid text-ink-muted", label: "Paused", Icon: Pause },
};

export default function SchedulerHealthPage() {
  const [data, setData] = useState<SchedulerHealth | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [toggling, setToggling] = useState<string | null>(null);
  const [pauseConfirmJob, setPauseConfirmJob] = useState<JobHealth | null>(null);
  const [running, setRunning] = useState<string | null>(null);
  const [justRan, setJustRan] = useState<string | null>(null);

  const [systemHealth, setSystemHealth] = useState<SystemHealth | null>(null);
  const [operatorHealth, setOperatorHealth] = useState<OperatorHealth | null>(null);
  const [healthLoading, setHealthLoading] = useState(true);

  const loadHealth = useCallback(async () => {
    try {
      const [healthRes, opRes] = await Promise.allSettled([
        fetch(`${API_URL}/ready`).then(r => r.json()),
        operatorFetch<OperatorHealth>("/api/v1/operator/system-health"),
      ]);
      if (healthRes.status === "fulfilled") setSystemHealth(healthRes.value);
      if (opRes.status === "fulfilled") setOperatorHealth(opRes.value);
    } catch {
      // silent — card shows stale or loading state
    } finally {
      setHealthLoading(false);
    }
  }, []);

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

  const toggleJob = useCallback(async (jobId: string) => {
    if (toggling) return;
    setToggling(jobId);
    setData((prev) =>
      prev
        ? {
            ...prev,
            jobs: prev.jobs.map((j) =>
              j.id === jobId ? { ...j, paused: !j.paused } : j
            ),
          }
        : prev
    );
    try {
      const auth = await getAuthHeaders();
      const res = await fetch(
        `${API_URL}/api/v1/operator/scheduler/${jobId}/toggle`,
        { method: "POST", headers: { ...auth } }
      );
      if (!res.ok) throw new Error(`Toggle failed (${res.status})`);
      await load();
    } catch (e) {
      setData((prev) =>
        prev
          ? {
              ...prev,
              jobs: prev.jobs.map((j) =>
                j.id === jobId ? { ...j, paused: !j.paused } : j
              ),
            }
          : prev
      );
      setError(e instanceof Error ? e.message : "Toggle failed");
    } finally {
      setToggling(null);
    }
  }, [toggling, load]);

  const requestToggle = useCallback((job: JobHealth) => {
    const isPausing = !job.paused;
    if (isPausing && CRITICAL_JOB_IDS.has(job.id)) {
      setPauseConfirmJob(job);
      return;
    }
    toggleJob(job.id);
  }, [toggleJob]);

  const confirmPause = useCallback(() => {
    if (!pauseConfirmJob) return;
    const jobId = pauseConfirmJob.id;
    setPauseConfirmJob(null);
    toggleJob(jobId);
  }, [pauseConfirmJob, toggleJob]);

  const runJob = useCallback(async (jobId: string) => {
    if (running) return;
    setRunning(jobId);
    setError(null);
    try {
      const auth = await getAuthHeaders();
      const res = await fetch(
        `${API_URL}/api/v1/operator/scheduler/${jobId}/run`,
        { method: "POST", headers: { ...auth } }
      );
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail || `Run failed (${res.status})`);
      }
      setJustRan(jobId);
      setTimeout(() => setJustRan((prev) => (prev === jobId ? null : prev)), 2500);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Run failed");
    } finally {
      setRunning(null);
    }
  }, [running, load]);

  useEffect(() => {
    load();
    loadHealth();
    const id = setInterval(() => { load(); loadHealth(); }, 30_000);
    return () => clearInterval(id);
  }, [load, loadHealth]);

  return (
    <div className="max-w-6xl mx-auto px-8 py-8">
      <div className="flex items-center justify-between mb-2">
        <h1 className="text-2xl font-bold text-ink">Scheduler Health</h1>
        <button
          onClick={load}
          className="flex items-center gap-1.5 text-sm text-ink-muted hover:text-ink"
        >
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} /> Refresh
        </button>
      </div>
      <p className="text-sm text-ink-muted mb-6">
        Platform-wide background jobs (run once for all tenants). Auto-refreshes every 30s.
      </p>

      {/* System Health — Aira's own server, same "is our infrastructure OK" question this page already answers for background jobs */}
      <SystemHealthCard health={systemHealth} operatorHealth={operatorHealth} loading={healthLoading} />

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
                  <p className="font-semibold text-ink text-sm">{meta.name}</p>
                  <p className="text-[11px] text-ink-muted font-mono">{j.id} · every {meta.every}</p>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold ${style.badge}`}>
                    <style.Icon size={11} /> {style.label}
                  </span>
                  <button
                    type="button"
                    onClick={() => runJob(j.id)}
                    disabled={j.paused || running === j.id}
                    aria-label={`Run ${meta.name} now`}
                    title={j.paused ? "Resume the job before running it" : "Run now"}
                    className="flex items-center justify-center w-6 h-6 rounded-full text-ink-muted hover:text-ink hover:bg-surface-mid disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-transparent transition-colors"
                  >
                    {justRan === j.id ? (
                      <Check size={13} className="text-emerald-600" />
                    ) : (
                      <Play size={13} className={running === j.id ? "animate-pulse" : ""} />
                    )}
                  </button>
                  <OperatorToggle
                    checked={!j.paused}
                    onChange={() => requestToggle(j)}
                    loading={toggling === j.id}
                    size="sm"
                    aria-label={j.paused ? `Resume ${meta.name}` : `Pause ${meta.name}`}
                  />
                </div>
              </div>
              <dl className="space-y-1.5 text-xs">
                <div className="flex justify-between">
                  <dt className="text-ink-muted">Next run</dt>
                  <dd className="text-ink-secondary font-medium">{j.paused ? "Paused" : relTime(j.next_run)}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-ink-muted">Last run</dt>
                  <dd className="text-ink-secondary font-medium">
                    {relTime(j.last_run)}
                    {lateSec != null && lateSec > 1 && (
                      <span className="text-warning"> (+{lateSec}s late)</span>
                    )}
                  </dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-ink-muted">Errors (24h)</dt>
                  <dd className={j.errors_24h > 0 ? "text-danger font-bold" : "text-ink-secondary font-medium"}>
                    {j.errors_24h}
                  </dd>
                </div>
              </dl>
              {j.last_error && (
                <p className="mt-3 text-[11px] text-danger bg-red-50 rounded-lg p-2 break-words line-clamp-3">
                  {j.last_error}
                </p>
              )}
            </div>
          );
        })}
      </div>

      {!loading && (data?.jobs?.length ?? 0) === 0 && (
        <p className="text-sm text-ink-muted py-12 text-center">No jobs reported.</p>
      )}

      {(data?.recent_failures?.length ?? 0) > 0 && (
        <div className="mt-8">
          <h2 className="text-sm font-bold text-ink-secondary mb-3">Recent failures</h2>
          <div className="bg-white rounded-2xl border border-border divide-y divide-border-subtle">
            {data!.recent_failures.map((f, i) => (
              <div key={i} className="px-4 py-3 flex items-start justify-between gap-4 text-xs">
                <div className="min-w-0">
                  <span className="font-mono text-ink-secondary">{f.job_id}</span>
                  <span className={`ml-2 font-semibold ${f.status === "error" ? "text-danger" : "text-warning"}`}>
                    {f.status}
                  </span>
                  {f.error && <p className="text-ink-muted truncate mt-0.5">{f.error}</p>}
                </div>
                <span className="text-ink-muted whitespace-nowrap shrink-0">{relTime(f.ran_at)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <ConfirmModal
        open={pauseConfirmJob !== null}
        onClose={() => setPauseConfirmJob(null)}
        onConfirm={confirmPause}
        title={`Pause ${pauseConfirmJob ? (JOB_LABELS[pauseConfirmJob.id]?.name ?? pauseConfirmJob.id) : "job"}?`}
        description={`This is a platform-critical job that runs once for every tenant. Pausing it will halt "${pauseConfirmJob ? (JOB_LABELS[pauseConfirmJob.id]?.name ?? pauseConfirmJob.id) : ""}" for all clients until it is resumed.`}
        confirmLabel="Pause job"
        tone="warning"
        loading={toggling === pauseConfirmJob?.id}
      />
    </div>
  );
}
