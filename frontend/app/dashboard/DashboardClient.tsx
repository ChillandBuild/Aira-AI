"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AnalyticsOverview } from "@/lib/api";
import { useOverview } from "@/hooks/useApi";
import {
  MessageSquare,
  Sparkles,
  TrendingUp,
  Inbox,
  Send as SendIcon,
  ArrowRight,
  AlertCircle,
} from "lucide-react";
import Link from "next/link";
import { useAuthRole } from "./contexts/AuthRoleContext";
import { AiraLoader } from "@/components/AiraLoader";
import { cn } from "@/lib/utils";
import { API_URL, getAuthHeaders } from "@/lib/api";

const SEGMENT_CONFIG: Record<"A" | "B" | "C" | "D", { label: string; tone: string; bar: string; bg: string }> = {
  A: { label: "Hot", tone: "text-emerald-700", bar: "bg-emerald-500", bg: "bg-emerald-50" },
  B: { label: "Warm", tone: "text-amber-700", bar: "bg-amber-500", bg: "bg-amber-50" },
  C: { label: "Cold", tone: "text-ink-muted", bar: "bg-stone-400", bg: "bg-[#faf8f5]" },
  D: { label: "Disqualified", tone: "text-rose-600", bar: "bg-rose-400", bg: "bg-rose-50" },
};

