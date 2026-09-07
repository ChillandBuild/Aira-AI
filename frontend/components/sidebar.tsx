"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { useAuthRole } from "@/app/dashboard/contexts/AuthRoleContext";
import { API_URL, getAuthHeaders } from "@/lib/api";
import {
  LayoutDashboard, MessageSquare, Users, Phone,
  BarChart2, Upload, BookOpen, Layers, FileCheck, StickyNote, Package,
  ChevronDown, ChevronRight, ChevronLeft, RadioTower, Calendar, CreditCard, ShieldCheck, Megaphone, Headset,
  Settings,
} from "lucide-react";
import { cn } from "@/lib/utils";

import { createClient } from "@/lib/supabase/client";
import { AiraLogo } from "@/components/logo";
import { getVisibleSettingsItems, SETTINGS_ITEMS, type CallingProvider } from "@/components/settingsNavigation";

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

function MainNavItem({
  href,
  active,
  icon: Icon,
  label,
  badge,
}: {
  href: string;
  active: boolean;
  icon: typeof LayoutDashboard;
  label: string;
  badge?: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      className={cn(
        "flex items-center gap-2.5 px-3 py-1.5 rounded-xl text-sm transition-all duration-150 border group",
        active
          ? "bg-white border-[#e2dcce] shadow-[0_1px_3px_rgba(0,0,0,0.05),0_1px_1px_rgba(0,0,0,0.02)] font-black"
          : "border-transparent text-[#1c1917] hover:bg-[#f0ece4] hover:text-[#1c1917]"
      )}
    >
      {active && (
        <span className="w-1 h-3.5 rounded-full bg-gradient-to-b from-[#3b0f79] via-[#5b21b6] to-[#7c3aed] -ml-0.5 mr-0.5 flex-shrink-0 shadow-[0_1px_3px_rgba(91,33,182,0.25)]" />
      )}
      <Icon
        size={16}
        className={active ? "text-[#5b21b6] flex-shrink-0" : "text-[#1c1917] group-hover:text-[#1c1917] flex-shrink-0"}
      />
      <span
        className={cn(
          "truncate flex-grow",
          active
            ? "bg-gradient-to-r from-[#3b0f79] via-[#5b21b6] to-[#7c3aed] bg-clip-text text-transparent font-black tracking-tight"
            : "font-medium"
        )}
      >
        {label}
      </span>
      {badge}
    </Link>
  );
}

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { role, permissions, enabledFeatures, loading: roleLoading } = useAuthRole();
  const [inboxCount, setInboxCount] = useState(0);
  const [subStatus, setSubStatus] = useState<"loading" | "active" | "none" | "pending_approval">("loading");
  const [purchasedFeatures, setPurchasedFeatures] = useState<string[]>([]);
  const [callingProvider, setCallingProvider] = useState<CallingProvider>(null);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const auth = await getAuthHeaders();
        const res = await fetch(`${API_URL}/api/v1/subscriptions/me`, { headers: auth });
        if (res.ok && active) {
          const data = await res.json();
          setSubStatus(data.status);
          setPurchasedFeatures((data.items ?? []).map((item: { feature_key: string }) => item.feature_key));
        } else if (active) {
          setSubStatus("active");
        }
      } catch {
        if (active) setSubStatus("active");
      }
    })();
    return () => { active = false; };
  }, []);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const auth = await getAuthHeaders();
        const res = await fetch(`${API_URL}/api/v1/settings/telecalling-config`, { headers: auth });
        if (!active) return;
        if (res.ok) {
          const data = await res.json();
          setCallingProvider((data.calling_provider as Exclude<CallingProvider, null> | undefined) ?? "telecmi");
        } else {
          setCallingProvider("telecmi");
        }
      } catch {
        if (active) setCallingProvider("telecmi");
      }
    })();
    return () => { active = false; };
  }, []);
  
  // Track open/collapsed state of nested groups
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>({
    Telecalling: true,
    Settings: false,
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
  const canSettings = canAny(["settings.view", "settings.manage"]);
  const visibleSettingsItems = getVisibleSettingsItems(purchasedFeatures, callingProvider);
  const isSettingsActive = SETTINGS_ITEMS.some(item => pathname.startsWith(item.href));
  const showSettings = expandedGroups.Settings || isSettingsActive;

  return (
    <aside className="fixed left-0 top-0 h-full w-[220px] bg-background border-r border-[#e8e3db] flex flex-col z-20 select-none">
      {/* Brand — h-16 (64px) matches the header so this bottom border and the
          header border form one continuous divider. shrink-0 is essential: the
          nav below overflows and would otherwise compress this box under flex
          pressure, lifting the divider above the header's fixed 64px line. */}
      <div className="h-16 shrink-0 flex items-center px-5 border-b border-[#e8e3db]">
        <AiraLogo className="h-6 w-auto text-[#1c1917]" />
      </div>


      {showSettings ? (
        <div className="flex-grow overflow-y-auto px-3 py-4 space-y-1 scrollbar-thin">
          <button
            onClick={() => {
              setExpandedGroups((prev) => ({ ...prev, Settings: false }));
              router.push("/dashboard");
            }}
            className="flex items-center gap-2 px-2 py-2 mb-2 w-full rounded-xl text-left text-sm font-bold text-[#1c1917] transition-all hover:bg-[#f0ece4]"
          >
            <ChevronLeft size={16} />
            <span>Settings</span>
          </button>

          {visibleSettingsItems.map((item) => {
            const matches = visibleSettingsItems.filter(
              (i) => pathname === i.href || pathname.startsWith(i.href + "/")
            );
            const bestMatch = matches.reduce<NavItem | null>(
              (best, i) => (!best || i.href.length > best.href.length ? i : best), null
            );
            const active = bestMatch?.href === item.href;

            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex items-center px-3 py-1.5 rounded-xl text-sm transition-all duration-150 border",
                  active
                    ? "bg-white border-[#e2dcce] shadow-[0_1px_3px_rgba(0,0,0,0.05),0_1px_1px_rgba(0,0,0,0.02)] font-black"
                    : "border-transparent text-[#78716c] hover:text-[#1c1917] hover:bg-[#f0ece4]"
                )}
              >
                {active && (
                  <span className="w-1 h-3.5 rounded-full bg-gradient-to-b from-[#3b0f79] via-[#5b21b6] to-[#7c3aed] mr-2 flex-shrink-0 shadow-[0_1px_3px_rgba(91,33,182,0.25)]" />
                )}
                <span
                  className={cn(
                    "truncate",
                    active
                      ? "bg-gradient-to-r from-[#3b0f79] via-[#5b21b6] to-[#7c3aed] bg-clip-text text-transparent font-black tracking-tight"
                      : "font-medium"
                  )}
                >
                  {item.label}
                </span>
              </Link>
            );
          })}
        </div>
      ) : (
      <div className="flex-grow overflow-y-auto px-3 py-4 space-y-1.5 scrollbar-thin">
        {/* TOP LEVEL: Overview / Dashboard */}
        {can("dashboard.view") ? (
          <MainNavItem
            href="/dashboard"
            active={pathname === "/dashboard"}
            icon={LayoutDashboard}
            label="Dashboard"
          />
        ) : (
          <MainNavItem
            href="/dashboard/profile"
            active={pathname === "/dashboard/profile"}
            icon={LayoutDashboard}
            label="Overview"
          />
        )}

        {/* TOP LEVEL: Conversations */}
        {isSubscribed && messagingOn && canAny(["conversations.view", "conversations.reply"]) && (
          <MainNavItem
            href="/dashboard/conversations"
            active={pathname.startsWith("/dashboard/conversations")}
            icon={MessageSquare}
            label="Conversations"
            badge={
              inboxCount > 0 ? (
                <span className="flex-shrink-0 px-1.5 py-0.5 rounded-full bg-orange-100 text-orange-600 font-bold text-[9px] min-w-[16px] text-center">
                  {inboxCount}
                </span>
              ) : undefined
            }
          />
        )}

        {/* TOP LEVEL: Intake */}
        {isSubscribed && messagingOn && canAny(["conversations.view", "conversations.reply"]) && (
          <MainNavItem
            href="/dashboard/intake"
            active={pathname.startsWith("/dashboard/intake")}
            icon={Headset}
            label="Intake"
          />
        )}

        {/* TOP LEVEL: Leads */}
        {isSubscribed && can("leads.view") && messagingOn && (
          <MainNavItem
            href="/dashboard/leads"
            active={pathname.startsWith("/dashboard/leads")}
            icon={Users}
            label="Segments"
          />
        )}

        {/* TOP LEVEL: Inbound Leads */}
        {isSubscribed && can("inbound_leads.view") && inboundOn && (
          <MainNavItem
            href="/dashboard/inbound-leads"
            active={pathname.startsWith("/dashboard/inbound-leads")}
            icon={RadioTower}
            label="Inbound Leads"
          />
        )}

        {/* TOP LEVEL: Meta Ads */}
        {isSubscribed && can("inbound_leads.view") && inboundOn && (
          <MainNavItem
            href="/dashboard/meta-ads"
            active={pathname.startsWith("/dashboard/meta-ads")}
            icon={Megaphone}
            label="Meta Ads"
          />
        )}

        {/* TOP LEVEL: Outbound Leads */}
        {isSubscribed && canAny(["outbound_leads.view", "outbound_leads.manage"]) && outboundOn && (
          <MainNavItem
            href="/dashboard/outbound-leads"
            active={pathname.startsWith("/dashboard/outbound-leads")}
            icon={Upload}
            label="Outbound Leads"
          />
        )}

        {/* TOP LEVEL: Templates */}
        {isSubscribed && canAny(["templates.view", "templates.manage"]) && outboundOn && (
          <MainNavItem
            href="/dashboard/templates"
            active={pathname.startsWith("/dashboard/templates")}
            icon={FileCheck}
            label="Templates"
          />
        )}

        {/* TOP LEVEL: Numbers Pool */}
        {isSubscribed && canAny(["numbers.view", "numbers.manage"]) && messagingOn && (
          <MainNavItem
            href="/dashboard/numbers"
            active={pathname.startsWith("/dashboard/numbers")}
            icon={Layers}
            label="Numbers Pool"
          />
        )}

        {/* TOP LEVEL: Knowledge Base */}
        {isSubscribed && canAny(["knowledge.view", "knowledge.manage"]) && messagingOn && (
          <MainNavItem
            href="/dashboard/knowledge"
            active={pathname.startsWith("/dashboard/knowledge")}
            icon={BookOpen}
            label="Knowledge Base"
          />
        )}

        {/* TOP LEVEL: Catalog */}
        {isSubscribed && canAny(["catalog.view", "catalog.manage"]) && messagingOn && (
          <MainNavItem
            href="/dashboard/catalog"
            active={pathname.startsWith("/dashboard/catalog")}
            icon={Package}
            label="Catalog"
          />
        )}

        {/* TOP LEVEL: Analytics */}
        {isSubscribed && can("analytics.view") && messagingOn && (
          <MainNavItem
            href="/dashboard/analytics"
            active={pathname.startsWith("/dashboard/analytics")}
            icon={BarChart2}
            label="Analytics"
          />
        )}

        {/* TOP LEVEL: Subscription */}
        {canAny(["subscription.view", "subscription.manage"]) && (
          <MainNavItem
            href="/dashboard/subscription"
            active={pathname === "/dashboard/subscription"}
            icon={CreditCard}
            label="Subscription"
          />
        )}

        {/* TOP LEVEL: Team */}
        {isSubscribed && can("team.view") && (
          <MainNavItem
            href="/dashboard/team"
            active={pathname.startsWith("/dashboard/team")}
            icon={Users}
            label="Team"
          />
        )}

        {/* TOP LEVEL: Roles */}
        {isSubscribed && canAny(["roles.view", "roles.manage"]) && (
          <MainNavItem
            href="/dashboard/roles"
            active={pathname.startsWith("/dashboard/roles")}
            icon={ShieldCheck}
            label="Roles"
          />
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
                          "flex items-center gap-2 ml-3.5 px-3 py-1.5 w-[145px] rounded-xl text-[13px] transition-all duration-150 group border",
                          active
                            ? "bg-white border-[#e2dcce] shadow-[0_1px_3px_rgba(0,0,0,0.05),0_1px_1px_rgba(0,0,0,0.02)] font-black"
                            : "border-transparent text-[#1c1917] hover:text-[#1c1917] hover:bg-[#f0ece4]"
                        )}
                      >
                        {active && (
                          <span className="w-1 h-3 rounded-full bg-gradient-to-b from-[#3b0f79] via-[#5b21b6] to-[#7c3aed] mr-1 flex-shrink-0 shadow-[0_1px_3px_rgba(91,33,182,0.25)]" />
                        )}
                        <span
                          className={cn(
                            "truncate flex-1",
                            active
                              ? "bg-gradient-to-r from-[#3b0f79] via-[#5b21b6] to-[#7c3aed] bg-clip-text text-transparent font-black tracking-tight"
                              : "font-medium"
                          )}
                        >
                          {item.label}
                        </span>
                      </Link>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* GROUP: Settings */}
        {isSubscribed && canSettings && (
          <button
            onClick={() => toggleGroup("Settings")}
            className={cn(
              "flex items-center gap-3 px-3 py-2 w-full rounded-xl text-sm font-semibold text-left transition-all group",
              isSettingsActive ? "text-[#5b21b6]" : "text-[#1c1917] hover:bg-[#f0ece4]"
            )}
          >
            <Settings size={16} className={isSettingsActive ? "text-[#5b21b6]" : "text-[#1c1917] group-hover:text-[#1c1917]"} />
            <span className="flex-1">Settings</span>
            <ChevronRight size={14} className="text-[#a8a29e]" />
          </button>
        )}
      </div>
      )}
    </aside>
  );
}
