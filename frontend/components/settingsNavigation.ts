import {
  Calendar,
  Headset,
  Megaphone,
  MessageSquare,
  RadioTower,
  Reply,
  Sparkles,
  UserCircle,
} from "lucide-react";

export type SettingsGroup = "Account" | "Channels" | "Aira" | "Calling" | "Alerts";

export type SettingsNavItem = {
  href: string;
  icon: typeof UserCircle;
  label: string;
  group: SettingsGroup;
  entitlement?: "notifications";
};

// Order here is the order groups and items render in the sidebar and the
// mobile "More" menu — see sidebar.tsx / MoreMenu.tsx.
export const SETTINGS_ITEMS: SettingsNavItem[] = [
  { href: "/dashboard/settings/account", icon: UserCircle, label: "Profile & Business", group: "Account" },
  { href: "/dashboard/settings/connect-channels", icon: RadioTower, label: "Connect Channels", group: "Channels" },
  { href: "/dashboard/settings/auto-reply", icon: Sparkles, label: "Auto-Reply", group: "Aira" },
  { href: "/dashboard/settings/quick-replies", icon: Reply, label: "Quick Replies", group: "Aira" },
  { href: "/dashboard/settings/follow-ups", icon: Calendar, label: "Follow-Ups", group: "Aira" },
  { href: "/dashboard/settings/inbox", icon: MessageSquare, label: "Inbox & Handover", group: "Aira" },
  { href: "/dashboard/settings/telecalling-behavior", icon: Headset, label: "Telecalling Behavior", group: "Calling" },
  { href: "/dashboard/settings/notifications", icon: Megaphone, label: "Notifications", group: "Alerts", entitlement: "notifications" },
];

export function hasNotificationSettings(purchasedFeatures: string[]): boolean {
  return purchasedFeatures.length === 0
    || purchasedFeatures.includes("inbound_messaging")
    || purchasedFeatures.includes("outbound_messaging");
}

export function getVisibleSettingsItems(purchasedFeatures: string[]): SettingsNavItem[] {
  const showNotifications = hasNotificationSettings(purchasedFeatures);

  return SETTINGS_ITEMS.filter((item) => {
    if (item.entitlement === "notifications") return showNotifications;
    return true;
  });
}

/** Groups, in display order, for rendering group headings above their items. */
export const SETTINGS_GROUP_ORDER: SettingsGroup[] = ["Account", "Channels", "Aira", "Calling", "Alerts"];
