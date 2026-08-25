import {
  Calendar,
  FileCheck,
  Headset,
  Megaphone,
  MessageSquare,
  Package,
  Phone,
  RadioTower,
  Reply,
  Sparkles,
  Users,
} from "lucide-react";

export type CallingProvider = "telecmi" | "sim_basic" | null;

export type SettingsNavItem = {
  href: string;
  icon: typeof Users;
  label: string;
  entitlement?: "notifications" | "telecmi";
};

export const SETTINGS_ITEMS: SettingsNavItem[] = [
  { href: "/dashboard/settings/general", icon: Users, label: "General" },
  { href: "/dashboard/settings/connect-channels", icon: RadioTower, label: "Connect Channels" },
  { href: "/dashboard/settings/telecalling", icon: Phone, label: "Telecalling Credentials", entitlement: "telecmi" },
  { href: "/dashboard/settings/auto-reply", icon: Sparkles, label: "Auto-Reply" },
  { href: "/dashboard/settings/follow-ups", icon: Calendar, label: "Follow-Ups" },
  { href: "/dashboard/settings/inbox", icon: MessageSquare, label: "Inbox" },
  { href: "/dashboard/settings/telecalling-behavior", icon: Headset, label: "Telecalling Behavior" },
  { href: "/dashboard/settings/intake-config", icon: FileCheck, label: "Intake Config" },
  { href: "/dashboard/settings/packages", icon: Package, label: "Packages" },
  { href: "/dashboard/settings/business-hours", icon: Calendar, label: "Business Hours", entitlement: "notifications" },
  { href: "/dashboard/settings/notifications", icon: Megaphone, label: "Notifications", entitlement: "notifications" },
  { href: "/dashboard/settings/quick-replies", icon: Reply, label: "Quick Replies" },
];

export function hasNotificationSettings(purchasedFeatures: string[]): boolean {
  return purchasedFeatures.length === 0
    || purchasedFeatures.includes("inbound_messaging")
    || purchasedFeatures.includes("outbound_messaging");
}

export function getVisibleSettingsItems(
  purchasedFeatures: string[],
  callingProvider: CallingProvider,
): SettingsNavItem[] {
  const showNotifications = hasNotificationSettings(purchasedFeatures);

  return SETTINGS_ITEMS.filter((item) => {
    if (item.entitlement === "notifications") return showNotifications;
    if (item.entitlement === "telecmi") return callingProvider === "telecmi";
    return true;
  });
}
