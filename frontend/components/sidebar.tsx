"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { useAuthRole } from "@/app/dashboard/contexts/AuthRoleContext";
import { API_URL, getAuthHeaders } from "@/lib/api";
import {
  LayoutDashboard, MessageSquare, Users, Phone,
  BarChart2, Upload, BookOpen, Layers, FileCheck, StickyNote, Package, ShoppingBag,
  ChevronDown, ChevronRight, ChevronLeft, RadioTower, Calendar, CreditCard, ShieldCheck, Megaphone, HandCoins,
  Settings,
} from "lucide-react";
import { cn } from "@/lib/utils";

import { createClient } from "@/lib/supabase/client";
import { AiraLogo } from "@/components/logo";
import { getVisibleSettingsItems, SETTINGS_GROUP_ORDER, SETTINGS_ITEMS } from "@/components/settingsNavigation";

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

function CollapsedNavItem({
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
  const router = useRouter();
  return (
    <div className="group relative" onMouseEnter={() => router.prefetch(href)}>
      <Link
        href={href}
        prefetch={true}
        className={cn(
          "flex items-center justify-center w-10 h-10 mx-auto rounded-xl transition-all duration-150 border relative",
          active
            ? "bg-white border-[#e2dcce] shadow-[0_1px_3px_rgba(0,0,0,0.05),0_1px_1px_rgba(0,0,0,0.02)]"
            : "border-transparent hover:bg-[#f0ece4]"
        )}
      >
        {active && (
          <span className="absolute -left-1.5 top-1/2 -translate-y-1/2 w-1 h-3 rounded-full bg-gradient-to-b from-[#3b0f79] via-[var(--primary-800)] to-[var(--primary-600)] flex-shrink-0 shadow-[0_1px_3px_rgba(var(--primary-800-rgb),0.25)]" />
        )}
        <Icon
          size={16}
          className={active ? "text-[var(--primary-800)] flex-shrink-0" : "text-[#1c1917] group-hover:text-[#1c1917] flex-shrink-0"}
        />
        {badge && (
          <span className="absolute -top-1 -right-1 flex items-center justify-center">
            {badge}
          </span>
        )}
      </Link>
      <div className="absolute left-full ml-2 top-1/2 -translate-y-1/2 px-2 py-1 rounded-md bg-[#1c1917] text-white text-xs whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-50">
        {label}
      </div>
    </div>
  );
}

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
  const router = useRouter();
  return (
    <Link
      href={href}
      prefetch={true}
      onMouseEnter={() => router.prefetch(href)}
      className={cn(
        "flex items-center gap-2.5 px-3 py-1.5 rounded-xl text-sm transition-all duration-150 border group",
        active
          ? "bg-white border-[#e2dcce] shadow-[0_1px_3px_rgba(0,0,0,0.05),0_1px_1px_rgba(0,0,0,0.02)] font-black"
          : "border-transparent text-[#1c1917] hover:bg-[#f0ece4] hover:text-[#1c1917]"
      )}
    >
      {active && (
        <span className="w-1 h-3.5 rounded-full bg-gradient-to-b from-[#3b0f79] via-[var(--primary-800)] to-[var(--primary-600)] -ml-0.5 mr-0.5 flex-shrink-0 shadow-[0_1px_3px_rgba(var(--primary-800-rgb),0.25)]" />
      )}
      <Icon
        size={16}
        className={active ? "text-[var(--primary-800)] flex-shrink-0" : "text-[#1c1917] group-hover:text-[#1c1917] flex-shrink-0"}
      />
      <span
        className={cn(
          "truncate flex-grow",
          active
            ? "bg-gradient-to-r from-[#3b0f79] via-[var(--primary-800)] to-[var(--primary-600)] bg-clip-text text-transparent font-black tracking-tight"
            : "font-medium"
        )}
      >
        {label}
      </span>
      {badge}
    </Link>
  );
}

interface SidebarProps {
  collapsed?: boolean;
}

