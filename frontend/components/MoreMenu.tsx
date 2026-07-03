"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import {
  BarChart2,
  BookOpen,
  Calendar,
  Grid3X3,
  Inbox,
  Layers,
  Menu,
  Settings,
  SquarePen,
  StickyNote,
  Upload,
  Users,
  X,
} from "lucide-react";
import { useAuthRole } from "@/app/dashboard/contexts/AuthRoleContext";
import { cn, isActive } from "@/lib/utils";

type MoreMenuItem = {
  href: string;
  icon: typeof Users;
  label: string;
  ownerOnly?: boolean;
  feature?: string;
  anyFeature?: string[];
};

const MORE_ITEMS: MoreMenuItem[] = [
  { href: "/dashboard/leads", icon: Users, label: "Leads", ownerOnly: true, anyFeature: ["outbound_leads", "inbound_leads"] },
  { href: "/dashboard/outbound-leads", icon: Upload, label: "Send", ownerOnly: true, feature: "outbound_leads" },
  { href: "/dashboard/templates", icon: SquarePen, label: "Templates", ownerOnly: true, feature: "outbound_leads" },
  { href: "/dashboard/telecalling/scheduled", icon: Calendar, label: "Scheduled Calls", feature: "telecalling.scheduled" },
  { href: "/dashboard/notes", icon: StickyNote, label: "Call Notes", feature: "telecalling.notes" },
  { href: "/dashboard/inbound-leads", icon: Inbox, label: "Inbound Leads", ownerOnly: true, feature: "inbound_leads" },
  { href: "/dashboard/numbers", icon: Layers, label: "Numbers Pool", ownerOnly: true, anyFeature: ["outbound_leads", "inbound_leads"] },
  { href: "/dashboard/knowledge", icon: BookOpen, label: "Knowledge Base", ownerOnly: true, anyFeature: ["outbound_leads", "inbound_leads"] },
  { href: "/dashboard/analytics", icon: BarChart2, label: "Analytics", ownerOnly: true, anyFeature: ["outbound_leads", "inbound_leads"] },
  { href: "/dashboard/team", icon: Grid3X3, label: "Team", ownerOnly: true },
  { href: "/dashboard/settings", icon: Settings, label: "Settings", ownerOnly: true },
];

function isVisible(item: MoreMenuItem, role: string | null, enabledFeatures: string[]) {
  if (item.ownerOnly && role !== "owner") return false;
  if (item.feature && !enabledFeatures.includes(item.feature)) return false;
  if (item.anyFeature && !item.anyFeature.some((feature) => enabledFeatures.includes(feature))) return false;
  return true;
}

export function MoreMenu() {
  const pathname = usePathname() || "/dashboard";
  const { role, enabledFeatures } = useAuthRole();
  const [isOpen, setIsOpen] = useState(false);

  const items = MORE_ITEMS.filter((item) => isVisible(item, role, enabledFeatures));

  return (
    <div className="relative md:hidden">
      <button
        type="button"
        onClick={() => setIsOpen(true)}
        aria-label="More"
        className="flex h-[34px] w-[34px] items-center justify-center rounded-full text-white transition-transform hover:scale-105"
        style={{ background: "linear-gradient(135deg, #2e1065, #5b21b6)" }}
      >
        <Menu size={16} />
      </button>

      {isOpen && (
        <div className="fixed inset-0 z-[70] md:hidden">
          <button
            type="button"
            aria-label="Close navigation"
            className="absolute inset-0 bg-black/35"
            onClick={() => setIsOpen(false)}
          />
          <div className="absolute left-0 top-0 bottom-[calc(4.75rem+env(safe-area-inset-bottom))] w-[80vw] max-w-xs overflow-y-auto bg-white p-4 pt-[calc(1rem+env(safe-area-inset-top))] shadow-2xl animate-in fade-in slide-in-from-left duration-200">
            <div className="mb-3 flex items-center justify-between px-1">
              <div className="font-display text-sm font-extrabold text-ink">More</div>
              <button
                type="button"
                onClick={() => setIsOpen(false)}
                className="flex h-9 w-9 items-center justify-center rounded-full text-ink-secondary hover:bg-surface-mid"
                aria-label="Close"
              >
                <X size={18} />
              </button>
            </div>
            {items.length === 0 ? (
              <div className="rounded-xl border border-border-subtle bg-surface-low px-3 py-4 text-center font-body text-sm text-ink-muted">
                No more sections are available for this account.
              </div>
            ) : (
              <div className="flex flex-col gap-2">
                {items.map((item) => {
                  const Icon = item.icon;
                  const active = isActive(pathname, item.href);
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      onClick={() => setIsOpen(false)}
                      className={cn(
                        "flex min-h-12 items-center gap-3 rounded-xl border px-3 py-2.5 text-sm font-bold",
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
            )}
          </div>
        </div>
      )}
    </div>
  );
}
