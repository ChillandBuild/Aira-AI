"use client";
import { useSettingsForm } from "../SettingsFormContext";
import { NotificationConfigPanel } from "../NotificationConfigPanel";

export default function NotificationsSettingsPage() {
  const { canManageSettings } = useSettingsForm();
  return <NotificationConfigPanel canManage={canManageSettings} />;
}
