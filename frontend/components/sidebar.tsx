"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { useAuthRole } from "@/app/dashboard/contexts/AuthRoleContext";
import { API_URL, getAuthHeaders } from "@/lib/api";
import {
  LayoutDashboard, MessageSquare, Users, Settings, Phone,
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
  const { role, enabledFeatures, loading: roleLoading } = useAuthRole();
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

  // Filter items by enabled features
  const filterEnabled = (items: NavItem[]) => 
    items.filter(item => !item.feature || enabledFeatures.includes(item.feature));

  const tcGroupItems = filterEnabled(TELECALLING_ITEMS);

  const isTcActive = tcGroupItems.some(item => pathname.startsWith(item.href));

  // Auto-expand active groups
  const showTc = expandedGroups.Telecalling || isTcActive;

  return (
    <aside className="fixed left-0 top-0 h-full w-[220px] bg-background flex flex-col z-20 select-none">
      {/* Brand */}
      <div className="px-5 py-5">
        <span
          className="block font-display font-extrabold leading-none text-[22px] text-[#5b21b6]"
          style={{
            letterSpacing: "-0.04em",
            textShadow: "0 0 4px rgba(91,33,182,0.6), 0 0 14px rgba(91,33,182,0.3), 0 0 30px rgba(91,33,182,0.15)",
          }}
        >
          Aira
        </span>
      </div>

      <div className="mx-5 h-px bg-[#e8e3db]" />

      <div className="flex-grow overflow-y-auto px-3 py-4 space-y-1.5 scrollbar-thin">
        {/* TOP LEVEL: Overview */}
        {role === "owner" && (
          <Link
            href="/dashboard"
            className={cn(
              "flex items-center gap-3 px-3 py-2 rounded-xl text-sm font-semibold transition-all duration-150 group",
              pathname === "/dashboard"
                ? "bg-[#f5f3ff] text-[#5b21b6]"
                : "text-[#78716c] hover:bg-[#f0ece4] hover:text-[#1c1917]"
            )}
          >
            <LayoutDashboard size={16} className={pathname === "/dashboard" ? "text-[#5b21b6]" : "text-[#a8a29e] group-hover:text-[#78716c]"} />
            <span>Dashboard</span>
          </Link>
        )}

        {/* TOP LEVEL: Inbox (Common for all platforms) */}
        {waEnabled && (
          <Link
            href="/dashboard/inbox"
            className={cn(
              "flex items-center gap-3 px-3 py-2 rounded-xl text-sm font-semibold transition-all duration-150 group",
              pathname.startsWith("/dashboard/inbox")
                ? "bg-[#f5f3ff] text-[#5b21b6]"
                : "text-[#78716c] hover:bg-[#f0ece4] hover:text-[#1c1917]"
            )}
          >
            <Inbox size={16} className={pathname.startsWith("/dashboard/inbox") ? "text-[#5b21b6]" : "text-[#a8a29e] group-hover:text-[#78716c]"} />
            <span className="flex-grow">Inbox</span>
            {inboxCount > 0 && (
              <span className="flex-shrink-0 px-1.5 py-0.5 rounded-full bg-orange-100 text-orange-600 font-bold text-[9px] min-w-[16px] text-center">
                {inboxCount}
              </span>
            )}
          </Link>
        )}

        {/* TOP LEVEL: Conversations (Common for all platforms) */}
        <Link
          href="/dashboard/conversations"
          className={cn(
            "flex items-center gap-3 px-3 py-2 rounded-xl text-sm font-semibold transition-all duration-150 group",
            pathname.startsWith("/dashboard/conversations")
              ? "bg-[#f5f3ff] text-[#5b21b6]"
              : "text-[#78716c] hover:bg-[#f0ece4] hover:text-[#1c1917]"
          )}
        >
          <MessageSquare size={16} className={pathname.startsWith("/dashboard/conversations") ? "text-[#5b21b6]" : "text-[#a8a29e] group-hover:text-[#78716c]"} />
          <span>Conversations</span>
        </Link>

        {/* TOP LEVEL: Leads */}
        {role === "owner" && (
          <Link
            href="/dashboard/leads"
            className={cn(
              "flex items-center gap-3 px-3 py-2 rounded-xl text-sm font-semibold transition-all duration-150 group",
              pathname.startsWith("/dashboard/leads")
                ? "bg-[#f5f3ff] text-[#5b21b6]"
                : "text-[#78716c] hover:bg-[#f0ece4] hover:text-[#1c1917]"
            )}
          >
            <Users size={16} className={pathname.startsWith("/dashboard/leads") ? "text-[#5b21b6]" : "text-[#a8a29e] group-hover:text-[#78716c]"} />
            <span>Segments</span>
          </Link>
        )}

        {/* TOP LEVEL: Inbound Leads */}
        {role === "owner" && anyInboundEnabled && (
          <Link
            href="/dashboard/inbound-leads"
            className={cn(
              "flex items-center gap-3 px-3 py-2 rounded-xl text-sm font-semibold transition-all duration-150 group",
              pathname.startsWith("/dashboard/inbound-leads")
                ? "bg-[#f5f3ff] text-[#5b21b6]"
                : "text-[#78716c] hover:bg-[#f0ece4] hover:text-[#1c1917]"
            )}
          >
            <RadioTower size={16} className={pathname.startsWith("/dashboard/inbound-leads") ? "text-[#5b21b6]" : "text-[#a8a29e] group-hover:text-[#78716c]"} />
            <span>Inbound Leads</span>
          </Link>
        )}

        {/* TOP LEVEL: Outbound Leads */}
        {role === "owner" && waEnabled && (
          <Link
            href="/dashboard/outbound-leads"
            className={cn(
              "flex items-center gap-3 px-3 py-2 rounded-xl text-sm font-semibold transition-all duration-150 group",
              pathname.startsWith("/dashboard/outbound-leads")
                ? "bg-[#f5f3ff] text-[#5b21b6]"
                : "text-[#78716c] hover:bg-[#f0ece4] hover:text-[#1c1917]"
            )}
          >
            <Upload size={16} className={pathname.startsWith("/dashboard/outbound-leads") ? "text-[#5b21b6]" : "text-[#a8a29e] group-hover:text-[#78716c]"} />
            <span>Outbound Leads</span>
          </Link>
        )}

        {/* TOP LEVEL: Templates */}
        {role === "owner" && waEnabled && (
          <Link
            href="/dashboard/templates"
            className={cn(
              "flex items-center gap-3 px-3 py-2 rounded-xl text-sm font-semibold transition-all duration-150 group",
              pathname.startsWith("/dashboard/templates")
                ? "bg-[#f5f3ff] text-[#5b21b6]"
                : "text-[#78716c] hover:bg-[#f0ece4] hover:text-[#1c1917]"
            )}
          >
            <FileCheck size={16} className={pathname.startsWith("/dashboard/templates") ? "text-[#5b21b6]" : "text-[#a8a29e] group-hover:text-[#78716c]"} />
            <span>Templates</span>
          </Link>
        )}

        {/* TOP LEVEL: Numbers Pool */}
        {role === "owner" && waEnabled && (
          <Link
            href="/dashboard/numbers"
            className={cn(
              "flex items-center gap-3 px-3 py-2 rounded-xl text-sm font-semibold transition-all duration-150 group",
              pathname.startsWith("/dashboard/numbers")
                ? "bg-[#f5f3ff] text-[#5b21b6]"
                : "text-[#78716c] hover:bg-[#f0ece4] hover:text-[#1c1917]"
            )}
          >
            <Layers size={16} className={pathname.startsWith("/dashboard/numbers") ? "text-[#5b21b6]" : "text-[#a8a29e] group-hover:text-[#78716c]"} />
            <span>Numbers Pool</span>
          </Link>
        )}

        {/* TOP LEVEL: Knowledge Base (Common for all platforms) */}
        {role === "owner" && (
          <Link
            href="/dashboard/knowledge"
            className={cn(
              "flex items-center gap-3 px-3 py-2 rounded-xl text-sm font-semibold transition-all duration-150 group",
              pathname.startsWith("/dashboard/knowledge")
                ? "bg-[#f5f3ff] text-[#5b21b6]"
                : "text-[#78716c] hover:bg-[#f0ece4] hover:text-[#1c1917]"
            )}
          >
            <BookOpen size={16} className={pathname.startsWith("/dashboard/knowledge") ? "text-[#5b21b6]" : "text-[#a8a29e] group-hover:text-[#78716c]"} />
            <span>Knowledge Base</span>
          </Link>
        )}

        {/* TOP LEVEL: Analytics */}
        {role === "owner" && (
          <Link
            href="/dashboard/analytics"
            className={cn(
              "flex items-center gap-3 px-3 py-2 rounded-xl text-sm font-semibold transition-all duration-150 group",
              pathname.startsWith("/dashboard/analytics")
                ? "bg-[#f5f3ff] text-[#5b21b6]"
                : "text-[#78716c] hover:bg-[#f0ece4] hover:text-[#1c1917]"
            )}
          >
            <BarChart2 size={16} className={pathname.startsWith("/dashboard/analytics") ? "text-[#5b21b6]" : "text-[#a8a29e] group-hover:text-[#78716c]"} />
            <span>Analytics</span>
          </Link>
        )}

        {/* TOP LEVEL: Team */}
        {role === "owner" && (
          <Link
            href="/dashboard/team"
            className={cn(
              "flex items-center gap-3 px-3 py-2 rounded-xl text-sm font-semibold transition-all duration-150 group",
              pathname.startsWith("/dashboard/team")
                ? "bg-[#f5f3ff] text-[#5b21b6]"
                : "text-[#78716c] hover:bg-[#f0ece4] hover:text-[#1c1917]"
            )}
          >
            <Users size={16} className={pathname.startsWith("/dashboard/team") ? "text-[#5b21b6]" : "text-[#a8a29e] group-hover:text-[#78716c]"} />
            <span>Team</span>
          </Link>
        )}

        <div className="mx-2 my-3 h-px bg-[#e8e3db]" />

        {/* TOP LEVEL: Channels */}
        {role === "owner" && (
          <Link
            href="/dashboard/channels"
            className={cn(
              "flex items-center gap-3 px-3 py-2 rounded-xl text-sm font-semibold transition-all duration-150 group",
              pathname.startsWith("/dashboard/channels")
                ? "bg-[#f5f3ff] text-[#5b21b6]"
                : "text-[#78716c] hover:bg-[#f0ece4] hover:text-[#1c1917]"
            )}
          >
            <MessageSquare size={16} className={pathname.startsWith("/dashboard/channels") ? "text-[#5b21b6]" : "text-[#a8a29e] group-hover:text-[#78716c]"} />
            <span>Channels</span>
          </Link>
        )}

        {/* GROUP: Telecalling */}
        {enabledFeatures.includes("telecalling") && tcGroupItems.length > 0 && (
          <div className="space-y-0.5">
            <button
              onClick={() => toggleGroup("Telecalling")}
              className={cn(
                "flex items-center gap-3 px-3 py-2 w-full rounded-xl text-sm font-semibold text-left transition-all group",
                isTcActive ? "text-[#1c1917]" : "text-[#78716c] hover:bg-[#f0ece4]"
              )}
            >
              <Phone size={16} className={isTcActive ? "text-[#5b21b6]" : "text-[#a8a29e] group-hover:text-[#78716c]"} />
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
                          isLast ? "top-0 h-4.5" : "-top-1 bottom-0"
                        )}
                      />
                      <div className="absolute left-3 top-1/2 -translate-y-1 w-3.5 h-3.5 border-l border-b border-[#d6cfc9] rounded-bl-lg" />

                      <Link
                        href={item.href}
                        className={cn(
                          "flex items-center gap-2.5 ml-3.5 px-3 py-1.5 w-[145px] rounded-xl text-[13px] transition-all duration-150 group",
                          active
                            ? "bg-white shadow-md border border-[#e8e3db] text-[#5b21b6] font-bold"
                            : "text-[#78716c] hover:text-[#1c1917] hover:bg-[#f0ece4]"
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

      {/* Footer Actions */}
      <div className="px-3 pb-4 space-y-1.5">
        <div className="mx-2 mb-2 h-px bg-[#e8e3db]" />

        {role === "owner" && (
          <Link
            href="/dashboard/settings"
            className={cn(
              "flex items-center gap-3 px-3 py-2 rounded-xl text-sm font-semibold transition-all duration-150 group",
              pathname.startsWith("/dashboard/settings")
                ? "bg-[#f5f3ff] text-[#5b21b6]"
                : "text-[#78716c] hover:bg-[#f0ece4] hover:text-[#1c1917]"
            )}
          >
            <Settings size={16} className={pathname.startsWith("/dashboard/settings") ? "text-[#5b21b6]" : "text-[#a8a29e] group-hover:text-[#78716c]"} />
            <span>Settings</span>
          </Link>
        )}

        {role !== "owner" && (
          <Link
            href="/dashboard/settings"
            className={cn(
              "flex items-center gap-3 px-3 py-2 rounded-xl text-sm font-semibold transition-all duration-150 group",
              pathname.startsWith("/dashboard/settings")
                ? "bg-[#f5f3ff] text-[#5b21b6]"
                : "text-[#78716c] hover:bg-[#f0ece4] hover:text-[#1c1917]"
            )}
          >
            <Settings size={16} className={pathname.startsWith("/dashboard/settings") ? "text-[#5b21b6]" : "text-[#a8a29e] group-hover:text-[#78716c]"} />
            <span>Account</span>
          </Link>
        )}

        {role === "owner" && (
          <div className="px-2 pt-1">
            <Link
              href="/dashboard/numbers?tab=activity"
              className="flex items-center gap-2.5 px-3 py-1.5 rounded-lg border border-emerald-300 bg-emerald-50 hover:bg-emerald-100/85 transition-colors cursor-pointer"
            >
              <span className="relative flex h-1.5 w-1.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-500"></span>
              </span>
              <span className="font-label text-emerald-700 font-bold tracking-wider" style={{ fontSize: "0.55rem" }}>
                ALL SYSTEMS ONLINE
              </span>
            </Link>
          </div>
        )}

      </div>
    </aside>
  );
}
