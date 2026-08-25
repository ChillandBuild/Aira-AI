"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useSettingsForm } from "../SettingsFormContext";
import { NotificationConfigPanel } from "../NotificationConfigPanel";

export default function NotificationsSettingsPage() {
  const router = useRouter();
  const { canManageSettings, hasNotifications } = useSettingsForm();

  useEffect(() => {
    if (!hasNotifications) router.replace("/dashboard/settings/general", { scroll: false });
  }, [hasNotifications, router]);

  if (!hasNotifications) return null;
  return <NotificationConfigPanel canManage={canManageSettings} />;
}
