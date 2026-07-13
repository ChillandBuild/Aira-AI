import { createClient } from "@/lib/supabase/server";
import { serverFetchJson } from "@/lib/serverApi";
import type { Caller, Lead } from "@/lib/api";
import type { AdminDashboardData } from "@/hooks/useApi";
import { TelecallingView } from "./TelecallingView";

interface TeamMe {
  role: "owner" | "caller";
  caller_id: string | null;
  permissions?: string[];
}

export default async function TelecallingPage() {
  const supabase = await createClient();
  const { data: { session } } = await supabase.auth.getSession();
  const token = session?.access_token;

  // Seed the role so the correct view (Admin/Caller) mounts without a spinner.
  const me = await serverFetchJson<TeamMe>("/api/v1/team/me", token);

  // For owners, also seed the admin dashboard data so numbers paint instantly.
  // All timeout-guarded — any null falls back to the client's own SWR fetch.
  let fallbackAdminData: AdminDashboardData | null = null;
  if (me?.role === "owner") {
    const [callersRes, leadsRes, stats] = await Promise.all([
      serverFetchJson<{ data: Caller[] }>("/api/v1/callers/", token),
      serverFetchJson<{ data: Lead[] }>("/api/v1/leads/?limit=5", token),
      serverFetchJson<{ calls_today: number; conversions_today: number }>("/api/v1/calls/stats-today", token),
    ]);
    if (callersRes && leadsRes) {
      fallbackAdminData = {
        callers: callersRes.data ?? [],
        topLeads: leadsRes.data ?? [],
        totalCallsToday: stats?.calls_today ?? 0,
        totalConversionsToday: stats?.conversions_today ?? 0,
      };
    }
  }

  return (
    <TelecallingView
      initialRole={me?.role ?? null}
      initialCallerId={me?.caller_id ?? null}
      initialPermissions={me?.permissions ?? []}
      fallbackAdminData={fallbackAdminData}
    />
  );
}
