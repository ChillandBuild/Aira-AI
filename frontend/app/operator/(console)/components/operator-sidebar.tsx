"use client";
import { usePathname, useRouter } from "next/navigation";
import { LayoutGrid, Clock, LogOut } from "lucide-react";
import { createClient } from "@/lib/supabase/client";

const NAV_ITEMS = [
  { href: "/operator", icon: LayoutGrid, label: "Clients" },
  { href: "/operator/scheduler", icon: Clock, label: "Schedulers" },
];

export function OperatorSidebar({ userEmail }: { userEmail: string }) {
  const pathname = usePathname();
  const router = useRouter();

  async function handleSignOut() {
    const supabase = createClient();
    await supabase.auth.signOut();
    router.push("/operator/login");
  }

  return (
    <aside className="fixed left-0 top-0 w-[240px] h-screen bg-white border-r border-border flex flex-col z-40">
      {/* Header */}
      <div className="px-6 py-5 border-b border-border-subtle">
        <div className="flex items-center gap-2">
          <span className="text-lg font-bold text-ink font-display">
            Aira <span className="text-primary">AI</span>
          </span>
        </div>
        <span className="inline-block mt-1.5 text-[10px] font-semibold text-primary uppercase tracking-[0.15em] bg-primary-light rounded px-2 py-0.5">
          Operator
        </span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4 space-y-1">
        {NAV_ITEMS.map((item) => {
          const isActive = item.href === "/operator"
            ? pathname === "/operator"
            : pathname.startsWith(item.href);
          return (
            <a
              key={item.href}
              href={item.href}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 ${
                isActive
                  ? "bg-primary-light text-primary border-l-[3px] border-primary"
                  : "text-ink-secondary hover:bg-surface-mid hover:text-ink"
              }`}
            >
              <item.icon size={18} />
              {item.label}
            </a>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="px-4 py-4 border-t border-border-subtle">
        <p className="text-xs text-ink-muted truncate mb-2">{userEmail}</p>
        <button
          onClick={handleSignOut}
          className="flex items-center gap-2 w-full px-3 py-2 rounded-xl text-sm text-ink-secondary hover:text-danger hover:bg-red-50 transition-all duration-200"
        >
          <LogOut size={16} />
          Sign Out
        </button>
      </div>
    </aside>
  );
}
