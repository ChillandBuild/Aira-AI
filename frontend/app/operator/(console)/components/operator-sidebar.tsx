"use client";
import { useState, useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Clock, LogOut } from "lucide-react";
import { createClient } from "@/lib/supabase/client";

const NAV_ITEMS = [
  { href: "/operator", label: "Clients" },
  { href: "/operator/scheduler", label: "Schedulers" },
];

export function OperatorSidebar({ userEmail }: { userEmail: string }) {
  const pathname = usePathname();
  const router = useRouter();
  const [showSignOut, setShowSignOut] = useState(false);
  const [time, setTime] = useState("");

  useEffect(() => {
    const tick = () => {
      const now = new Date();
      setTime(now.toLocaleTimeString("en-US", { hour12: false, hour: "2-digit", minute: "2-digit" }));
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  async function handleSignOut() {
    const supabase = createClient();
    await supabase.auth.signOut();
    router.push("/login");
  }

  const initial = (userEmail || "O")[0].toUpperCase();

  return (
    <>
      <header className="sticky top-0 z-40 h-16 flex items-center justify-between gap-4 px-7 bg-white border-b border-border">
        {/* Left: Logo + Nav */}
        <div className="flex items-center gap-8">
          <div className="flex items-center gap-2">
            <span className="text-lg font-bold text-ink font-display italic">Aira</span>
            <span className="text-[10px] font-semibold text-primary uppercase tracking-[0.15em] bg-primary-light rounded px-2 py-0.5">
              Operator
            </span>
          </div>
          <nav className="flex items-center gap-1">
            {NAV_ITEMS.map((item) => {
              const isActive = item.href === "/operator"
                ? pathname === "/operator" || (pathname?.startsWith("/operator/client") ?? false)
                : pathname?.startsWith(item.href) ?? false;
              return (
                <a
                  key={item.href}
                  href={item.href}
                  className={`px-4 py-2 rounded-xl text-sm font-medium transition-all duration-200 ${
                    isActive
                      ? "bg-primary-light text-primary"
                      : "text-ink-secondary hover:bg-surface-mid hover:text-ink"
                  }`}
                >
                  {item.label}
                </a>
              );
            })}
          </nav>
        </div>

        {/* Right: Clock + Avatar/SignOut */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 h-[34px] px-3 text-ink font-mono text-[13px] font-semibold tracking-wide border border-border rounded-lg">
            <Clock size={13} className="opacity-50" />
            <span>{time || "00:00"}</span>
          </div>
          <button
            onClick={() => setShowSignOut(true)}
            className="w-9 h-9 rounded-full bg-primary flex items-center justify-center text-white text-sm font-bold hover:bg-primary-dark transition-colors"
            title={userEmail}
          >
            {initial}
          </button>
        </div>
      </header>

      {/* Sign Out Confirmation */}
      {showSignOut && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-card shadow-xl w-full max-w-sm p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-full bg-danger/10 flex items-center justify-center">
                <LogOut size={20} className="text-danger" />
              </div>
              <div>
                <h3 className="text-lg font-bold text-ink">Sign Out</h3>
                <p className="text-xs text-ink-muted">{userEmail}</p>
              </div>
            </div>
            <p className="text-sm text-ink-secondary mb-6">
              Are you sure you want to sign out of the operator console?
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => setShowSignOut(false)}
                className="flex-1 px-4 py-2.5 border border-border text-sm text-ink-secondary rounded-xl hover:bg-surface-mid transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSignOut}
                className="flex-1 px-4 py-2.5 bg-danger text-white text-sm font-medium rounded-xl hover:bg-danger/90 transition-colors"
              >
                Sign Out
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