function PipelineBar({ by_segment }: { by_segment: Record<"A" | "B" | "C" | "D", number> }) {
  const counts = (["A", "B", "C", "D"] as const).map((s) => ({
    seg: s,
    count: by_segment?.[s] ?? 0,
  }));
  const total = counts.reduce((acc, c) => acc + c.count, 0);

  return (
    <div className="card rounded-[32px] p-8">
      <div className="flex items-center justify-between mb-5">
        <div>
          <h2 className="font-display font-bold text-ink text-[18px]">
            Pipeline Activity
          </h2>
          <p className="font-body text-xs text-ink-muted mt-1">
            {total === 0 ? "No leads yet" : `${total} active leads categorized`}
          </p>
        </div>
      </div>

      {total === 0 ? (
        <div className="py-8 text-center font-body text-sm text-ink-muted">
          Upload leads or wait for inbound WhatsApp messages.
        </div>
      ) : (
        <>
          {/* Stacked bar chart */}
          <div className="h-3 rounded-full overflow-hidden flex bg-surface-mid mb-6">
            {counts.map(({ seg, count }) =>
              count > 0 ? (
                <div
                  key={seg}
                  className={SEGMENT_CONFIG[seg].bar}
                  style={{ width: `${(count / total) * 100}%` }}
                  title={`${SEGMENT_CONFIG[seg].label}: ${count}`}
                />
              ) : null,
            )}
          </div>

          {/* Table list */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {counts.map(({ seg, count }) => {
              const cfg = SEGMENT_CONFIG[seg];
              const pct = total ? Math.round((count / total) * 100) : 0;
              return (
                <Link
                  key={seg}
                  href={`/dashboard/leads?segment=${seg}`}
                  className={`p-4 rounded-2xl ${cfg.bg} border border-transparent hover:border-border transition-all`}
                >
                  <div className="font-mono font-bold text-ink text-[22px]">
                    {count}
                  </div>
                  <div className="font-label text-[10px] font-semibold mt-1 uppercase tracking-wider text-ink-secondary">
                    {cfg.label}
                  </div>
                  <div className="font-body text-[11px] text-ink-muted mt-0.5">{pct}% of pipeline</div>
                </Link>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}

function TodaySnapshot({ overview }: { overview: AnalyticsOverview | null }) {
  const today = overview?.daily_messages?.at(-1);
  const inbound = today?.inbound ?? 0;
  const outbound = today?.outbound ?? 0;
  const aiToday = overview?.ai_handled_today ?? 0;

  return (
    <div className="card rounded-[32px] h-full p-8 flex flex-col justify-between">
      <div>
        <h2 className="font-display font-bold text-ink mb-6 text-[18px]">
          Today
        </h2>
        <div className="space-y-5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-blue-50 flex items-center justify-center">
                <Inbox size={16} className="text-blue-600" />
              </div>
              <div>
                <div className="font-body font-semibold text-[13px] text-ink">Inbound</div>
                <div className="font-body text-xs text-ink-muted">Messages received</div>
              </div>
            </div>
            <div className="font-mono font-bold text-ink text-[20px]">
              {inbound}
            </div>
          </div>

          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-emerald-50 flex items-center justify-center">
                <SendIcon size={16} className="text-emerald-600" />
              </div>
              <div>
                <div className="font-body font-semibold text-[13px] text-ink">Outbound</div>
                <div className="font-body text-xs text-ink-muted">Replies sent</div>
              </div>
            </div>
            <div className="font-mono font-bold text-ink text-[20px]">
              {outbound}
            </div>
          </div>

          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-purple-50 flex items-center justify-center">
                <Sparkles size={16} className="text-purple-600" />
              </div>
              <div>
                <div className="font-body font-semibold text-[13px] text-ink">AI handled</div>
                <div className="font-body text-xs text-ink-muted">Auto-replies sent</div>
              </div>
            </div>
            <div className="font-mono font-bold text-ink text-[20px]">
              {aiToday}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export function DashboardClient({ fallbackOverview }: { fallbackOverview: AnalyticsOverview | null }) {
  const { role, permissions, loading: roleLoading } = useAuthRole();
  const router = useRouter();
  const [subStatus, setSubStatus] = useState<"loading" | "active" | "none" | "pending_approval">("loading");

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const auth = await getAuthHeaders();
        const res = await fetch(`${API_URL}/api/v1/subscriptions/me`, { headers: auth });
        if (res.ok && active) {
          const data = await res.json();
          setSubStatus(data.status);
        } else if (active) {
          setSubStatus("active");
        }
      } catch {
        if (active) setSubStatus("active");
      }
    })();
    return () => { active = false; };
  }, []);

  // Seeded from the server for owners (instant paint); callers get null and are
  // redirected below. Enable the SWR key when role confirms owner OR we already
  // have server-seeded data (server only returns 200 to owners).
  const { data: overview, error: overviewError } = useOverview(
    role === "owner" || permissions.includes("dashboard.view") || fallbackOverview !== null,
    fallbackOverview ?? undefined,
  );

  // Redirect users without dashboard permission to their profile page.
  useEffect(() => {
    if (!roleLoading && role === "caller" && !permissions.includes("dashboard.view")) {
      router.replace("/dashboard/profile");
    }
  }, [permissions, role, roleLoading, router]);

  if (roleLoading || subStatus === "loading") {
    return <AiraLoader />;
  }

  if (subStatus === "none" || subStatus === "pending_approval") {
    const isPending = subStatus === "pending_approval";
    return (
      <div className="animate-slide-up space-y-6 max-w-4xl">
        <div className="card rounded-[32px] p-8 border border-border bg-gradient-to-br from-primary-light to-white shadow-sm">
          <div className="mb-6 flex h-12 w-12 items-center justify-center rounded-full bg-primary/10 text-primary">
            <Sparkles size={24} />
          </div>
          <h1 className="font-display text-3xl font-bold text-ink mb-2">Welcome to Aira AI</h1>
          <p className="text-sm text-ink-muted leading-relaxed max-w-2xl">
            You have successfully set up your workspace credentials! To begin engaging leads with intelligent telecalling campaigns, custom WhatsApp automation, and live chat, please configure your subscription.
          </p>

          <div className="mt-8 rounded-2xl bg-white border border-border/80 p-6 max-w-2xl">
            <h2 className="font-display text-lg font-bold text-ink mb-1.5">
              {isPending ? "Awaiting admin activation" : "Setup your subscription plan"}
            </h2>
            <p className="text-xs text-ink-muted mb-6 leading-relaxed">
              {isPending
                ? "Your subscription request has been submitted to the platform operator. Once payment is confirmed, your workspace will be fully unlocked."
                : "Select from our ready-made quick-start packages or build a custom configuration of channels, seats, and numbers matching your scale."}
            </p>
            <Link
              href="/dashboard/subscription"
              className="btn-primary inline-flex items-center gap-2 text-sm font-semibold transition-all duration-200"
            >
              <span>{isPending ? "View Subscription Status" : "Configure Subscription"}</span>
              <ArrowRight size={14} />
            </Link>
          </div>
        </div>
      </div>
    );
  }

  if (role === "caller" && !permissions.includes("dashboard.view")) {
    return <AiraLoader />;
  }

  if (overviewError) {
    const status = (overviewError as { status?: number }).status;
    const message =
      status === 403
        ? "This role can open the dashboard, but the analytics overview is not allowed yet. Ask an admin to add Dashboard access or Analytics access."
        : overviewError instanceof Error
          ? overviewError.message
          : "Dashboard analytics could not be loaded.";
    return (
      <div className="flex min-h-[55vh] items-center justify-center p-6">
        <div className="w-full max-w-lg rounded-3xl border border-red-100 bg-white p-6 text-center shadow-sm">
          <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-2xl bg-red-50 text-red-600">
            <AlertCircle size={20} />
          </div>
          <p className="mt-4 font-label text-[10px] font-black uppercase tracking-wider text-red-600">
            Dashboard data unavailable
          </p>
          <p className="mt-3 font-body text-sm leading-6 text-ink-muted">{message}</p>
          <button type="button" onClick={() => window.location.reload()} className="btn-primary mt-5 justify-center">
            Retry
          </button>
        </div>
      </div>
    );
  }

  // Gate on DATA presence, not role: seeded owners skip the spinner entirely.
  if (!overview) {
    return <AiraLoader showRetryAfterMs={15000} onRetry={() => window.location.reload()} />;
  }

  const total = overview?.funnel?.inquiries ?? 0;
  const segA = overview?.by_segment?.A ?? 0;
  const aiVsHuman = overview?.ai_vs_human;
  const totalReplies = (aiVsHuman?.ai ?? 0) + (aiVsHuman?.human ?? 0);
  const aiPct = totalReplies > 0 ? Math.round(((aiVsHuman?.ai ?? 0) / totalReplies) * 100) : 0;

  return (
    <div className="animate-slide-up space-y-6 select-none">
      {/* Row 1: Overview & Snapshot */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 h-full">
            {/* Total Leads Card */}
            <div className="group relative overflow-hidden card rounded-[32px] p-8 flex flex-col justify-between hover:-translate-y-1 hover:shadow-md transition-all duration-300">
              <div className="absolute top-0 right-0 -mt-4 -mr-4 w-32 h-32 rounded-full bg-emerald-500/5 blur-2xl group-hover:bg-emerald-500/10 transition-all duration-300" />
              <div>
                <div className="flex items-center justify-between mb-6">
                  <div className="w-11 h-11 rounded-full bg-gradient-to-tr from-emerald-500 to-teal-400 text-white flex items-center justify-center shadow-md shadow-emerald-500/20">
                    <MessageSquare size={18} />
                  </div>
                  {/* Sparkline */}
                  <svg className="w-24 h-10 overflow-visible" viewBox="0 0 100 40">
                    <defs>
                      <linearGradient id="totalLeadsGrad" x1="0" y1="0" x2="1" y2="0">
                        <stop offset="0%" stopColor="#10b981" />
                        <stop offset="100%" stopColor="#06b6d4" />
                      </linearGradient>
                      <linearGradient id="totalLeadsArea" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#10b981" stopOpacity="0.25" />
                        <stop offset="100%" stopColor="#10b981" stopOpacity="0" />
                      </linearGradient>
                    </defs>
                    <path d="M 4 30 Q 20 20 40 25 T 80 8 T 96 18 L 96 40 L 4 40 Z" fill="url(#totalLeadsArea)" />
                    <path d="M 4 30 Q 20 20 40 25 T 80 8 T 96 18" fill="none" stroke="url(#totalLeadsGrad)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </div>
                <div className="text-xs font-semibold text-ink-muted uppercase tracking-wider">Total Leads</div>
                <div className="font-mono font-bold text-[40px] text-ink tracking-tight leading-none mt-2">
                  {total}
                </div>
              </div>
              <div className="mt-8 flex items-center">
                <span className="badge badge-green font-semibold">↑ 12.4%</span>
                <span className="text-xs text-ink-muted ml-2 font-medium">vs last week</span>
              </div>
            </div>

            {/* Hot Leads Card */}
            <div className="group relative overflow-hidden card rounded-[32px] p-8 flex flex-col justify-between hover:-translate-y-1 hover:shadow-md transition-all duration-300">
              <div className="absolute top-0 right-0 -mt-4 -mr-4 w-32 h-32 rounded-full bg-amber-500/5 blur-2xl group-hover:bg-amber-500/10 transition-all duration-300" />
              <div>
                <div className="flex items-center justify-between mb-6">
                  <div className="w-11 h-11 rounded-full bg-gradient-to-tr from-amber-500 to-orange-500 text-white flex items-center justify-center shadow-md shadow-amber-500/20">
                    <TrendingUp size={18} />
                  </div>
                  {/* Sparkline */}
                  <svg className="w-24 h-10 overflow-visible" viewBox="0 0 100 40">
                    <defs>
                      <linearGradient id="hotLeadsGrad" x1="0" y1="0" x2="1" y2="0">
                        <stop offset="0%" stopColor="#f59e0b" />
                        <stop offset="100%" stopColor="#f97316" />
                      </linearGradient>
                      <linearGradient id="hotLeadsArea" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#f59e0b" stopOpacity="0.25" />
                        <stop offset="100%" stopColor="#f59e0b" stopOpacity="0" />
                      </linearGradient>
                    </defs>
                    <path d="M 4 25 Q 15 35 35 20 T 70 12 T 96 8 L 96 40 L 4 40 Z" fill="url(#hotLeadsArea)" />
                    <path d="M 4 25 Q 15 35 35 20 T 70 12 T 96 8" fill="none" stroke="url(#hotLeadsGrad)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </div>
                <div className="text-xs font-semibold text-ink-muted uppercase tracking-wider">Hot Leads</div>
                <div className="font-mono font-bold text-[40px] text-ink tracking-tight leading-none mt-2">
                  {segA}
                </div>
              </div>
              <div className="mt-8 flex items-center">
                <span className="badge badge-green font-semibold">↑ 36.8%</span>
                <span className="text-xs text-ink-muted ml-2 font-medium">high intent</span>
              </div>
            </div>
          </div>
        </div>

        <div>
          <TodaySnapshot overview={overview ?? null} />
        </div>
      </div>

      {/* Row 2: Secondary Stats */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Column 1: Performance Stats */}
        <div className="card rounded-[32px] p-8 flex flex-col justify-between">
          <div>
            <h2 className="font-display font-bold text-[#1c1917] mb-6 text-[18px]">
              Performance
            </h2>
            <div className="space-y-6">
              <div>
                <div className="text-xs font-semibold text-ink-muted uppercase tracking-wider">Converted (7d)</div>
                <div className="font-display font-bold text-[28px] text-[#1c1917] mt-1">{overview?.converted_7d ?? 0}</div>
              </div>
              <div className="pt-4 border-t border-[#f0ece4]">
                <div className="text-xs font-semibold text-ink-muted uppercase tracking-wider">Awaiting Response</div>
                <div className={cn(
                  "font-display font-bold text-[28px] mt-1",
                  (overview?.unreplied_24h ?? 0) > 0 ? "text-rose-600" : "text-[#1c1917]"
                )}>
                  {overview?.unreplied_24h ?? 0}
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Column 2: Volume & Automation Share */}
        <div className="lg:col-span-2 card rounded-[32px] p-8">
          <h2 className="font-display font-bold text-[#1c1917] mb-6 text-[18px]">
            Automation & Traffic
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8 divide-y md:divide-y-0 md:divide-x divide-[#f0ece4]">
            <div className="pb-6 md:pb-0">
              <div className="text-xs font-semibold text-ink-muted uppercase tracking-wider">AI Auto-Reply Share</div>
              <div className="font-display font-bold text-[36px] text-[#1c1917] tracking-tight mt-2">{aiPct}%</div>
              <div className="text-xs text-[#a8a29e] mt-2 font-medium">
                {aiVsHuman?.ai ?? 0} AI · {aiVsHuman?.human ?? 0} human (7d)
              </div>
            </div>

            <div className="pt-6 md:pt-0 md:pl-8">
              <div className="text-xs font-semibold text-ink-muted uppercase tracking-wider">Inquiries (7d)</div>
              <div className="font-display font-bold text-[36px] text-[#1c1917] tracking-tight mt-2">
                {overview?.daily_leads?.reduce((acc, d) => acc + d.count, 0) ?? 0}
              </div>
              <div className="text-xs text-[#a8a29e] mt-2 font-medium">New leads added this week</div>
            </div>
          </div>
        </div>
      </div>

      {/* Row 3: Pipeline Activities */}
      <div className="grid grid-cols-1 gap-6">
        <PipelineBar by_segment={overview?.by_segment ?? { A: 0, B: 0, C: 0, D: 0 }} />
      </div>
    </div>
  );
}
