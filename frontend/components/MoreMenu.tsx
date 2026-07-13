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
  Package,
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
  permissionAny?: string[];
  feature?: string;
  anyFeature?: string[];
};

const MORE_ITEMS: MoreMenuItem[] = [
  { href: "/dashboard/leads", icon: Users, label: "Leads", permissionAny: ["leads.view", "leads.manage"], anyFeature: ["outbound_messaging", "inbound_messaging"] },
  { href: "/dashboard/outbound-leads", icon: Upload, label: "Send", permissionAny: ["outbound_leads.view", "outbound_leads.manage"], feature: "outbound_messaging" },
  { href: "/dashboard/templates", icon: SquarePen, label: "Templates", permissionAny: ["templates.view", "templates.manage"], feature: "outbound_messaging" },
  { href: "/dashboard/telecalling/scheduled", icon: Calendar, label: "Scheduled Calls", permissionAny: ["telecalling.scheduled.view", "telecalling.scheduled"], feature: "telecalling.scheduled" },
  { href: "/dashboard/notes", icon: StickyNote, label: "Call Notes", permissionAny: ["telecalling.notes.view", "telecalling.notes"], feature: "telecalling.notes" },
  { href: "/dashboard/inbound-leads", icon: Inbox, label: "Inbound Leads", permissionAny: ["inbound_leads.view", "inbound_leads.manage"], feature: "inbound_messaging" },
  { href: "/dashboard/numbers", icon: Layers, label: "Numbers Pool", permissionAny: ["numbers.view", "numbers.manage"], anyFeature: ["outbound_messaging", "inbound_messaging"] },
  { href: "/dashboard/knowledge", icon: BookOpen, label: "Knowledge Base", permissionAny: ["knowledge.view", "knowledge.manage"], anyFeature: ["outbound_messaging", "inbound_messaging"] },
  { href: "/dashboard/catalog", icon: Package, label: "Catalog", permissionAny: ["catalog.view", "catalog.manage"], anyFeature: ["outbound_messaging", "inbound_messaging"] },
  { href: "/dashboard/analytics", icon: BarChart2, label: "Analytics", permissionAny: ["analytics.view"], anyFeature: ["outbound_messaging", "inbound_messaging"] },
  { href: "/dashboard/team", icon: Grid3X3, label: "Team", permissionAny: ["team.view", "team.manage"] },
  { href: "/dashboard/settings", icon: Settings, label: "Settings", permissionAny: ["settings.view", "settings.manage"] },
];

function isVisible(item: MoreMenuItem, role: string | null, enabledFeatures: string[], permissions: string[]) {
  if (role !== "owner" && item.permissionAny && !item.permissionAny.some((permission) => permissions.includes(permission))) return false;
  if (item.feature && !enabledFeatures.includes(item.feature)) return false;
  if (item.anyFeature && !item.anyFeature.some((feature) => enabledFeatures.includes(feature))) return false;
  return true;
}

export function MoreMenu() {
  const pathname = usePathname() || "/dashboard";
  const { role, enabledFeatures, permissions } = useAuthRole();
  const [isOpen, setIsOpen] = useState(false);

  const items = MORE_ITEMS.filter((item) => isVisible(item, role, enabledFeatures, permissions));

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
