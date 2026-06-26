"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import {
  BarChart2,
  BookOpen,
  FileCheck,
  Grid3X3,
  Home,
  Inbox,
  Layers,
  Menu,
  MessageSquare,
  Phone,
  Settings,
  Upload,
  Users,
  X,
} from "lucide-react";
import { useAuthRole } from "@/app/dashboard/contexts/AuthRoleContext";
import { cn } from "@/lib/utils";

type MobileNavItem = {
  href: string;
  icon: typeof Home;
  label: string;
  ownerOnly?: boolean;
  feature?: string;
  anyFeature?: string[];
};

const PRIMARY_ITEMS: MobileNavItem[] = [
  { href: "/dashboard", icon: Home, label: "Home", ownerOnly: true },
  { href: "/dashboard/conversations", icon: MessageSquare, label: "Inbox", anyFeature: ["outbound_leads", "inbound_leads"] },
  { href: "/dashboard/leads", icon: Users, label: "Leads", ownerOnly: true, anyFeature: ["outbound_leads", "inbound_leads"] },
  { href: "/dashboard/telecalling", icon: Phone, label: "Calls", feature: "telecalling" },
];

const MORE_ITEMS: MobileNavItem[] = [
  { href: "/dashboard/inbound-leads", icon: Inbox, label: "Inbound Leads", ownerOnly: true, feature: "inbound_leads" },
  { href: "/dashboard/outbound-leads", icon: Upload, label: "Outbound Leads", ownerOnly: true, feature: "outbound_leads" },
  { href: "/dashboard/templates", icon: FileCheck, label: "Templates", ownerOnly: true, feature: "outbound_leads" },
  { href: "/dashboard/numbers", icon: Layers, label: "Numbers Pool", ownerOnly: true, anyFeature: ["outbound_leads", "inbound_leads"] },
  { href: "/dashboard/knowledge", icon: BookOpen, label: "Knowledge Base", ownerOnly: true, anyFeature: ["outbound_leads", "inbound_leads"] },
  { href: "/dashboard/analytics", icon: BarChart2, label: "Analytics", ownerOnly: true, anyFeature: ["outbound_leads", "inbound_leads"] },
  { href: "/dashboard/team", icon: Grid3X3, label: "Team", ownerOnly: true },
  { href: "/dashboard/settings", icon: Settings, label: "Settings", ownerOnly: true },
];

function isVisible(item: MobileNavItem, role: string | null, enabledFeatures: string[]) {
  if (item.ownerOnly && role !== "owner") return false;
  if (item.feature && !enabledFeatures.includes(item.feature)) return false;
  if (item.anyFeature && !item.anyFeature.some((feature) => enabledFeatures.includes(feature))) return false;
  return true;
}

function isActive(pathname: string, href: string) {
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function MobileDashboardNav() {
  const pathname = usePathname() || "/dashboard";
  const { role, enabledFeatures } = useAuthRole();
  const [isMoreOpen, setIsMoreOpen] = useState(false);

  const primaryItems = PRIMARY_ITEMS.filter((item) => isVisible(item, role, enabledFeatures));
  const moreItems = MORE_ITEMS.filter((item) => isVisible(item, role, enabledFeatures));

  return (
    <>
      {isMoreOpen && (
        <div className="fixed inset-0 z-[70] md:hidden">
          <button
            type="button"
            aria-label="Close navigation"
            className="absolute inset-0 bg-black/35"
            onClick={() => setIsMoreOpen(false)}
          />
          <div className="absolute inset-x-3 bottom-[calc(5.75rem+env(safe-area-inset-bottom))] rounded-3xl border border-border bg-white p-3 shadow-2xl">
            <div className="mb-2 flex items-center justify-between px-2">
              <div className="font-display text-sm font-extrabold text-ink">More</div>
              <button
                type="button"
                onClick={() => setIsMoreOpen(false)}
                className="flex h-9 w-9 items-center justify-center rounded-full text-ink-secondary hover:bg-surface-mid"
                aria-label="Close"
              >
                <X size={18} />
              </button>
            </div>
            <div className="grid grid-cols-2 gap-2">
              {moreItems.map((item) => {
                const Icon = item.icon;
                const active = isActive(pathname, item.href);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    onClick={() => setIsMoreOpen(false)}
                    className={cn(
                      "flex items-center gap-3 rounded-2xl border px-3 py-3 text-sm font-bold",
                      active
                        ? "border-primary-muted bg-primary-light text-primary"
                        : "border-border-subtle bg-surface-low text-ink hover:border-border"
                    )}
                  >
                    <Icon size={17} />
                    <span className="min-w-0 truncate">{item.label}</span>
                  </Link>
                );
              })}
            </div>
          </div>
        </div>
      )}

      <nav className="fixed inset-x-0 bottom-0 z-[60] border-t border-border bg-white/95 px-3 pt-2 shadow-[0_-10px_30px_rgba(28,25,23,0.08)] backdrop-blur md:hidden">
        <div className="mx-auto grid max-w-md grid-cols-5 gap-1 pb-[calc(0.65rem+env(safe-area-inset-bottom))]">
          {primaryItems.slice(0, 4).map((item) => {
            const Icon = item.icon;
            const active = isActive(pathname, item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex min-w-0 flex-col items-center justify-center gap-1 rounded-2xl px-1 py-2 text-[10px] font-extrabold",
                  active ? "bg-primary-light text-primary" : "text-ink-secondary"
                )}
              >
                <Icon size={19} strokeWidth={2.2} />
                <span className="truncate">{item.label}</span>
              </Link>
            );
          })}

          <button
            type="button"
            onClick={() => setIsMoreOpen(true)}
            className={cn(
              "flex min-w-0 flex-col items-center justify-center gap-1 rounded-2xl px-1 py-2 text-[10px] font-extrabold",
              moreItems.some((item) => isActive(pathname, item.href)) ? "bg-primary-light text-primary" : "text-ink-secondary"
            )}
          >
            <Menu size={19} strokeWidth={2.2} />
            <span>More</span>
          </button>
        </div>
      </nav>
    </>
  );
}
