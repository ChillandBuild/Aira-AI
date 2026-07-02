"use client";
import { useCallback, useEffect, useState } from "react";
import { Eye } from "lucide-react";
import { getImpersonationSession, startImpersonation, subscribeImpersonation } from "@/lib/impersonation";

/**
 * "View as tenant" action for the client detail header. Starts a read-only,
 * audited, time-boxed impersonation session (POST /operator/impersonation/start)
 * and lets the persistent banner (rendered at the console layout level) take
 * over from there. Disabled while already viewing this tenant.
 */
export function ViewAsTenantButton({ tenantId, tenantName }: { tenantId: string; tenantName: string }) {
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [active, setActive] = useState(false);

  const refresh = useCallback(() => {
    const session = getImpersonationSession();
    setActive(session?.tenantId === tenantId);
  }, [tenantId]);

  useEffect(() => {
    refresh();
    return subscribeImpersonation(refresh);
  }, [refresh]);

  async function handleClick() {
    setStarting(true);
    setError(null);
    try {
      await startImpersonation(tenantId);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start impersonation");
    } finally {
      setStarting(false);
    }
  }

  return (
    <div className="relative">
      <button
        onClick={handleClick}
        disabled={starting || active}
        aria-label={active ? `Currently viewing as ${tenantName}` : `View as ${tenantName} (read-only)`}
        title="Start a read-only, audited support session as this tenant"
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold border border-primary/30 bg-primary-light text-primary hover:bg-primary/15 transition-colors disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-primary/40"
      >
        <Eye size={13} />
        {active ? "Viewing as tenant" : starting ? "Starting…" : "View as tenant"}
      </button>
      {error && (
        <div className="absolute right-0 top-full mt-1.5 z-30 w-64 p-2.5 bg-white border border-danger/20 rounded-lg shadow-lg text-xs text-danger">
          {error}
        </div>
      )}
    </div>
  );
}