export function Sidebar({ collapsed = false }: SidebarProps) {
  const pathname = usePathname();
  const router = useRouter();
  const { role, permissions, enabledFeatures, loading: roleLoading } = useAuthRole();
  const [inboxCount, setInboxCount] = useState(0);
  const [subStatus, setSubStatus] = useState<"loading" | "active" | "none" | "pending_approval">("loading");
  const [purchasedFeatures, setPurchasedFeatures] = useState<string[]>([]);

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
      <aside className={cn("fixed left-0 top-0 h-full bg-background border-r border-[#e8e3db] z-20", collapsed ? "w-16" : "w-[220px]")} />
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
  const visibleSettingsItems = getVisibleSettingsItems(purchasedFeatures);
  const canServices = canAny(["settings.view", "settings.manage", "catalog.view", "catalog.manage"]);
  const isSettingsActive = SETTINGS_ITEMS.some(item => pathname.startsWith(item.href));
  const showSettings = expandedGroups.Settings || isSettingsActive;

  return (
    <aside className={cn("fixed left-0 top-0 h-full bg-background border-r border-[#e8e3db] flex flex-col z-20 select-none", collapsed ? "w-16" : "w-[220px]")}>
      {/* Brand — h-16 (64px) matches the header so this bottom border and the
          header border form one continuous divider. shrink-0 is essential: the
          nav below overflows and would otherwise compress this box under flex
          pressure, lifting the divider above the header's fixed 64px line. */}
      <div className={cn("h-16 shrink-0 flex items-center border-b border-[#e8e3db]", collapsed ? "justify-center px-2" : "px-5")}>
        {collapsed ? (
          // Brand mark only: every page is already an icon in the rail below, so the
          // old "open menu" drawer was a second copy of the same navigation.
          // public/ assets are not basePath-prefixed, hence the hard-coded /aira.
          // eslint-disable-next-line @next/next/no-img-element
          <img src="/aira/icons/aira-icon.svg" alt="Aira" width={32} height={32} className="h-8 w-8" />
        ) : (
          <AiraLogo className="h-6 w-auto text-[#1c1917]" />
        )}
      </div>


      {collapsed ? (
        <div className="flex-grow overflow-y-auto flex flex-col items-center py-4 space-y-1.5 scrollbar-thin">
        {/* TOP LEVEL: Overview / Dashboard */}
        {can("dashboard.view") ? (
          <CollapsedNavItem
            href="/dashboard"
            active={pathname === "/dashboard"}
            icon={LayoutDashboard}
            label="Dashboard"
          />
        ) : (
          <CollapsedNavItem
            href="/dashboard/profile"
            active={pathname === "/dashboard/profile"}
            icon={LayoutDashboard}
            label="Overview"
          />
        )}

        {/* TOP LEVEL: Conversations */}
        {isSubscribed && messagingOn && canAny(["conversations.view", "conversations.reply"]) && (
          <CollapsedNavItem
            href="/dashboard/conversations"
            active={pathname.startsWith("/dashboard/conversations")}
            icon={MessageSquare}
            label="Conversations"
            badge={
              inboxCount > 0 ? (
                <span className="flex items-center justify-center w-4 h-4 rounded-full bg-orange-600 text-white text-[10px] font-bold min-w-[16px]">
                  {inboxCount > 9 ? "9+" : inboxCount}
                </span>
              ) : undefined
            }
          />
        )}

        {/* TOP LEVEL: Deals -- every sale attempt (chat, form, call, walk-in).
            No messagingOn gate: walk-ins and calls are deals too. */}
        {isSubscribed && can("leads.view") && (
          <CollapsedNavItem
            href="/dashboard/deals"
            active={pathname.startsWith("/dashboard/deals") || pathname.startsWith("/dashboard/intake")}
            icon={HandCoins}
            label="Deals"
          />
        )}

        {/* TOP LEVEL: Leads */}
        {isSubscribed && can("leads.view") && messagingOn && (
          <CollapsedNavItem
            href="/dashboard/leads"
            active={pathname.startsWith("/dashboard/leads")}
            icon={Users}
            label="Segments"
          />
        )}

        {/* TOP LEVEL: Inbound Leads */}
        {isSubscribed && can("inbound_leads.view") && inboundOn && (
          <CollapsedNavItem
            href="/dashboard/inbound-leads"
            active={pathname.startsWith("/dashboard/inbound-leads")}
            icon={RadioTower}
            label="Inbound Leads"
          />
        )}

        {/* TOP LEVEL: Meta Ads */}
        {isSubscribed && can("inbound_leads.view") && inboundOn && (
          <CollapsedNavItem
            href="/dashboard/meta-ads"
            active={pathname.startsWith("/dashboard/meta-ads")}
            icon={Megaphone}
            label="Meta Ads"
          />
        )}

        {/* TOP LEVEL: Outbound Leads */}
        {isSubscribed && canAny(["outbound_leads.view", "outbound_leads.manage"]) && outboundOn && (
          <CollapsedNavItem
            href="/dashboard/outbound-leads"
            active={pathname.startsWith("/dashboard/outbound-leads")}
            icon={Upload}
            label="Outbound Leads"
          />
        )}

        {/* TOP LEVEL: Templates */}
        {isSubscribed && canAny(["templates.view", "templates.manage"]) && outboundOn && (
          <CollapsedNavItem
            href="/dashboard/templates"
            active={pathname.startsWith("/dashboard/templates")}
            icon={FileCheck}
            label="Templates"
          />
        )}

        {/* TOP LEVEL: Numbers Pool */}
        {isSubscribed && canAny(["numbers.view", "numbers.manage"]) && messagingOn && (
          <CollapsedNavItem
            href="/dashboard/numbers"
            active={pathname.startsWith("/dashboard/numbers")}
            icon={Layers}
            label="Numbers Pool"
          />
        )}

        {/* TOP LEVEL: Knowledge Base */}
        {isSubscribed && canAny(["knowledge.view", "knowledge.manage"]) && messagingOn && (
          <CollapsedNavItem
            href="/dashboard/knowledge"
            active={pathname.startsWith("/dashboard/knowledge")}
            icon={BookOpen}
            label="Knowledge Base"
          />
        )}

        {/* TOP LEVEL: Products (route stays /dashboard/catalog) */}
        {isSubscribed && canAny(["catalog.view", "catalog.manage"]) && messagingOn && (
          <CollapsedNavItem
            href="/dashboard/catalog"
            active={pathname.startsWith("/dashboard/catalog")}
            icon={ShoppingBag}
            label="Products"
          />
        )}

        {/* TOP LEVEL: Services -- packages/prices sold in chat, next to Products */}
        {isSubscribed && canServices && messagingOn && (
          <CollapsedNavItem
            href="/dashboard/services"
            active={pathname.startsWith("/dashboard/services")}
            icon={Package}
            label="Services"
          />
        )}

        {/* TOP LEVEL: Analytics */}
        {isSubscribed && can("analytics.view") && messagingOn && (
          <CollapsedNavItem
            href="/dashboard/analytics"
            active={pathname.startsWith("/dashboard/analytics")}
            icon={BarChart2}
            label="Analytics"
          />
        )}

        {/* TOP LEVEL: Subscription */}
        {canAny(["subscription.view", "subscription.manage"]) && (
          <CollapsedNavItem
            href="/dashboard/subscription"
            active={pathname === "/dashboard/subscription"}
            icon={CreditCard}
            label="Subscription"
          />
        )}

        {/* TOP LEVEL: Team */}
        {isSubscribed && can("team.view") && (
          <CollapsedNavItem
            href="/dashboard/team"
            active={pathname.startsWith("/dashboard/team")}
            icon={Users}
            label="Team"
          />
        )}

        {/* TOP LEVEL: Roles */}
        {isSubscribed && canAny(["roles.view", "roles.manage"]) && (
          <CollapsedNavItem
            href="/dashboard/roles"
            active={pathname.startsWith("/dashboard/roles")}
            icon={ShieldCheck}
            label="Roles"
          />
        )}

        {/* GROUP: Telecalling */}
        {isSubscribed && telecallingOn && tcGroupItems.length > 0 && (
          <div className="group relative">
            <button
              // Groups open their first page: the collapsed rail has no drawer to expand.
              onClick={() => router.push(tcGroupItems[0].href)}
              className={cn(
                "flex items-center justify-center w-10 h-10 mx-auto rounded-xl transition-all group/tc border relative",
                isTcActive
                  ? "bg-white border-[#e2dcce] shadow-[0_1px_3px_rgba(0,0,0,0.05),0_1px_1px_rgba(0,0,0,0.02)]"
                  : "border-transparent hover:bg-[#f0ece4]"
              )}
              title="Telecalling"
            >
              {isTcActive && (
                <span className="absolute -left-1.5 top-1/2 -translate-y-1/2 w-1 h-3 rounded-full bg-gradient-to-b from-[#3b0f79] via-[var(--primary-800)] to-[var(--primary-600)] flex-shrink-0 shadow-[0_1px_3px_rgba(var(--primary-800-rgb),0.25)]" />
              )}
              <Phone
                size={16}
                className={isTcActive ? "text-[var(--primary-800)] flex-shrink-0" : "text-[#1c1917] group-hover/tc:text-[#1c1917] flex-shrink-0"}
              />
            </button>
            <div className="absolute left-full ml-2 top-1/2 -translate-y-1/2 px-2 py-1 rounded-md bg-[#1c1917] text-white text-xs whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-50">
              Telecalling
            </div>
          </div>
        )}

        {/* GROUP: Settings */}
        {isSubscribed && canSettings && (
          <div className="group relative">
            <button
              onClick={() => router.push(visibleSettingsItems[0]?.href ?? "/dashboard/settings/account")}
              className={cn(
                "flex items-center justify-center w-10 h-10 mx-auto rounded-xl transition-all group/settings border relative",
                isSettingsActive
                  ? "bg-white border-[#e2dcce] shadow-[0_1px_3px_rgba(0,0,0,0.05),0_1px_1px_rgba(0,0,0,0.02)]"
                  : "border-transparent hover:bg-[#f0ece4]"
              )}
              title="Settings"
            >
              {isSettingsActive && (
                <span className="absolute -left-1.5 top-1/2 -translate-y-1/2 w-1 h-3 rounded-full bg-gradient-to-b from-[#3b0f79] via-[var(--primary-800)] to-[var(--primary-600)] flex-shrink-0 shadow-[0_1px_3px_rgba(var(--primary-800-rgb),0.25)]" />
              )}
              <Settings
                size={16}
                className={isSettingsActive ? "text-[var(--primary-800)] flex-shrink-0" : "text-[#1c1917] group-hover/settings:text-[#1c1917] flex-shrink-0"}
              />
            </button>
            <div className="absolute left-full ml-2 top-1/2 -translate-y-1/2 px-2 py-1 rounded-md bg-[#1c1917] text-white text-xs whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-50">
              Settings
            </div>
          </div>
        )}
        </div>
      ) : (
        <>
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

              {SETTINGS_GROUP_ORDER.map((group) => {
                const groupItems = visibleSettingsItems.filter((i) => i.group === group);
                if (groupItems.length === 0) return null;
                return (
                  <div key={group} className="pt-2 first:pt-0">
                    <div className="px-3 pb-1 font-label text-[10px] font-bold uppercase tracking-wider text-[#a8a29e]">
                      {group}
                    </div>
                    {groupItems.map((item) => {
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
                          prefetch={true}
                          onMouseEnter={() => router.prefetch(item.href)}
                          className={cn(
                            "flex items-center px-3 py-1.5 rounded-xl text-sm transition-all duration-150 border",
                            active
                              ? "bg-white border-[#e2dcce] shadow-[0_1px_3px_rgba(0,0,0,0.05),0_1px_1px_rgba(0,0,0,0.02)] font-black"
                              : "border-transparent text-[#78716c] hover:text-[#1c1917] hover:bg-[#f0ece4]"
                          )}
                        >
                          {active && (
                            <span className="w-1 h-3.5 rounded-full bg-gradient-to-b from-[#3b0f79] via-[var(--primary-800)] to-[var(--primary-600)] mr-2 flex-shrink-0 shadow-[0_1px_3px_rgba(var(--primary-800-rgb),0.25)]" />
                          )}
                          <span
                            className={cn(
                              "truncate",
                              active
                                ? "bg-gradient-to-r from-[#3b0f79] via-[var(--primary-800)] to-[var(--primary-600)] bg-clip-text text-transparent font-black tracking-tight"
                                : "font-medium"
                            )}
                          >
                            {item.label}
                          </span>
                        </Link>
                      );
                    })}
                  </div>
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

        {/* TOP LEVEL: Deals -- every sale attempt (chat, form, call, walk-in).
            No messagingOn gate: walk-ins and calls are deals too. */}
        {isSubscribed && can("leads.view") && (
          <MainNavItem
            href="/dashboard/deals"
            active={pathname.startsWith("/dashboard/deals") || pathname.startsWith("/dashboard/intake")}
            icon={HandCoins}
            label="Deals"
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

        {/* TOP LEVEL: Products (route stays /dashboard/catalog) */}
        {isSubscribed && canAny(["catalog.view", "catalog.manage"]) && messagingOn && (
          <MainNavItem
            href="/dashboard/catalog"
            active={pathname.startsWith("/dashboard/catalog")}
            icon={ShoppingBag}
            label="Products"
          />
        )}

        {/* TOP LEVEL: Services -- packages/prices sold in chat, next to Products */}
        {isSubscribed && canServices && messagingOn && (
          <MainNavItem
            href="/dashboard/services"
            active={pathname.startsWith("/dashboard/services")}
            icon={Package}
            label="Services"
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
                isTcActive ? "text-[var(--primary-800)]" : "text-[#1c1917] hover:bg-[#f0ece4]"
              )}
            >
              <Phone size={16} className={isTcActive ? "text-[var(--primary-800)]" : "text-[#1c1917] group-hover:text-[#1c1917]"} />
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
                        prefetch={true}
                        onMouseEnter={() => router.prefetch(item.href)}
                        className={cn(
                          "flex items-center gap-2 ml-3.5 px-3 py-1.5 w-[145px] rounded-xl text-[13px] transition-all duration-150 group border",
                          active
                            ? "bg-white border-[#e2dcce] shadow-[0_1px_3px_rgba(0,0,0,0.05),0_1px_1px_rgba(0,0,0,0.02)] font-black"
                            : "border-transparent text-[#1c1917] hover:text-[#1c1917] hover:bg-[#f0ece4]"
                        )}
                      >
                        {active && (
                          <span className="w-1 h-3 rounded-full bg-gradient-to-b from-[#3b0f79] via-[var(--primary-800)] to-[var(--primary-600)] mr-1 flex-shrink-0 shadow-[0_1px_3px_rgba(var(--primary-800-rgb),0.25)]" />
                        )}
                        <span
                          className={cn(
                            "truncate flex-1",
                            active
                              ? "bg-gradient-to-r from-[#3b0f79] via-[var(--primary-800)] to-[var(--primary-600)] bg-clip-text text-transparent font-black tracking-tight"
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
                  isSettingsActive ? "text-[var(--primary-800)]" : "text-[#1c1917] hover:bg-[#f0ece4]"
                )}
              >
                <Settings size={16} className={isSettingsActive ? "text-[var(--primary-800)]" : "text-[#1c1917] group-hover:text-[#1c1917]"} />
                <span className="flex-1">Settings</span>
                <ChevronRight size={14} className="text-[#a8a29e]" />
              </button>
            )}
            </div>
          )}
        </>
      )}
    </aside>
  );
}
