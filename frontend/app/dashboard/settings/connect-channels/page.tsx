"use client";
import { useSettingsForm } from "../SettingsFormContext";
import { CallingCredentialsSection } from "../CallingCredentialsSection";
import ConnectChannelsPanel from "./Panel";

export default function ConnectChannelsSettingsPage() {
  const { canManageSettings, hasTelecmiConfig } = useSettingsForm();
  return (
    <div className="space-y-6">
      <ConnectChannelsPanel canManage={canManageSettings} />
      {/* TeleCMI credentials live here, not as a separate settings page —
          only shown once the calling provider is confirmed as TeleCMI. */}
      {hasTelecmiConfig && (
        <div id="calling">
          <CallingCredentialsSection />
        </div>
      )}
    </div>
  );
}
