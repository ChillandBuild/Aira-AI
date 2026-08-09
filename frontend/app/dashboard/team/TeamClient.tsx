"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { AlertCircle, Loader2 } from "lucide-react";
import { Caller, TeamMember } from "@/lib/api";
import { cn } from "@/lib/utils";
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

  const [showTelecallerHint, setShowTelecallerHint] = useState(true);
  const [dismissingHint, setDismissingHint] = useState(false);

  useEffect(() => {
    const dismissTimer = setTimeout(() => setDismissingHint(true), 10000);
    return () => clearTimeout(dismissTimer);
  }, []);

  useEffect(() => {
    if (!dismissingHint) return;
    const removeTimer = setTimeout(() => setShowTelecallerHint(false), 300);
    return () => clearTimeout(removeTimer);
  }, [dismissingHint]);

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
      {showTelecallerHint && (
        <div className="mb-5 flex min-w-0 justify-end">
          <div
            className={cn(
              "flex items-center gap-2 rounded-2xl border border-amber-100 bg-amber-50 px-4 py-2 font-body text-xs font-semibold text-amber-800 transition-opacity duration-300",
              dismissingHint ? "opacity-0" : "opacity-100"
            )}
          >
            <AlertCircle size={14} className="shrink-0" />
            Add telecallers from Roles by assigning the Telecaller role.
          </div>
        </div>
      )}

      <WinnerBanner />

      {tab === "log" ? (
        <AssignmentLog callers={callers} />
      ) : (
        <PerformanceView callers={callers} adminCaller={adminCaller} />
      )}
    </div>
  );
}
