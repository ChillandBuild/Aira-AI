"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { useAuthRole } from "@/app/dashboard/contexts/AuthRoleContext";
import { API_URL, getAuthHeaders } from "@/lib/api";
import {
  LayoutDashboard, MessageSquare, Users, Phone,
  BarChart2, Upload, BookOpen, Layers, FileCheck, StickyNote, Package,
  ChevronDown, ChevronRight, RadioTower, Calendar, CreditCard, ShieldCheck, Megaphone,
} from "lucide-react";
import { cn } from "@/lib/utils";

import { createClient } from "@/lib/supabase/client";
import { AiraLogo } from "@/components/logo";

type NavItem = {
  href: string;
  icon: typeof LayoutDashboard;
  label: string;
  feature?: string;
  badgeType?: "scheduled" | "drafts";
};

const TC_FEATURE_MAP: Record<string, string> = {
  "/dashboard/telecalling/upload": "telecalling.upload",
  "/dashboard/telecalling": "telecalling.dialer",
  "/dashboard/telecalling/scheduled": "telecalling.scheduled",
  "/dashboard/notes": "telecalling.notes",
};

const TC_PERMISSION_MAP: Record<string, string[]> = {
  "/dashboard/telecalling/upload": ["telecalling.upload.view", "telecalling.upload"],
  "/dashboard/telecalling": ["telecalling.dialer.view", "telecalling.dialer"],
  "/dashboard/telecalling/scheduled": ["telecalling.scheduled.view", "telecalling.scheduled"],
  "/dashboard/notes": ["telecalling.notes.view", "telecalling.notes"],
};

const TELECALLING_ITEMS: NavItem[] = [
  { href: "/dashboard/telecalling/upload", icon: Upload, label: "Upload" },
  { href: "/dashboard/telecalling", icon: Phone, label: "Dialer" },
  { href: "/dashboard/telecalling/scheduled", icon: Calendar, label: "Scheduled Calls" },
  { href: "/dashboard/notes", icon: StickyNote, label: "Call Notes" },
];

