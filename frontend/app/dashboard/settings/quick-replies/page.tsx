"use client";
import { useSettingsForm } from "../SettingsFormContext";
import { QuickRepliesPanel } from "../QuickRepliesPanel";

export default function QuickRepliesSettingsPage() {
  const { canManageSettings } = useSettingsForm();
  return <QuickRepliesPanel canManage={canManageSettings} />;
}
