"use client";
import { useSettingsForm } from "../SettingsFormContext";
import { BusinessHoursPanel } from "../BusinessHoursPanel";

export default function BusinessHoursSettingsPage() {
  const { canManageSettings } = useSettingsForm();
  return <BusinessHoursPanel canManage={canManageSettings} />;
}
