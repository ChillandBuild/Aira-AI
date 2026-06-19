"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { useAuthRole } from "@/app/dashboard/contexts/AuthRoleContext";
import { API_URL, getAuthHeaders } from "@/lib/api";
import {
  LayoutDashboard, MessageSquare, Users, Phone,
  BarChart2, Upload, BookOpen, Layers, FileCheck, StickyNote,
  Inbox, ChevronDown, ChevronRight, RadioTower, Calendar,
} from "lucide-react";
import { cn } from "@/lib/utils";

import { createClient } from "@/lib/supabase/client";

type NavItem = {
  href: string;
  icon: typeof LayoutDashboard;
  label: string;
  feature?: string;
  badgeType?: "inbox" | "scheduled" | "drafts";
};



const TELECALLING_ITEMS: NavItem[] = [
  { href: "/dashboard/telecalling/upload", icon: Upload, label: "Upload" },
  { href: "/dashboard/telecalling", icon: Phone, label: "Dialer" },
  { href: "/dashboard/telecalling/scheduled", icon: Calendar, label: "Scheduled Calls" },
  { href: "/dashboard/notes", icon: StickyNote, label: "Call Notes" },
];

export function Sidebar() {
  const pathname = usePathname();
  const { role, enabledFeatures, pageToggles, loading: roleLoading } = useAuthRole();
  const [inboxCount, setInboxCount] = useState(0);
  
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
  const anyInboundEnabled = ["whatsapp", "instagram", "facebook", "telegram"].some(
    (c) => enabledFeatures.includes(c)
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

  if (roleLoading) {
    return (
      <aside className="fixed left-0 top-0 h-full w-[220px] bg-background z-20" />
    );
  }

  // Helper to check if a page is toggled ON (defaults to true if toggles are missing)
  const isEnabled = (key: string) => {
    if (!pageToggles) return true;
    if (pageToggles[key] === undefined) return true;
    if (typeof pageToggles[key] === 'object') return pageToggles[key].enabled !== false;
    return pageToggles[key] !== false;
  };

  // Helper for nested toggles
  const isNestedEnabled = (parent: string, child: string) => {
    if (!pageToggles) return true;
    if (!pageToggles[parent]) return true;
    if (typeof pageToggles[parent] === 'object') {
      if (pageToggles[parent].enabled === false) return false;
      return pageToggles[parent][child] !== false;
    }
    return true;
  };

  // Filter items by enabled features
  const filterEnabled = (items: NavItem[]) => 
    items.filter(item => !item.feature || enabledFeatures.includes(item.feature));

  // Telecalling items, filtered by toggles
  const baseTcItems = filterEnabled(TELECALLING_ITEMS).filter(
    (item) => item.href !== "/dashboard/telecalling/upload" || role === "owner"
  );
  
  const tcGroupItems = baseTcItems.filter(item => {
    if (item.href === "/dashboard/telecalling/upload") return isNestedEnabled("telecalling", "upload");
    if (item.href === "/dashboard/telecalling") return isNestedEnabled("telecalling", "dialer");
    if (item.href === "/dashboard/telecalling/scheduled") return isNestedEnabled("telecalling", "scheduled");
    if (item.href === "/dashboard/notes") return isNestedEnabled("telecalling", "notes");
    return true;
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
        <span
          className="text-[#1c1917] leading-none select-none"
          style={{
            fontFamily: "var(--font-script), cursive",
            fontSize: "32px",
            paddingBottom: "2px",
          }}
        >
          Aira
        </span>
      </div>

      <div className="flex-grow overflow-y-auto px-3 py-4 space-y-1.5 scrollbar-thin">
        {/* TOP LEVEL: Overview */}
        {role === "owner" && isEnabled("dashboard") && (
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
        )}

        {/* TOP LEVEL: Inbox (Common for all platforms) */}
        {waEnabled && isEnabled("inbox") && (
          <Link
            href="/dashboard/inbox"
            className={cn(
              "flex items-center gap-3 px-3 py-2 rounded-xl text-sm font-semibold transition-all duration-150 group",
              pathname.startsWith("/dashboard/inbox")
                ? "bg-[#f5f3ff] text-[#5b21b6]"
                : "text-[#1c1917] hover:bg-[#f0ece4] hover:text-[#1c1917]"
            )}
          >
            <Inbox size={16} className={pathname.startsWith("/dashboard/inbox") ? "text-[#5b21b6]" : "text-[#1c1917] group-hover:text-[#1c1917]"} />
            <span className="flex-grow">Inbox</span>
            {inboxCount > 0 && (
              <span className="flex-shrink-0 px-1.5 py-0.5 rounded-full bg-orange-100 text-orange-600 font-bold text-[9px] min-w-[16px] text-center">
                {inboxCount}
              </span>
            )}
          </Link>
        )}

        {/* TOP LEVEL: Conversations (Common for all platforms) */}
        {isEnabled("conversations") && (
          <Link
            href="/dashboard/conversations"
            className={cn(
              "flex items-center gap-3 px-3 py-2 rounded-xl text-sm font-semibold transition-all duration-150 group",
              pathname.startsWith("/dashboard/conversations")
                ? "bg-[#f5f3ff] text-[#5b21b6]"
                : "text-[#1c1917] hover:bg-[#f0ece4] hover:text-[#1c1917]"
            )}
          >
            <MessageSquare size={16} className={pathname.startsWith("/dashboard/conversations") ? "text-[#5b21b6]" : "text-[#1c1917] group-hover:text-[#1c1917]"} />
            <span>Conversations</span>
          </Link>
        )}

        {/* TOP LEVEL: Leads */}
        {role === "owner" && isEnabled("segments") && (
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
        {role === "owner" && anyInboundEnabled && isEnabled("inbound_leads") && (
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

        {/* TOP LEVEL: Outbound Leads */}
        {role === "owner" && waEnabled && isEnabled("outbound_leads") && (
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
        {role === "owner" && waEnabled && isEnabled("templates") && (
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
        {role === "owner" && waEnabled && isEnabled("numbers_pool") && (
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

        {/* TOP LEVEL: Knowledge Base (Common for all platforms) */}
        {role === "owner" && isEnabled("knowledge") && (
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

        {/* TOP LEVEL: Analytics */}
        {role === "owner" && isEnabled("analytics") && (
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

        {/* TOP LEVEL: Team */}
        {role === "owner" && isEnabled("team") && (
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



        {/* GROUP: Telecalling */}
        {enabledFeatures.includes("telecalling") && isEnabled("telecalling") && tcGroupItems.length > 0 && (
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
