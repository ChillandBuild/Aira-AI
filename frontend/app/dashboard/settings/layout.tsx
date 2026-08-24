"use client";
import { SettingsFormProvider } from "./SettingsFormContext";

export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  return <SettingsFormProvider>{children}</SettingsFormProvider>;
}
