"use client";
import { useEffect, useState, useMemo } from "react";
import {
  Phone, Loader2, Activity, TrendingUp, Coffee, UserCircle, Clock, BarChart3, Calendar,
} from "lucide-react";
import { api, TimelineEvent, CallLog } from "@/lib/api";
import { format, differenceInSeconds, subDays, startOfDay, isSameDay } from "date-fns";
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, BarChart, Bar } from "recharts";
import { formatDuration, initials } from "./helpers";
import AttendanceMini from "./AttendanceMini";

interface StatusSummary {
  active_minutes_today: number;
  break_minutes_today: number;
  idle_minutes_today: number;
  current_status: string;
  since: string;
  first_login_at: string | null;
  last_logout_at: string | null;
  breaks: { started_at: string; ended_at: string | null; duration_minutes: number }[];
  scheduled_count: number;
}

interface GapEvent {
  type: "idle";
  id: string;
  started_at: string;
  duration_seconds: number;
}

type DisplayEvent = TimelineEvent | GapEvent;

const OUTCOME_COLORS: Record<string, string> = {
  converted: "#10b981",
  callback: "#f59e0b",
  not_interested: "#f43f5e",
  no_answer: "#94a3b8",
  do_not_call: "#7c3aed",
  do_not_contact: "#7c3aed",
  in_progress: "#6366f1",
};

const OUTCOME_LABELS: Record<string, string> = {
  converted: "Converted",
  callback: "Callback",
  not_interested: "Not Interested",
  no_answer: "No Answer",
  do_not_call: "DNC",
  do_not_contact: "DNC",
  in_progress: "In Progress",
};

