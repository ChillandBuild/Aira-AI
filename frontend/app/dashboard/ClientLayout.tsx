"use client";
import { useState, useEffect, Suspense } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Sidebar } from "@/components/sidebar";
import { AuthRoleProvider } from "./contexts/AuthRoleContext";
import { ActiveCallProvider } from "./contexts/ActiveCallContext";
import { CalendarPanel } from "@/components/CalendarPanel";
import { SessionTracker } from "@/components/SessionTracker";
import { AppHeader } from "@/components/AppHeader";
import { ClaimBanner } from "@/components/ClaimBanner";
import { MobileDashboardNav } from "@/components/MobileDashboardNav";
import { MoreMenu } from "@/components/MoreMenu";
import { API_URL, getAuthHeaders } from "@/lib/api";
import { useAuthRole } from "./contexts/AuthRoleContext";
import { AiraLoader } from "@/components/AiraLoader";
import { NotificationProvider } from "@/hooks/useNotifications";
import ChangePasswordCard from "./settings/ChangePasswordCard";

const PING_INTERVAL_MS = 8 * 60 * 1000; // 8 min — keeps Render warm (sleeps after 15 min)

function DashboardAuthGuard({ children }: { children: React.ReactNode }) {
  const { loading: roleLoading, forcePasswordReset, bootstrapError } = useAuthRole();

  if (roleLoading) {
    return <AiraLoader showRetryAfterMs={15000} onRetry={() => window.location.reload()} />;
  }

  if (bootstrapError) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background p-6">
        <div className="w-full max-w-md rounded-2xl border border-red-100 bg-white p-6 text-center shadow-sm">
          <p className="font-label text-[10px] font-black uppercase tracking-wider text-red-600">Workspace access failed</p>
          <p className="mt-3 font-body text-sm leading-6 text-ink-muted">{bootstrapError}</p>
          <button type="button" onClick={() => window.location.reload()} className="btn-primary mt-5 justify-center">
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (forcePasswordReset) {
    return (
      <div className="mx-auto w-full max-w-4xl p-4 md:p-8">
        <div className="mb-4 rounded-3xl border border-amber-200 bg-amber-50 px-5 py-4">
          <p className="font-label text-[10px] font-black uppercase tracking-wider text-amber-700">Password reset required</p>
          <p className="mt-1 font-body text-sm text-ink">Update your temporary password before using the dashboard.</p>
        </div>
        <ChangePasswordCard defaultOpen />
      </div>
    );
  }

  return <>{children}</>;
}

export function ClientLayout({ children }: { children: React.ReactNode }) {
  const [isCalendarOpen, setIsCalendarOpen] = useState(false);
  const [isInboxSidebarOpen, setIsInboxSidebarOpen] = useState(false);
  const [subStatus, setSubStatus] = useState<"loading" | "none" | "pending_approval" | "active">("loading");
  const pathname = usePathname();
  // The conversations route renders its own thin inbox rail (Bulkwise-style) and
  // fills the viewport, so we suppress the labeled sidebar + app header there.
  const isInbox = pathname?.startsWith("/dashboard/conversations") ?? false;

  useEffect(() => {
    const ping = () => fetch(`${API_URL}/health`, { method: "GET" }).catch(() => {});
    ping(); // immediate ping on mount to wake server if sleeping
    const id = setInterval(ping, PING_INTERVAL_MS);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const auth = await getAuthHeaders();
        const res = await fetch(`${API_URL}/api/v1/subscriptions/me`, { headers: auth });
        if (res.ok) {
          const data = await res.json();
          setSubStatus(data.status);
        } else {
          setSubStatus("active"); // fail open — e.g. pre-existing/backfilled tenants if the call errors
        }
      } catch {
        setSubStatus("active");
      }
    })();
  }, []);

  useEffect(() => {
    const handleOpen = () => setIsInboxSidebarOpen(true);
    const handleClose = () => setIsInboxSidebarOpen(false);
    window.addEventListener("open-inbox-sidebar", handleOpen);
    window.addEventListener("close-inbox-sidebar", handleClose);
    return () => {
      window.removeEventListener("open-inbox-sidebar", handleOpen);
      window.removeEventListener("close-inbox-sidebar", handleClose);
    };
  }, []);

  const router = useRouter();

  useEffect(() => {
    setIsInboxSidebarOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (subStatus === "none" || subStatus === "pending_approval") {
      const allowed = pathname === "/dashboard" || pathname === "/dashboard/subscription";
      if (!allowed) {
        router.replace("/dashboard");
      }
    }
  }, [subStatus, pathname, router]);

  if (subStatus === "loading") {
    return <AiraLoader />;
  }

  if (isInbox) {
    return (
      <AuthRoleProvider>
        <ActiveCallProvider>
          <NotificationProvider>
            <SessionTracker />
            <DashboardAuthGuard>
              <div className="h-screen bg-background overflow-hidden relative">
                {isInboxSidebarOpen && (
                  <>
                    {/* Backdrop */}
                    <div
                      onClick={() => setIsInboxSidebarOpen(false)}
                      className="fixed inset-0 bg-black/45 backdrop-blur-xs z-40 transition-opacity cursor-pointer"
                    />
                    {/* Labeled Sidebar Drawer Overlay */}
                    <div className="fixed left-0 top-0 bottom-0 w-[220px] z-50 [&>aside]:z-50 [&>aside]:shadow-2xl animate-in slide-in-from-left duration-200">
                      <Sidebar />
                    </div>
                  </>
                )}
                {children}
                <div className="fixed top-[calc(0.75rem+env(safe-area-inset-top))] left-3 z-[65] md:hidden">
                  <MoreMenu />
                </div>
                <MobileDashboardNav />
              </div>
              <CalendarPanel isOpen={isCalendarOpen} onClose={() => setIsCalendarOpen(false)} />
            </DashboardAuthGuard>
          </NotificationProvider>
        </ActiveCallProvider>
      </AuthRoleProvider>
    );
  }

  return (
    <AuthRoleProvider>
      <ActiveCallProvider>
        <NotificationProvider>
          <SessionTracker />
          <DashboardAuthGuard>
            <div className="flex min-h-screen overflow-x-hidden bg-background">
              <div className="hidden md:block">
                <Sidebar />
              </div>

              <main className="flex min-h-screen min-w-0 flex-1 flex-col md:ml-[220px]">
                <Suspense fallback={<div className="h-20 bg-[#faf8f5] border-b border-[#e8e3db]" />}>
                  <AppHeader onOpenCalendar={() => setIsCalendarOpen(true)} />
                </Suspense>
                <ClaimBanner />
                <div className="w-full min-w-0 max-w-[1400px] overflow-x-hidden px-3 py-4 pb-28 sm:px-4 md:p-7">
                  {children}
                </div>
              </main>

              <MobileDashboardNav />

              <CalendarPanel
                isOpen={isCalendarOpen}
                onClose={() => setIsCalendarOpen(false)}
              />
            </div>
          </DashboardAuthGuard>
        </NotificationProvider>
      </ActiveCallProvider>
    </AuthRoleProvider>
  );
}
