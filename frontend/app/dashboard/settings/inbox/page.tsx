"use client";
import { useSettingsForm } from "../SettingsFormContext";
import { InboxConfigPanel } from "../InboxConfigPanel";

export default function InboxSettingsPage() {
  const { canManageSettings } = useSettingsForm();
  return <InboxConfigPanel canManage={canManageSettings} />;
}
