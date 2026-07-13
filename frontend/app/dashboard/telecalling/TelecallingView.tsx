"use client";
import { RefreshCw } from "lucide-react";
import { useAuthRole } from "../contexts/AuthRoleContext";
import { AdminDashboardData } from "@/hooks/useApi";
import CallerView from "./CallerView";
import AdminView from "./AdminView";

interface TelecallingViewProps {
  initialRole: "owner" | "caller" | null;
  initialCallerId: string | null;
  initialPermissions: string[];
  fallbackAdminData: AdminDashboardData | null;
}

export function TelecallingView({ initialRole, initialCallerId, initialPermissions, fallbackAdminData }: TelecallingViewProps) {
  const ctx = useAuthRole();
  // Prefer the server-seeded role/callerId until the client context resolves.
  // Both read team/me, so they agree — this just skips the first-paint spinner
  // for BOTH admins (AdminView) and telecallers (CallerView).
  const role = ctx.loading ? initialRole : ctx.role;
  const callerId = ctx.loading ? initialCallerId : ctx.callerId;
  const permissions = ctx.loading ? initialPermissions : ctx.permissions;
  const canDial = role === "owner" || permissions.includes("telecalling.dialer");
  const canViewTelecalling =
    role === "owner" ||
    permissions.includes("telecalling.dialer.view") ||
    permissions.includes("telecalling.dialer") ||
    permissions.includes("leads.view") ||
    permissions.includes("team.view");

  if (role === null) {
    // No server seed and context still resolving (e.g. cold backend) — brief spinner.
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <RefreshCw size={24} className="animate-spin text-primary" />
      </div>
    );
  }

  if (role === "caller" && callerId) {
    return <CallerView callerId={callerId} readOnly={!canDial} />;
  }

  if (!canViewTelecalling) {
    return (
      <div className="flex min-h-[400px] items-center justify-center rounded-3xl border border-[#e8e3db] bg-[#faf8f5] p-8 text-center">
        <p className="font-body text-sm text-[#78716c]">This section is not available for this role.</p>
      </div>
    );
  }

  return <AdminView fallbackData={fallbackAdminData ?? undefined} readOnly={!canDial} />;
}
