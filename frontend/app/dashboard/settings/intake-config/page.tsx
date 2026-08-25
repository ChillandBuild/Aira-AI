"use client";
import { useSettingsForm } from "../SettingsFormContext";
import { IntakeConfigPanel } from "../IntakeConfigPanel";

export default function IntakeConfigSettingsPage() {
  const { canManageSettings } = useSettingsForm();
  return <IntakeConfigPanel canManage={canManageSettings} />;
}
