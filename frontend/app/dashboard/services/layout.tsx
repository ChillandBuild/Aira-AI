"use client";
import { SettingsFormProvider } from "../settings/SettingsFormContext";

// Services lives at the top level (next to Products), not under /settings, but
// it still needs the same tenant settings/business context (canManageSettings,
// etc.) that every settings page gets from this provider.
export default function ServicesLayout({ children }: { children: React.ReactNode }) {
  return <SettingsFormProvider>{children}</SettingsFormProvider>;
}
