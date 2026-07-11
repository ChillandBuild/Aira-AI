"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { ClipboardList, Loader2, TrendingUp } from "lucide-react";
import { Caller, TeamMember } from "@/lib/api";
import { useAuthRole } from "../contexts/AuthRoleContext";
import { useCallers } from "@/hooks/useApi";

import AssignmentLog from "../telecalling/components/assignment-log";
import PerformanceView from "../telecalling/components/performance-view";
import WinnerBanner from "./WinnerBanner";

interface TeamClientProps {
  fallbackTeam: { data: TeamMember[] } | null;
  fallbackCallers: Caller[] | null;
}

export function TeamClient({ fallbackTeam, fallbackCallers }: TeamClientProps) {
  const { role, permissions, loading: roleLoading } = useAuthRole();
  const router = useRouter();
  const searchParams = useSearchParams();
  const rawTab = searchParams.get("tab");
  const tab = (rawTab === "log" ? "log" : "performance") as "performance" | "log";
  const canViewTeam = role === "owner" || permissions.includes("team.view") || fallbackTeam !== null;

  const { data: callersData } = useCallers(
    canViewTeam,
    fallbackCallers ?? undefined,
  );

  const callers = callersData?.data ?? [];
  const adminCaller = callersData?.admin_caller ?? null;

  const setTab = (val: "performance" | "log") => {
    const params = new URLSearchParams(searchParams.toString());
    params.set("tab", val);
    router.replace(`/dashboard/team?${params.toString()}`, { scroll: false });
  };

  if (roleLoading && !fallbackTeam) {
    return (
      <div className="flex min-h-[400px] items-center justify-center">
        <Loader2 size={24} className="animate-spin text-primary" />
      </div>
    );
  }

  if (!canViewTeam) {
    return (
      <div className="py-20 text-center">
        <p className="font-body text-sm text-ink-muted">This section is only available for users with team access.</p>
      </div>
    );
  }

  return (
    <div className="min-w-0">
      <div className="mb-5 flex min-w-0 flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
        <div className="-mx-1 overflow-x-auto px-1 pb-1 sm:mx-0 sm:overflow-visible sm:p-0">
          <div className="flex w-max gap-1 rounded-2xl bg-[#e8e3db]/60 p-1 sm:w-fit">
            <button
              onClick={() => setTab("performance")}
              className={`flex shrink-0 items-center gap-1.5 rounded-xl px-3 py-2.5 font-label text-xs font-bold transition-all sm:px-5 ${
                tab === "performance" ? "bg-white text-primary shadow-sm" : "text-[#78716c] hover:text-[#292524]"
              }`}
            >
              <TrendingUp size={14} /> Team & Performance
            </button>
            <button
              onClick={() => setTab("log")}
              className={`flex shrink-0 items-center gap-1.5 rounded-xl px-3 py-2.5 font-label text-xs font-bold transition-all sm:px-5 ${
                tab === "log" ? "bg-white text-primary shadow-sm" : "text-[#78716c] hover:text-[#292524]"
              }`}
            >
              <ClipboardList size={14} /> Assignment Log
            </button>
          </div>
        </div>
        <div className="rounded-2xl border border-border-subtle bg-surface-subtle px-4 py-2 font-body text-xs font-semibold text-ink-muted">
          Add telecallers from Roles by assigning the Telecaller role.
        </div>
      </div>

      <WinnerBanner />

      {tab === "log" ? (
        <AssignmentLog callers={callers} />
      ) : (
        <PerformanceView callers={callers} adminCaller={adminCaller} />
      )}
    </div>
  );
}
