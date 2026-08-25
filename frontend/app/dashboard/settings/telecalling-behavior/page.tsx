"use client";
import { useSettingsForm } from "../SettingsFormContext";
import { TelecallingConfigPanel } from "../TelecallingConfigPanel";

export default function TelecallingBehaviorSettingsPage() {
  const { canManageSettings } = useSettingsForm();
  return <TelecallingConfigPanel canManage={canManageSettings} />;
}