export function Sidebar() {
  const pathname = usePathname();
  const { role, permissions, enabledFeatures, loading: roleLoading } = useAuthRole();
  const [inboxCount, setInboxCount] = useState(0);
  const [subStatus, setSubStatus] = useState<"loading" | "active" | "none" | "pending_approval">("loading");

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const auth = await getAuthHeaders();
        const res = await fetch(`${API_URL}/api/v1/subscriptions/me`, { headers: auth });
        if (res.ok && active) {
          const data = await res.json();
          setSubStatus(data.status);
        } else if (active) {
          setSubStatus("active");
        }
      } catch {
        if (active) setSubStatus("active");
      }
    })();
    return () => { active = false; };
  }, []);
  
  // Track open/collapsed state of nested groups
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>({
    Telecalling: true,
  });

  const toggleGroup = (groupName: string) => {
    setExpandedGroups(prev => ({ ...prev, [groupName]: !prev[groupName] }));
  };

  const fetchCount = useCallback(async () => {
    try {
      const auth = await getAuthHeaders();
      const res = await fetch(`${API_URL}/api/v1/chat-handovers/count`, { headers: auth });
      if (res.ok) setInboxCount((await res.json()).count ?? 0);
    } catch {}
  }, []);

  const waEnabled = enabledFeatures.includes("whatsapp");
  const outboundOn = enabledFeatures.includes("outbound_messaging");
  const inboundOn = enabledFeatures.includes("inbound_messaging");
  const messagingOn = outboundOn || inboundOn;
  // Telecalling is purchased as a SIM or Tele-CMI bundle (each pulls in its own
  // telecalling.* sub-features); there is no bare "telecalling" key anymore.
  const telecallingOn = enabledFeatures.some(
    (f) => f === "telecalling_sim" || f === "telecalling_telecmi" || f.startsWith("telecalling.")
  );
  useEffect(() => {
    if (!waEnabled) return;
    fetchCount();

    const supabase = createClient();
    const channel = supabase
      .channel("inbox-count-realtime")
      .on(
        "postgres_changes",
        {
          event: "*",
          schema: "public",
          table: "chat_handovers",
        },
        () => {
          fetchCount();
        }
      )
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, [waEnabled, fetchCount]);

  if (roleLoading || subStatus === "loading") {
    return (
      <aside className="fixed left-0 top-0 h-full w-[220px] bg-background border-r border-[#e8e3db] z-20" />
    );
  }

  const isSubscribed = subStatus === "active";
  const can = (permission: string) => role === "owner" || permissions.includes(permission);
  const canAny = (items: string[]) => role === "owner" || items.some((permission) => permissions.includes(permission));

  // Gate telecalling sub-items by sub-feature flags with backwards compatibility
  const hasTcSubFeatures = enabledFeatures.some(f => f.startsWith("telecalling."));
  const visibleTcItems = hasTcSubFeatures
    ? TELECALLING_ITEMS.filter(item => {
        const featureKey = TC_FEATURE_MAP[item.href];
        return !featureKey || enabledFeatures.includes(featureKey);
      })
    : TELECALLING_ITEMS;

  const tcGroupItems = visibleTcItems.filter((item) => {
    const permissionKeys = TC_PERMISSION_MAP[item.href];
    return !permissionKeys || canAny(permissionKeys);
  });

  const isTcActive = tcGroupItems.some(item => pathname.startsWith(item.href));

  // Auto-expand active groups
  const showTc = expandedGroups.Telecalling || isTcActive;

  return (
    <aside className="fixed left-0 top-0 h-full w-[220px] bg-background border-r border-[#e8e3db] flex flex-col z-20 select-none">
      {/* Brand — h-20 (80px) matches the header so this bottom border and the
          header border form one continuous divider. shrink-0 is essential: the
          nav below overflows and would otherwise compress this box under flex
          pressure, lifting the divider above the header's fixed 80px line. */}
      <div className="h-20 shrink-0 flex items-center px-5 border-b border-[#e8e3db]">
        <AiraLogo className="h-7 w-auto text-[#1c1917]" />
      </div>


      <div className="flex-grow overflow-y-auto px-3 py-4 space-y-1.5 scrollbar-thin">
        {/* TOP LEVEL: Overview / Dashboard */}
        {can("dashboard.view") ? (
          <Link
            href="/dashboard"
            className={cn(
              "flex items-center gap-3 px-3 py-2 rounded-xl text-sm font-semibold transition-all duration-150 group",
              pathname === "/dashboard"
                ? "bg-[#f5f3ff] text-[#5b21b6]"
                : "text-[#1c1917] hover:bg-[#f0ece4] hover:text-[#1c1917]"
            )}
          >
            <LayoutDashboard size={16} className={pathname === "/dashboard" ? "text-[#5b21b6]" : "text-[#1c1917] group-hover:text-[#1c1917]"} />
            <span>Dashboard</span>
          </Link>
        ) : (
          <Link
            href="/dashboard/profile"
            className={cn(
              "flex items-center gap-3 px-3 py-2 rounded-xl text-sm font-semibold transition-all duration-150 group",
              pathname === "/dashboard/profile"
                ? "bg-[#f5f3ff] text-[#5b21b6]"
                : "text-[#1c1917] hover:bg-[#f0ece4] hover:text-[#1c1917]"
            )}
          >
            <LayoutDashboard size={16} className={pathname === "/dashboard/profile" ? "text-[#5b21b6]" : "text-[#1c1917] group-hover:text-[#1c1917]"} />
            <span>Overview</span>
          </Link>
        )}

        {/* TOP LEVEL: Conversations */}
        {isSubscribed && messagingOn && canAny(["conversations.view", "conversations.reply"]) && <Link
          href="/dashboard/conversations"
          className={cn(
            "flex items-center gap-3 px-3 py-2 rounded-xl text-sm font-semibold transition-all duration-150 group",
            pathname.startsWith("/dashboard/conversations")
              ? "bg-[#f5f3ff] text-[#5b21b6]"
              : "text-[#1c1917] hover:bg-[#f0ece4] hover:text-[#1c1917]"
          )}
        >
          <MessageSquare size={16} className={pathname.startsWith("/dashboard/conversations") ? "text-[#5b21b6]" : "text-[#1c1917] group-hover:text-[#1c1917]"} />
          <span className="flex-grow">Conversations</span>
          {inboxCount > 0 && (
            <span className="flex-shrink-0 px-1.5 py-0.5 rounded-full bg-orange-100 text-orange-600 font-bold text-[9px] min-w-[16px] text-center">
              {inboxCount}
            </span>
          )}
        </Link>}

        {/* TOP LEVEL: Leads */}
        {isSubscribed && can("leads.view") && messagingOn && (
          <Link
            href="/dashboard/leads"
            className={cn(
              "flex items-center gap-3 px-3 py-2 rounded-xl text-sm font-semibold transition-all duration-150 group",
              pathname.startsWith("/dashboard/leads")
                ? "bg-[#f5f3ff] text-[#5b21b6]"
                : "text-[#1c1917] hover:bg-[#f0ece4] hover:text-[#1c1917]"
            )}
          >
            <Users size={16} className={pathname.startsWith("/dashboard/leads") ? "text-[#5b21b6]" : "text-[#1c1917] group-hover:text-[#1c1917]"} />
            <span>Segments</span>
          </Link>
        )}

        {/* TOP LEVEL: Inbound Leads */}
        {isSubscribed && can("inbound_leads.view") && inboundOn && (
          <Link
            href="/dashboard/inbound-leads"
            className={cn(
              "flex items-center gap-3 px-3 py-2 rounded-xl text-sm font-semibold transition-all duration-150 group",
              pathname.startsWith("/dashboard/inbound-leads")
                ? "bg-[#f5f3ff] text-[#5b21b6]"
                : "text-[#1c1917] hover:bg-[#f0ece4] hover:text-[#1c1917]"
            )}
          >
            <RadioTower size={16} className={pathname.startsWith("/dashboard/inbound-leads") ? "text-[#5b21b6]" : "text-[#1c1917] group-hover:text-[#1c1917]"} />
            <span>Inbound Leads</span>
          </Link>
        )}

        {/* TOP LEVEL: Meta Ads */}
        {isSubscribed && can("inbound_leads.view") && inboundOn && (
          <Link
            href="/dashboard/meta-ads"
            className={cn(
              "flex items-center gap-3 px-3 py-2 rounded-xl text-sm font-semibold transition-all duration-150 group",
              pathname.startsWith("/dashboard/meta-ads")
                ? "bg-[#f5f3ff] text-[#5b21b6]"
                : "text-[#1c1917] hover:bg-[#f0ece4] hover:text-[#1c1917]"
            )}
          >
            <Megaphone size={16} className={pathname.startsWith("/dashboard/meta-ads") ? "text-[#5b21b6]" : "text-[#1c1917] group-hover:text-[#1c1917]"} />
            <span>Meta Ads</span>
          </Link>
        )}

        {/* TOP LEVEL: Outbound Leads */}
        {isSubscribed && canAny(["outbound_leads.view", "outbound_leads.manage"]) && outboundOn && (
          <Link
            href="/dashboard/outbound-leads"
            className={cn(
              "flex items-center gap-3 px-3 py-2 rounded-xl text-sm font-semibold transition-all duration-150 group",
              pathname.startsWith("/dashboard/outbound-leads")
                ? "bg-[#f5f3ff] text-[#5b21b6]"
                : "text-[#1c1917] hover:bg-[#f0ece4] hover:text-[#1c1917]"
            )}
          >
            <Upload size={16} className={pathname.startsWith("/dashboard/outbound-leads") ? "text-[#5b21b6]" : "text-[#1c1917] group-hover:text-[#1c1917]"} />
            <span>Outbound Leads</span>
          </Link>
        )}

        {/* TOP LEVEL: Templates */}
        {isSubscribed && canAny(["templates.view", "templates.manage"]) && outboundOn && (
          <Link
            href="/dashboard/templates"
            className={cn(
              "flex items-center gap-3 px-3 py-2 rounded-xl text-sm font-semibold transition-all duration-150 group",
              pathname.startsWith("/dashboard/templates")
                ? "bg-[#f5f3ff] text-[#5b21b6]"
                : "text-[#1c1917] hover:bg-[#f0ece4] hover:text-[#1c1917]"
            )}
          >
            <FileCheck size={16} className={pathname.startsWith("/dashboard/templates") ? "text-[#5b21b6]" : "text-[#1c1917] group-hover:text-[#1c1917]"} />
            <span>Templates</span>
          </Link>
        )}

        {/* TOP LEVEL: Numbers Pool */}
        {isSubscribed && canAny(["numbers.view", "numbers.manage"]) && messagingOn && (
          <Link
            href="/dashboard/numbers"
            className={cn(
              "flex items-center gap-3 px-3 py-2 rounded-xl text-sm font-semibold transition-all duration-150 group",
              pathname.startsWith("/dashboard/numbers")
                ? "bg-[#f5f3ff] text-[#5b21b6]"
                : "text-[#1c1917] hover:bg-[#f0ece4] hover:text-[#1c1917]"
            )}
          >
            <Layers size={16} className={pathname.startsWith("/dashboard/numbers") ? "text-[#5b21b6]" : "text-[#1c1917] group-hover:text-[#1c1917]"} />
            <span>Numbers Pool</span>
          </Link>
        )}

        {/* TOP LEVEL: Knowledge Base */}
        {isSubscribed && canAny(["knowledge.view", "knowledge.manage"]) && messagingOn && (
          <Link
            href="/dashboard/knowledge"
            className={cn(
              "flex items-center gap-3 px-3 py-2 rounded-xl text-sm font-semibold transition-all duration-150 group",
              pathname.startsWith("/dashboard/knowledge")
                ? "bg-[#f5f3ff] text-[#5b21b6]"
                : "text-[#1c1917] hover:bg-[#f0ece4] hover:text-[#1c1917]"
            )}
          >
            <BookOpen size={16} className={pathname.startsWith("/dashboard/knowledge") ? "text-[#5b21b6]" : "text-[#1c1917] group-hover:text-[#1c1917]"} />
            <span>Knowledge Base</span>
          </Link>
        )}

        {/* TOP LEVEL: Catalog */}
        {isSubscribed && canAny(["catalog.view", "catalog.manage"]) && messagingOn && (
          <Link
            href="/dashboard/catalog"
            className={cn(
              "flex items-center gap-3 px-3 py-2 rounded-xl text-sm font-semibold transition-all duration-150 group",
              pathname.startsWith("/dashboard/catalog")
                ? "bg-[#f5f3ff] text-[#5b21b6]"
                : "text-[#1c1917] hover:bg-[#f0ece4] hover:text-[#1c1917]"
            )}
          >
            <Package size={16} className={pathname.startsWith("/dashboard/catalog") ? "text-[#5b21b6]" : "text-[#1c1917] group-hover:text-[#1c1917]"} />
            <span>Catalog</span>
          </Link>
        )}

        {/* TOP LEVEL: Analytics */}
        {isSubscribed && can("analytics.view") && messagingOn && (
          <Link
            href="/dashboard/analytics"
            className={cn(
              "flex items-center gap-3 px-3 py-2 rounded-xl text-sm font-semibold transition-all duration-150 group",
              pathname.startsWith("/dashboard/analytics")
                ? "bg-[#f5f3ff] text-[#5b21b6]"
                : "text-[#1c1917] hover:bg-[#f0ece4] hover:text-[#1c1917]"
            )}
          >
            <BarChart2 size={16} className={pathname.startsWith("/dashboard/analytics") ? "text-[#5b21b6]" : "text-[#1c1917] group-hover:text-[#1c1917]"} />
            <span>Analytics</span>
          </Link>
        )}

        {/* TOP LEVEL: Subscription */}
        {canAny(["subscription.view", "subscription.manage"]) && (
          <Link
            href="/dashboard/subscription"
            className={cn(
              "flex items-center gap-3 px-3 py-2 rounded-xl text-sm font-semibold transition-all duration-150 group",
              pathname === "/dashboard/subscription"
                ? "bg-[#f5f3ff] text-[#5b21b6]"
                : "text-[#1c1917] hover:bg-[#f0ece4] hover:text-[#1c1917]"
            )}
          >
            <CreditCard size={16} className={pathname === "/dashboard/subscription" ? "text-[#5b21b6]" : "text-[#1c1917] group-hover:text-[#1c1917]"} />
            <span>Subscription</span>
          </Link>
        )}

        {/* TOP LEVEL: Team */}
        {isSubscribed && can("team.view") && (
          <Link
            href="/dashboard/team"
            className={cn(
              "flex items-center gap-3 px-3 py-2 rounded-xl text-sm font-semibold transition-all duration-150 group",
              pathname.startsWith("/dashboard/team")
                ? "bg-[#f5f3ff] text-[#5b21b6]"
                : "text-[#1c1917] hover:bg-[#f0ece4] hover:text-[#1c1917]"
            )}
          >
            <Users size={16} className={pathname.startsWith("/dashboard/team") ? "text-[#5b21b6]" : "text-[#1c1917] group-hover:text-[#1c1917]"} />
            <span>Team</span>
          </Link>
        )}

        {/* TOP LEVEL: Roles */}
        {isSubscribed && canAny(["roles.view", "roles.manage"]) && (
          <Link
            href="/dashboard/roles"
            className={cn(
              "flex items-center gap-3 px-3 py-2 rounded-xl text-sm font-semibold transition-all duration-150 group",
              pathname.startsWith("/dashboard/roles")
                ? "bg-[#f5f3ff] text-[#5b21b6]"
                : "text-[#1c1917] hover:bg-[#f0ece4] hover:text-[#1c1917]"
            )}
          >
            <ShieldCheck size={16} className={pathname.startsWith("/dashboard/roles") ? "text-[#5b21b6]" : "text-[#1c1917] group-hover:text-[#1c1917]"} />
            <span>Roles</span>
          </Link>
        )}

        {/* GROUP: Telecalling */}
        {isSubscribed && telecallingOn && tcGroupItems.length > 0 && (
          <div className="space-y-0.5">
            <button
              onClick={() => toggleGroup("Telecalling")}
              className={cn(
                "flex items-center gap-3 px-3 py-2 w-full rounded-xl text-sm font-semibold text-left transition-all group",
                isTcActive ? "text-[#5b21b6]" : "text-[#1c1917] hover:bg-[#f0ece4]"
              )}
            >
              <Phone size={16} className={isTcActive ? "text-[#5b21b6]" : "text-[#1c1917] group-hover:text-[#1c1917]"} />
              <span className="flex-1">Telecalling</span>
              {showTc ? <ChevronDown size={14} className="text-[#a8a29e]" /> : <ChevronRight size={14} className="text-[#a8a29e]" />}
            </button>

            {/* Tree items */}
            {showTc && (
              <div className="space-y-0.5">
                {tcGroupItems.map((item, idx) => {
                  // Pick the most specific (longest href) match so a parent route
                  // (e.g. Dialer at /dashboard/telecalling) doesn't also light up
                  // when on a nested route (e.g. /dashboard/telecalling/scheduled).
                  const matches = tcGroupItems.filter(
                    (i) => pathname === i.href || pathname.startsWith(i.href + "/")
                  );
                  const bestMatch = matches.reduce<NavItem | null>(
                    (best, i) => (!best || i.href.length > best.href.length ? i : best),
                    null
                  );
                  const active = bestMatch?.href === item.href;
                  const isLast = idx === tcGroupItems.length - 1;

                  return (
                    <div key={item.href} className="relative pl-6 flex items-center h-9">
                      {/* Curved branch lines */}
                      <div
                        className={cn(
                          "absolute left-3 w-px bg-[#d6cfc9]",
                          isLast ? "top-0 h-[18px]" : "-top-1 bottom-0"
                        )}
                      />
                      <div className="absolute left-3 top-1/2 -translate-y-1 w-3.5 h-3.5 border-l border-b border-[#d6cfc9] rounded-bl-lg" />

                      <Link
                        href={item.href}
                        className={cn(
                          "flex items-center gap-2.5 ml-3.5 px-3 py-1.5 w-[145px] rounded-xl text-[13px] transition-all duration-150 group",
                          active
                            ? "bg-white shadow-md border border-[#e8e3db] text-[#5b21b6] font-bold"
                            : "text-[#1c1917] hover:text-[#1c1917] hover:bg-[#f0ece4]"
                        )}
                      >
                        <span className="truncate flex-1">{item.label}</span>
                      </Link>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>


    </aside>
  );
}
