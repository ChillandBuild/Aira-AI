"use client";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Eye, LogOut } from "lucide-react";
import {
  type ImpersonationSession,
  clearImpersonationSession,
  endImpersonation,
  getImpersonationSession,
  subscribeImpersonation,
} from "@/lib/impersonation";

/**
 * Persistent, unmissable banner shown for the lifetime of a "View as tenant"
 * session. Rendered at the console layout level so it stays visible across
 * every operator page while a session is active — the whole point is that
 * an operator can never lose track of the fact that they are looking at a
 * tenant's data. Exit always calls the audited /impersonation/end endpoint.
 */
export function ImpersonationBanner() {
  const router = useRouter();
  const [session, setSession] = useState<ImpersonationSession | null>(null);
  const [exiting, setExiting] = useState(false);
  const [remaining, setRemaining] = useState("");

  const refresh = useCallback(() => setSession(getImpersonationSession()), []);

  useEffect(() => {
    refresh();
    return subscribeImpersonation(refresh);
  }, [refresh]);

  useEffect(() => {
    if (!session) return;
    const tick = () => {
      const ms = new Date(session.expiresAt).getTime() - Date.now();
      if (ms <= 0) {
        // Local-only cleanup: clear the stored session and notify every
        // other listener (sidebars, client-detail header) so the whole UI
        // re-syncs instead of staying shifted forever. Does not call the
        // backend /end endpoint on expiry — that's deliberate (backlog).
        clearImpersonationSession();
        setSession(null);
        setRemaining("");
        return;
      }
      const mins = Math.floor(ms / 60000);
      const secs = Math.floor((ms % 60000) / 1000);
      setRemaining(`${mins}:${secs.toString().padStart(2, "0")}`);
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [session]);

  async function handleExit() {
    if (!session) return;
    setExiting(true);
    try {
      await endImpersonation(session.tenantId);
    } finally {
      setExiting(false);
      router.push(`/operator/client/${session.tenantId}`);
    }
  }

  if (!session) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      className="sticky top-0 z-50 h-11 flex items-center justify-center gap-3 px-4 bg-amber-500 text-amber-950 shadow-md"
    >
      <Eye size={15} strokeWidth={2.5} />
      <span className="text-sm font-semibold">
        Viewing as <span className="font-bold">{session.tenantName}</span>
      </span>
      <span className="text-xs font-medium text-amber-900/70">Read-only · expires in {remaining || "…"}</span>
      <button
        onClick={handleExit}
        disabled={exiting}
        className="ml-2 flex items-center gap-1.5 px-3 py-1 rounded-lg bg-amber-950/10 hover:bg-amber-950/20 text-xs font-bold uppercase tracking-wide transition-colors disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-amber-950/40"
      >
        <LogOut size={12} />
        {exiting ? "Exiting…" : "Exit"}
      </button>
    </div>
  );
}
