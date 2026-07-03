"use client";
import { useState, useEffect, Suspense } from "react";
import { usePathname } from "next/navigation";
import { Sidebar } from "@/components/sidebar";
import { AuthRoleProvider } from "./contexts/AuthRoleContext";
import { ActiveCallProvider } from "./contexts/ActiveCallContext";
import { CalendarPanel } from "@/components/CalendarPanel";
import { SessionTracker } from "@/components/SessionTracker";
import { AppHeader } from "@/components/AppHeader";
import { ClaimBanner } from "@/components/ClaimBanner";
import { MobileDashboardNav } from "@/components/MobileDashboardNav";
import { MoreMenu } from "@/components/MoreMenu";
import { API_URL } from "@/lib/api";
import { NotificationProvider } from "@/hooks/useNotifications";

const PING_INTERVAL_MS = 8 * 60 * 1000; // 8 min — keeps Render warm (sleeps after 15 min)

export function ClientLayout({ children }: { children: React.ReactNode }) {
  const [isCalendarOpen, setIsCalendarOpen] = useState(false);
  const [isInboxSidebarOpen, setIsInboxSidebarOpen] = useState(false);
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
    const handleOpen = () => setIsInboxSidebarOpen(true);
    const handleClose = () => setIsInboxSidebarOpen(false);
    window.addEventListener("open-inbox-sidebar", handleOpen);
    window.addEventListener("close-inbox-sidebar", handleClose);
    return () => {
      window.removeEventListener("open-inbox-sidebar", handleOpen);
      window.removeEventListener("close-inbox-sidebar", handleClose);
    };
  }, []);

  useEffect(() => {
    setIsInboxSidebarOpen(false);
  }, [pathname]);

  if (isInbox) {
    return (
      <AuthRoleProvider>
        <ActiveCallProvider>
          <NotificationProvider>
            <SessionTracker />
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
              <div className="fixed top-[calc(0.75rem+env(safe-area-inset-top))] right-3 z-[65] md:hidden">
                <MoreMenu />
              </div>
              <MobileDashboardNav />
            </div>
            <CalendarPanel isOpen={isCalendarOpen} onClose={() => setIsCalendarOpen(false)} />
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
        </NotificationProvider>
      </ActiveCallProvider>
    </AuthRoleProvider>
  );
}