export default function TeamProfilePanel({ callerId, callerName }: { callerId: string, callerName: string }) {
  const [loading, setLoading] = useState(true);
  const [date, setDate] = useState(() => format(new Date(), "yyyy-MM-dd"));
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [summary, setSummary] = useState<StatusSummary | null>(null);
  const [callLogs, setCallLogs] = useState<CallLog[]>([]);

  useEffect(() => {
    let cancelled = false;
    async function loadData() {
      setLoading(true);
      try {
        const [sumRes, timeRes, logsRes] = await Promise.all([
          api.callers.statusSummary(callerId),
          api.callers.getTimeline(callerId, date),
          api.callers.logs(callerId),
        ]);
        if (cancelled) return;
        setSummary(sumRes);
        setTimeline(timeRes.data);
        setCallLogs(logsRes);
      } catch (e) {
        console.error(e);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    loadData();
    return () => { cancelled = true; };
  }, [date, callerId]);

  const todayCallEvents = useMemo(() => timeline.filter((e) => e.type === "call"), [timeline]);
  const totalDurationSeconds = useMemo(() => callLogs.reduce((s, l) => s + (l.duration_seconds ?? 0), 0), [callLogs]);
  const conversionRate = useMemo(() => {
    if (callLogs.length === 0) return 0;
    const converted = callLogs.filter((l) => l.outcome === "converted").length;
    return Math.round((converted / callLogs.length) * 100);
  }, [callLogs]);
  const avgScore = useMemo(() => {
    const scored = callLogs.filter((l) => l.score !== null);
    if (scored.length === 0) return 0;
    return +(scored.reduce((s, l) => s + (l.score ?? 0), 0) / scored.length).toFixed(1);
  }, [callLogs]);

  const dailyTrend = useMemo(() => {
    const days: { label: string; dateStr: string; calls: number; converted: number }[] = [];
    const now = new Date();
    for (let i = 13; i >= 0; i--) {
      const d = subDays(now, i);
      days.push({ label: format(d, "MMM d"), dateStr: format(d, "yyyy-MM-dd"), calls: 0, converted: 0 });
    }
    callLogs.forEach((log) => {
      const logDate = startOfDay(new Date(log.created_at));
      const match = days.find((d) => isSameDay(new Date(d.dateStr), logDate));
      if (match) {
        match.calls++;
        if (log.outcome === "converted") match.converted++;
      }
    });
    return days;
  }, [callLogs]);

  const outcomeBreakdown = useMemo(() => {
    const map: Record<string, number> = {};
    callLogs.forEach((l) => {
      const key = l.outcome ?? "unknown";
      map[key] = (map[key] ?? 0) + 1;
    });
    return map;
  }, [callLogs]);
  const outcomeTotal = useMemo(() => Object.values(outcomeBreakdown).reduce((a, b) => a + b, 0), [outcomeBreakdown]);

  const hourlyDistribution = useMemo(() => {
    const hours = Array.from({ length: 24 }, (_, h) => ({ hour: `${h}`, calls: 0 }));
    callLogs.forEach((log) => {
      const h = new Date(log.created_at).getHours();
      hours[h].calls++;
    });
    return hours;
  }, [callLogs]);

  const timeDist = useMemo(() => {
    if (!summary) return { active: 0, breakPct: 0, idle: 0 };
    const total = summary.active_minutes_today + summary.break_minutes_today + summary.idle_minutes_today;
    if (total === 0) return { active: 0, breakPct: 0, idle: 0 };
    return {
      active: Math.round((summary.active_minutes_today / total) * 100),
      breakPct: Math.round((summary.break_minutes_today / total) * 100),
      idle: Math.round((summary.idle_minutes_today / total) * 100),
    };
  }, [summary]);

  const eventsWithGaps = useMemo<DisplayEvent[]>(() => {
    const result: DisplayEvent[] = [];
    for (let i = 0; i < timeline.length; i++) {
      result.push(timeline[i]);
      if (i < timeline.length - 1) {
        const current = timeline[i];
        const next = timeline[i + 1];
        let currentEnd: Date;
        if (current.type === "status" && current.ended_at) {
          currentEnd = new Date(current.ended_at);
        } else if (current.type === "call" && current.duration_seconds) {
          currentEnd = new Date(new Date(current.started_at).getTime() + current.duration_seconds * 1000);
        } else {
          currentEnd = new Date(current.started_at);
        }
        const nextStart = new Date(next.started_at);
        const gapSeconds = differenceInSeconds(nextStart, currentEnd);
        if (gapSeconds > 120 && current.status !== "logged_out" && current.status !== "break") {
          result.push({ type: "idle", id: `gap-${i}`, started_at: currentEnd.toISOString(), duration_seconds: gapSeconds });
        }
      }
    }
    return result;
  }, [timeline]);

  const scoreRingPct = Math.min(avgScore / 10, 1);
  const RING_RADIUS = 30;
  const RING_CIRC = 2 * Math.PI * RING_RADIUS;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full min-h-[400px]">
        <Loader2 className="animate-spin text-primary" size={24} />
      </div>
    );
  }

  const statusColor = summary?.current_status === "active" ? "bg-emerald-500"
    : summary?.current_status === "break" ? "bg-amber-500"
      : "bg-[#a8a29e]";
  const statusLabel = summary?.current_status === "active" ? "Active"
    : summary?.current_status === "break" ? "On Break"
      : "Offline";

  return (
    <div className="space-y-6 max-h-[calc(100vh-120px)] overflow-y-auto pr-2 pb-10 custom-scrollbar">
      {/* HEADER */}
      <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-[#292524] via-[#1c1917] to-[#1c1917] p-6">
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className="w-14 h-14 rounded-full bg-gradient-to-br from-amber-400 to-orange-500 flex items-center justify-center text-white font-display text-lg font-bold shadow-lg">
              {initials(callerName)}
            </div>
            <div>
              <h2 className="font-display text-lg font-bold text-white">{callerName}</h2>
              <div className="flex items-center gap-2 mt-1">
                <span className={`w-2 h-2 rounded-full ${statusColor}`} />
                <span className="text-xs text-[#d6cfc9] font-body">{statusLabel}</span>
              </div>
            </div>
          </div>
          <div className="flex flex-col items-center gap-1 relative">
            <svg width="70" height="70" viewBox="0 0 70 70" className="transform -rotate-90">
              <circle cx="35" cy="35" r={RING_RADIUS} fill="none" stroke="rgba(255,255,255,0.1)" strokeWidth="6" />
              <circle cx="35" cy="35" r={RING_RADIUS} fill="none"
                stroke={avgScore >= 7 ? "#10b981" : avgScore >= 4 ? "#f59e0b" : "#f43f5e"}
                strokeWidth="6" strokeLinecap="round" strokeDasharray={`${scoreRingPct * RING_CIRC} ${RING_CIRC}`}
                className="transition-all duration-700" />
            </svg>
            <div className="absolute inset-0 flex items-center justify-center mt-[-4px]">
               <span className="text-white font-display text-sm font-bold">{avgScore}</span>
            </div>
            <span className="text-[9px] font-label text-[#a8a29e] uppercase tracking-wide">Avg Score</span>
          </div>
        </div>
        <div className="flex flex-wrap gap-x-5 gap-y-1 mt-4 text-xs text-[#a8a29e] font-body">
          {summary?.first_login_at && (
            <span>Login: <span className="text-[#e8e3db]">{format(new Date(summary.first_login_at), "h:mm a")}</span></span>
          )}
          {summary?.last_logout_at && (
            <span>Logout: <span className="text-[#e8e3db]">{format(new Date(summary.last_logout_at), "h:mm a")}</span></span>
          )}
        </div>
      </div>

      {/* METRICS ROW */}
      <div className="grid grid-cols-3 gap-3">
        <div className="rounded-xl bg-sky-50 dark:bg-sky-950/30 border border-sky-100 p-4">
          <div className="flex items-center gap-2 mb-1">
            <Phone size={14} className="text-sky-600" />
            <span className="text-[11px] font-label text-sky-700">Calls Today</span>
          </div>
          <p className="font-display text-xl font-bold text-ink">{todayCallEvents.length}</p>
        </div>
        <div className="rounded-xl bg-violet-50 dark:bg-violet-950/30 border border-violet-100 p-4">
          <div className="flex items-center gap-2 mb-1">
            <Clock size={14} className="text-violet-600" />
            <span className="text-[11px] font-label text-violet-700">Duration</span>
          </div>
          <p className="font-display text-xl font-bold text-ink">{formatDuration(totalDurationSeconds)}</p>
        </div>
        <div className="rounded-xl bg-fuchsia-50 dark:bg-fuchsia-950/30 border border-fuchsia-100 p-4">
          <div className="flex items-center gap-2 mb-1">
            <TrendingUp size={14} className="text-fuchsia-600" />
            <span className="text-[11px] font-label text-fuchsia-700">Conversion</span>
          </div>
          <p className="font-display text-xl font-bold text-ink">{conversionRate}%</p>
        </div>
      </div>

      {/* ATTENDANCE */}
      <AttendanceMini callerId={callerId} />

      {/* CHARTS */}
      <div className="grid grid-cols-1 gap-4">
        <div className="card p-5">
          <div className="flex items-center gap-2 mb-4">
            <BarChart3 size={14} className="text-amber-600" />
            <h3 className="font-display font-semibold text-ink text-xs">Calls vs Conversions — Last 14 Days</h3>
          </div>
          <ResponsiveContainer width="100%" height={180}>
            <LineChart data={dailyTrend} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0ece4" />
              <XAxis dataKey="label" tick={{ fontSize: 9, fill: "#a8a29e" }} interval={1} />
              <YAxis tick={{ fontSize: 10, fill: "#a8a29e" }} allowDecimals={false} />
              <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e8e3db" }} />
              <Line type="monotone" dataKey="calls" stroke="#f59e0b" strokeWidth={2} dot={false} name="Calls" />
              <Line type="monotone" dataKey="converted" stroke="#10b981" strokeWidth={2} dot={false} name="Converted" />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="card p-5">
          <div className="flex items-center gap-2 mb-4">
            <Activity size={14} className="text-emerald-600" />
            <h3 className="font-display font-semibold text-ink text-xs">Outcome Breakdown</h3>
          </div>
          {outcomeTotal === 0 ? (
            <p className="text-center py-4 text-[11px] text-ink-muted font-body">No calls logged yet.</p>
          ) : (
            <div className="flex flex-col gap-2.5">
              {Object.entries(outcomeBreakdown).map(([key, count]) => {
                const pct = Math.round((count / outcomeTotal) * 100);
                return (
                  <div key={key}>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-[11px] font-label text-ink-muted">{OUTCOME_LABELS[key] ?? key}</span>
                      <span className="text-[11px] font-label text-ink font-semibold">{count} ({pct}%)</span>
                    </div>
                    <div className="w-full bg-surface-subtle h-2 rounded-full overflow-hidden">
                      <div
                        className="h-full rounded-full transition-all duration-500"
                        style={{ width: `${pct}%`, backgroundColor: OUTCOME_COLORS[key] ?? "#a78bfa" }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <div className="card p-5">
          <div className="flex items-center gap-2 mb-4">
            <Clock size={14} className="text-indigo-600" />
            <h3 className="font-display font-semibold text-ink text-xs">Calls by Hour of Day</h3>
          </div>
          {callLogs.length === 0 ? (
            <p className="text-center py-4 text-[11px] text-ink-muted font-body">No calls logged yet.</p>
          ) : (
            <ResponsiveContainer width="100%" height={160}>
              <BarChart data={hourlyDistribution} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0ece4" />
                <XAxis dataKey="hour" tick={{ fontSize: 9, fill: "#a8a29e" }} interval={1} />
                <YAxis tick={{ fontSize: 10, fill: "#a8a29e" }} allowDecimals={false} />
                <Tooltip
                  contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e8e3db" }}
                  labelFormatter={(h) => `${h}:00`}
                />
                <Bar dataKey="calls" fill="#6366f1" radius={[4, 4, 0, 0]} name="Calls" />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* TIME DISTRIBUTION */}
      {summary && (
        <div className="card p-5">
          <div className="flex items-center gap-2 mb-3">
            <Clock size={14} className="text-[#78716c]" />
            <h3 className="font-display font-semibold text-ink text-xs">Time Distribution</h3>
          </div>
          <div className="w-full h-3 rounded-full overflow-hidden flex bg-[#f0ece4]">
            {timeDist.active > 0 && <div className="h-full bg-emerald-500 transition-all duration-500" style={{ width: `${timeDist.active}%` }} />}
            {timeDist.breakPct > 0 && <div className="h-full bg-amber-400 transition-all duration-500" style={{ width: `${timeDist.breakPct}%` }} />}
            {timeDist.idle > 0 && <div className="h-full bg-[#d6cfc9] transition-all duration-500" style={{ width: `${timeDist.idle}%` }} />}
          </div>
          <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2 text-[10px] font-label text-ink-muted">
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-emerald-500 inline-block" /> Active: {timeDist.active}%
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-amber-400 inline-block" /> Break: {timeDist.breakPct}%
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-[#d6cfc9] inline-block" /> Idle: {timeDist.idle}%
            </span>
          </div>
        </div>
      )}

      {/* TIMELINE */}
      <div className="card p-5">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Calendar size={14} className="text-primary" />
            <h3 className="font-display font-semibold text-ink text-xs">Activity</h3>
          </div>
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)} className="input py-1 px-2 text-[11px] w-auto h-7" />
        </div>
        {eventsWithGaps.length === 0 ? (
          <div className="text-center py-6 text-[11px] text-ink-muted font-body">No activity logged.</div>
        ) : (
          <div className="relative border-l-2 border-border-subtle ml-3 space-y-5">
            {eventsWithGaps.map((ev) => {
              if (ev.type === "idle") {
                const gap = ev as GapEvent;
                return (
                  <div key={gap.id} className="relative pl-5 py-0.5">
                    <div className="absolute -left-[5px] top-2 w-2 h-2 rounded-full bg-[#e8e3db] border-2 border-white" />
                    <p className="text-[10px] font-body text-ink-muted bg-surface-subtle inline-block px-2 py-1 rounded-md border border-dashed border-border-subtle">
                      Idle — {formatDuration(gap.duration_seconds)}
                    </p>
                  </div>
                );
              }
              const tev = ev as TimelineEvent;
              let Icon = UserCircle;
              let iconBg = "bg-gray-100 text-gray-500";
              let title = "Event";
              let details = "";
              if (tev.type === "status") {
                if (tev.status === "active") { Icon = UserCircle; iconBg = "bg-emerald-100 text-emerald-600"; title = "Active"; }
                else if (tev.status === "break") { Icon = Coffee; iconBg = "bg-amber-100 text-amber-600"; title = "Break"; }
                else if (tev.status === "logged_out") { Icon = UserCircle; iconBg = "bg-rose-100 text-rose-600"; title = "Logged Out"; }
              } else if (tev.type === "call") {
                Icon = Phone; iconBg = "bg-blue-100 text-blue-600";
                title = `Call with ${tev.lead_name ?? "Unknown"}`;
                details = [tev.duration_seconds != null ? `${formatDuration(tev.duration_seconds)}` : null, tev.outcome ? `${tev.outcome}` : null].filter(Boolean).join(" · ");
              }
              return (
                <div key={tev.id} className="relative pl-6">
                  <div className={`absolute -left-3.5 top-0 p-1.5 rounded-full ring-2 ring-white ${iconBg}`}>
                    <Icon size={12} />
                  </div>
                  <div className="flex flex-col">
                    <div className="flex items-center gap-1.5">
                      <p className="font-label font-medium text-ink text-[11px]">{title}</p>
                      <span className="text-[9px] text-ink-muted font-body">{format(new Date(tev.started_at), "h:mm a")}</span>
                    </div>
                    {details && <p className="text-[10px] text-ink-muted font-body mt-0.5">{details}</p>}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
