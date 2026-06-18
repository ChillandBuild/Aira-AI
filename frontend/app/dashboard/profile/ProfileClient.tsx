"use client";
import { useState } from "react";
import Link from "next/link";
import {
  Phone,
  TrendingUp,
  Clock,
  Target,
  Sparkles,
  RefreshCw,
  CheckCircle2,
  XCircle,
  PhoneForwarded,
  Minus,
  Upload,
  BarChart2,
  Settings,
  Users,
  Crown,
} from "lucide-react";
import { api } from "@/lib/api";
import type { CallerStats, CallLog } from "@/lib/api";
import { toast } from "sonner";
import { useMyStats, useMyPerformance, useCallerLogs } from "@/hooks/useApi";
import { useAuthRole } from "../contexts/AuthRoleContext";
import AttendanceMini from "../team/AttendanceMini";

export interface ProfileClientProps {
  fallbackStats: CallerStats | null;
  fallbackPerformance: { target: number; achieved: number } | null;
  fallbackLogs: CallLog[] | null;
  userEmail?: string | null;
  userName?: string | null;
  userCreatedAt?: string | null;
}

export function ProfileClient({
  fallbackStats,
  fallbackPerformance,
  fallbackLogs,
  userEmail,
  userName,
  userCreatedAt,
}: ProfileClientProps) {
  const { role } = useAuthRole();
  const isAdmin = role === "owner";

  const { data: stats, mutate: mutateStats } = useMyStats(!isAdmin, fallbackStats ?? undefined);
  const { data: performanceData } = useMyPerformance(!isAdmin, fallbackPerformance ?? undefined);
  const { data: logsData } = useCallerLogs(stats?.caller_id ?? null, !isAdmin, fallbackLogs ?? undefined);

  const [tip, setTip] = useState<string | null>(null);
  const [tipLoading, setTipLoading] = useState(false);
  const [togglingStatus, setTogglingStatus] = useState(false);

  const performance = performanceData ?? { target: 50, achieved: 0 };
  const logs = logsData ?? [];

  const toggleMyStatus = async () => {
    if (!stats) return;
    const currentStatus = (stats.status as "active" | "break") || "active";
    const next = currentStatus === "active" ? "break" : "active";
    setTogglingStatus(true);
    try {
      await api.callers.setMyStatus(next);
      mutateStats({ ...stats, status: next });
      toast.success(next === "active" ? "You are now active" : "Break mode enabled");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to update status");
    } finally {
      setTogglingStatus(false);
    }
  };

  async function loadTip() {
    if (!stats?.caller_id) return;
    setTipLoading(true);
    try {
      const res = await api.callers.coaching(stats.caller_id);
      setTip(res.tip);
    } catch (err) {
      setTip(err instanceof Error ? err.message : "Could not fetch tip");
    } finally {
      setTipLoading(false);
    }
  }

  function formatDuration(seconds: number | null): string {
    if (!seconds) return "—";
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}m ${s}s`;
  }

  function timeAgo(dateStr: string): string {
    const diff = Date.now() - new Date(dateStr).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    return `${Math.floor(hrs / 24)}d ago`;
  }

  const outcomeIcon = (outcome: string | null) => {
    switch (outcome) {
      case "converted":
        return <CheckCircle2 size={14} className="text-green-500" />;
      case "not_interested":
        return <XCircle size={14} className="text-red-400" />;
      case "callback":
        return <PhoneForwarded size={14} className="text-amber-500" />;
      case "no_answer":
        return <Minus size={14} className="text-gray-400" />;
      default:
        return <Minus size={14} className="text-gray-300" />;
    }
  };

  const outcomeLabel = (outcome: string | null) => {
    switch (outcome) {
      case "converted":
        return "Converted";
      case "not_interested":
        return "Not interested";
      case "callback":
        return "Callback";
      case "no_answer":
        return "No answer";
      default:
        return "—";
    }
  };

  if (isAdmin) {
    const adminName = userName || userEmail?.split("@")[0] || "Admin";
    const initials = adminName.split(" ").map((n: string) => n[0]).join("").toUpperCase().slice(0, 2);
    const memberSince = userCreatedAt ? new Date(userCreatedAt).toLocaleDateString("en-IN", { month: "long", year: "numeric" }) : null;

    const now = new Date(new Date().toLocaleString("en-US", { timeZone: "Asia/Kolkata" }));
    const hour = now.getHours();
    const greeting = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";

    const quickLinks = [
      { href: "/dashboard", icon: BarChart2, label: "Dashboard", desc: "Team overview & metrics", color: "from-indigo-500 to-violet-500" },
      { href: "/dashboard/telecalling/upload", icon: Upload, label: "Upload Contacts", desc: "Import CSV & manage scripts", color: "from-emerald-500 to-teal-500" },
      { href: "/dashboard/telecalling", icon: Phone, label: "Telecalling", desc: "Dialer & lead queue", color: "from-amber-500 to-orange-500" },
      { href: "/dashboard/team", icon: Users, label: "Team", desc: "Manage telecallers", color: "from-blue-500 to-cyan-500" },
      { href: "/dashboard/settings", icon: Settings, label: "Settings", desc: "Config & channels", color: "from-slate-500 to-zinc-500" },
      { href: "/dashboard/analytics", icon: TrendingUp, label: "Analytics", desc: "Performance reports", color: "from-rose-500 to-pink-500" },
    ];

    return (
      <div>
        <div className="mb-8">
          <h1 className="font-display text-3xl font-bold text-tertiary">My Profile</h1>
          <p className="font-body text-on-surface-muted mt-1">{greeting}, {adminName.split(" ")[0]}</p>
        </div>

        {/* Admin Identity Card */}
        <div className="bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 rounded-[2rem] p-8 shadow-xl mb-8 relative overflow-hidden">
          <div className="absolute top-0 right-0 w-64 h-64 bg-gradient-to-bl from-indigo-500/10 to-transparent rounded-full -translate-y-1/2 translate-x-1/3" />
          <div className="absolute bottom-0 left-0 w-48 h-48 bg-gradient-to-tr from-amber-500/10 to-transparent rounded-full translate-y-1/2 -translate-x-1/4" />

          <div className="relative flex items-center gap-6">
            <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center shadow-lg shadow-indigo-500/25">
              <span className="font-display text-3xl font-bold text-white">{initials}</span>
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-3 flex-wrap">
                <h2 className="font-display text-2xl font-bold text-white">{adminName}</h2>
                <span className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-amber-500/15 border border-amber-500/30">
                  <Crown size={12} className="text-amber-400" />
                  <span className="font-label text-xs font-bold text-amber-300 uppercase tracking-wider">Admin</span>
                </span>
              </div>
              {userEmail && (
                <p className="font-body text-sm text-slate-400 mt-1">{userEmail}</p>
              )}
              <div className="flex items-center gap-4 mt-3">
                {memberSince && (
                  <span className="font-label text-xs text-slate-500">Member since {memberSince}</span>
                )}
                <span className="flex items-center gap-1.5 font-label text-xs text-emerald-400">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                  All systems online
                </span>
              </div>
            </div>
          </div>

          {/* Signature quote */}
          <div className="relative mt-6 pt-6 border-t border-slate-700/50">
            <p className="font-body text-sm text-slate-400 italic leading-relaxed">
              &quot;The best leaders don&apos;t create followers — they create more leaders.&quot;
            </p>
            <p className="font-label text-[10px] text-slate-600 mt-1 uppercase tracking-widest">Your role: Empower your team</p>
          </div>
        </div>

        {/* Quick Navigation */}
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
          {quickLinks.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="group bg-surface rounded-2xl p-5 shadow-card ring-1 ring-[#c4c7c7]/15 hover:shadow-lg hover:ring-primary/20 transition-all duration-200"
            >
              <div className={`w-10 h-10 rounded-xl bg-gradient-to-br ${link.color} flex items-center justify-center mb-3 shadow-sm group-hover:scale-110 transition-transform`}>
                <link.icon size={18} className="text-white" />
              </div>
              <h3 className="font-display text-sm font-bold text-on-surface">{link.label}</h3>
              <p className="font-body text-xs text-on-surface-muted mt-0.5">{link.desc}</p>
            </Link>
          ))}
        </div>
      </div>
    );
  }

  if (!stats) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <RefreshCw size={24} className="animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div>
      {/* Header */}
      <div className="mb-8">
        <h1 className="font-display text-3xl font-bold text-tertiary">
          My Profile
        </h1>
        <p className="font-body text-on-surface-muted mt-1">
          Your performance at a glance
        </p>
      </div>

      {/* Profile Card + Stats */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
        {/* Profile Card */}
        <div className="bg-surface rounded-card p-6 shadow-card ring-1 ring-[#c4c7c7]/15">
          <div className="flex items-center gap-4 mb-4">
            <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-primary/20 to-secondary/20 flex items-center justify-center">
              <span className="font-display text-2xl font-bold text-primary">
                {stats.name
                  ?.split(" ")
                  .map((n: string) => n[0])
                  .join("")
                  .toUpperCase() || "?"}
              </span>
            </div>
            <div>
              <h2 className="font-display text-xl font-bold text-on-surface">
                {stats.name}
              </h2>
              <p className="font-label text-sm text-on-surface-muted">
                {stats.phone || "—"}
              </p>
              <div className="flex items-center gap-2 mt-1.5">
                <button
                  onClick={toggleMyStatus}
                  disabled={togglingStatus}
                  className={`px-3 py-1 rounded-full font-label text-xs font-semibold transition-all flex items-center gap-1.5 shadow-sm border ${
                    stats.status === "active"
                      ? "bg-emerald-50 border-emerald-200 text-emerald-700 hover:bg-emerald-100"
                      : "bg-amber-50 border-amber-200 text-amber-700 hover:bg-amber-100"
                  } disabled:opacity-60`}
                  title="Click to toggle status"
                >
                  <span className={`w-1.5 h-1.5 rounded-full ${stats.status === "active" ? "bg-emerald-500 animate-pulse" : "bg-amber-500"}`} />
                  {stats.status === "active" ? "🟢 Active" : "🟡 On Break"}
                </button>
              </div>
            </div>
          </div>

          {/* Overall Score */}
          <div className="mt-4 pt-4 border-t border-surface-mid">
            <p className="font-label text-xs text-on-surface-muted uppercase tracking-wider mb-1">
              Performance Score
            </p>
            <div className="flex items-baseline gap-2">
              <span className="font-display text-4xl font-bold text-primary">
                {Number(stats.overall_score).toFixed(1)}
              </span>
              <span className="font-label text-sm text-on-surface-muted">
                / 10
              </span>
            </div>
          </div>
        </div>

        {/* Stats Grid */}
        <div className="lg:col-span-2 grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-surface rounded-card p-5 shadow-card ring-1 ring-[#c4c7c7]/15 flex flex-col">
            <div className="flex items-center gap-2 mb-2">
              <div className="p-2 rounded-xl bg-primary/10">
                <Phone size={16} className="text-primary" />
              </div>
            </div>
            <span className="font-display text-3xl font-bold text-on-surface">
              {stats.calls_today}
            </span>
            <span className="font-label text-xs text-on-surface-muted mt-1">
              Calls Today
            </span>
          </div>

          <div className="bg-surface rounded-card p-5 shadow-card ring-1 ring-[#c4c7c7]/15 flex flex-col">
            <div className="flex items-center gap-2 mb-2">
              <div className="p-2 rounded-xl bg-green-100">
                <Target size={16} className="text-green-600" />
              </div>
            </div>
            <span className="font-display text-3xl font-bold text-on-surface">
              {(stats.conversion_rate_week * 100).toFixed(0)}%
            </span>
            <span className="font-label text-xs text-on-surface-muted mt-1">
              Conv. Rate (Week)
            </span>
          </div>

          <div className="bg-surface rounded-card p-5 shadow-card ring-1 ring-[#c4c7c7]/15 flex flex-col">
            <div className="flex items-center gap-2 mb-2">
              <div className="p-2 rounded-xl bg-blue-100">
                <Clock size={16} className="text-blue-600" />
              </div>
            </div>
            <span className="font-display text-3xl font-bold text-on-surface">
              {stats.avg_duration_seconds
                ? formatDuration(stats.avg_duration_seconds)
                : "—"}
            </span>
            <span className="font-label text-xs text-on-surface-muted mt-1">
              Avg Duration
            </span>
          </div>

          <div className="bg-surface rounded-card p-5 shadow-card ring-1 ring-[#c4c7c7]/15 flex flex-col">
            <div className="flex items-center gap-2 mb-2">
              <div className="p-2 rounded-xl bg-red-100">
                <TrendingUp size={16} className="text-red-500" />
              </div>
            </div>
            <span className="font-display text-3xl font-bold text-on-surface">
              {stats.pending_hot_leads}
            </span>
            <span className="font-label text-xs text-on-surface-muted mt-1">
              Pending Hot Leads
            </span>
          </div>

          <div className="bg-surface rounded-card p-5 shadow-card ring-1 ring-[#c4c7c7]/15 flex flex-col col-span-2">
            <div className="flex items-center gap-2 mb-2">
              <div className="p-2 rounded-xl bg-secondary/10">
                <Phone size={16} className="text-secondary" />
              </div>
            </div>
            <span className="font-display text-3xl font-bold text-on-surface">
              {stats.calls_this_week}
            </span>
            <span className="font-label text-xs text-on-surface-muted mt-1">
              Calls This Week
            </span>
          </div>

          <div className="bg-surface rounded-card p-5 shadow-card ring-1 ring-[#c4c7c7]/15 flex col-span-2 justify-between items-center">
            <div className="flex-1 flex flex-col justify-between h-full min-h-[90px]">
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <div className="p-1.5 rounded-lg bg-indigo-50">
                    <Target size={14} className="text-indigo-600" />
                  </div>
                  <span className="font-label text-xs text-on-surface-muted font-bold tracking-wider uppercase">
                    Daily Target
                  </span>
                </div>
                <p className="font-display text-lg font-extrabold text-on-surface mt-1">
                  {performance.achieved} / {performance.target} Calls
                </p>
              </div>
              
              <div className="flex items-center gap-2 mt-2 pt-2 border-t border-surface-low">
                {performance.achieved >= performance.target ? (
                  <span className="text-[10px] text-green-600 font-bold bg-emerald-50 border border-emerald-100 px-2.5 py-0.5 rounded-full animate-pulse">
                    🎉 Target Met!
                  </span>
                ) : (
                  <span className="text-[10px] text-amber-600 font-semibold bg-amber-50 border border-amber-100 px-2.5 py-0.5 rounded-full">
                    {performance.target - performance.achieved} calls to go 🎯
                  </span>
                )}
              </div>
            </div>

            {/* Circular SVG Progress Ring */}
            <div className="relative flex items-center justify-center shrink-0 ml-4">
              <svg height="96" width="96" className="rotate-[-90deg]">
                <circle
                  stroke="rgba(226, 232, 240, 0.5)"
                  fill="transparent"
                  strokeWidth="8"
                  r="38"
                  cx="48"
                  cy="48"
                />
                <circle
                  stroke="url(#targetRingGradient)"
                  fill="transparent"
                  strokeWidth="8"
                  strokeDasharray="238.76"
                  strokeDashoffset={238.76 - (Math.min(100, performance.target > 0 ? (performance.achieved / performance.target) * 100 : 0) / 100) * 238.76}
                  strokeLinecap="round"
                  r="38"
                  cx="48"
                  cy="48"
                  className="transition-all duration-500"
                />
                <defs>
                  <linearGradient id="targetRingGradient" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stopColor="#6366f1" />
                    <stop offset="100%" stopColor="#a855f7" />
                  </linearGradient>
                </defs>
              </svg>
              <div className="absolute flex flex-col items-center justify-center">
                <span className="font-display text-sm font-black text-on-surface">
                  {performance.target > 0 ? Math.round((performance.achieved / performance.target) * 100) : 0}%
                </span>
                <span className="font-label text-[8px] text-on-surface-muted uppercase tracking-wider font-bold">
                  done
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Attendance History */}
      <div className="mb-8">
        <AttendanceMini callerId={stats.caller_id} readOnly={true} />
      </div>

      {/* AI Coaching */}
      <div className="mb-8 bg-surface rounded-card p-6 shadow-card ring-1 ring-[#c4c7c7]/15">
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-display text-base font-bold text-tertiary flex items-center gap-2">
            <Sparkles size={16} className="text-secondary" /> AI Coaching
          </h2>
          <button
            onClick={loadTip}
            disabled={tipLoading}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-surface-low rounded-lg font-label text-xs font-semibold hover:bg-surface-mid transition-colors disabled:opacity-40"
          >
            <RefreshCw
              size={12}
              className={tipLoading ? "animate-spin" : ""}
            />
            {tip ? "New Tip" : "Get Tip"}
          </button>
        </div>
        <div className="p-4 bg-surface-low rounded-xl min-h-[3rem]">
          <p className="font-body text-sm text-on-surface leading-relaxed">
            {tipLoading
              ? "Generating your personalized coaching tip…"
              : tip
                ? `💡 ${tip}`
                : "Click 'Get Tip' to receive a personalized coaching suggestion based on your recent call data."}
          </p>
        </div>
      </div>

      {/* Call History */}
      <div className="bg-surface rounded-card p-6 shadow-card ring-1 ring-[#c4c7c7]/15">
        <h2 className="font-display text-base font-bold text-tertiary mb-4 flex items-center gap-2">
          <Phone size={16} className="text-secondary" /> Recent Call History
        </h2>

        {logs.length === 0 ? (
          <p className="font-body text-sm text-on-surface-muted py-8 text-center">
            No calls yet. Start calling your assigned leads!
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-surface-mid">
                  <th className="pb-3 font-label text-xs text-on-surface-muted uppercase tracking-wider">
                    Lead
                  </th>
                  <th className="pb-3 font-label text-xs text-on-surface-muted uppercase tracking-wider">
                    Phone
                  </th>
                  <th className="pb-3 font-label text-xs text-on-surface-muted uppercase tracking-wider">
                    Duration
                  </th>
                  <th className="pb-3 font-label text-xs text-on-surface-muted uppercase tracking-wider">
                    Outcome
                  </th>
                  <th className="pb-3 font-label text-xs text-on-surface-muted uppercase tracking-wider text-right">
                    When
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-low">
                {logs.map((log: CallLog) => (
                  <tr key={log.id} className="hover:bg-surface-low transition-colors">
                    <td className="py-3 pr-4">
                      <span className="font-body text-sm font-semibold text-on-surface">
                        {log.leads?.name || "Unknown"}
                      </span>
                    </td>
                    <td className="py-3 pr-4">
                      <span className="font-label text-xs text-on-surface-muted">
                        {log.leads?.phone || "—"}
                      </span>
                    </td>
                    <td className="py-3 pr-4">
                      <span className="font-label text-xs text-on-surface">
                        {formatDuration(log.duration_seconds)}
                      </span>
                    </td>
                    <td className="py-3 pr-4">
                      <span className="flex items-center gap-1.5 font-label text-xs">
                        {outcomeIcon(log.outcome)}
                        {outcomeLabel(log.outcome)}
                      </span>
                    </td>
                    <td className="py-3 text-right">
                      <span className="font-label text-xs text-on-surface-muted">
                        {timeAgo(log.created_at)}
                      </span>
                    </td>
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
