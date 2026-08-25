"use client";
import { useCallback, useEffect, useState } from "react";
import { Package } from "lucide-react";
import { API_URL, getAuthHeaders } from "@/lib/api";
import { useSettingsForm } from "../SettingsFormContext";
import { SaveButton, SaveStatus, SectionFooter, SettingsSection } from "../SettingsSection";
import { PackageEditor, type IntakePackage } from "./PackageEditor";

export default function PackagesSettingsPage() {
  const { canManageSettings } = useSettingsForm();
  const [saved, setSaved] = useState<IntakePackage[]>([]);
  const [draft, setDraft] = useState<IntakePackage[]>([]);
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved">("idle");

  const load = useCallback(async () => {
    try {
      const auth = await getAuthHeaders();
      const res = await fetch(`${API_URL}/api/v1/settings/intake-config`, { headers: auth });
      if (res.ok) {
        const data = await res.json();
        setSaved(data.packages ?? []);
        setDraft(data.packages ?? []);
      }
    } catch {
      /* non-critical */
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const isDirty = JSON.stringify(draft) !== JSON.stringify(saved);

  async function handleSave() {
    if (!canManageSettings) return;
    setSaveState("saving");
    try {
      const auth = await getAuthHeaders();
      const res = await fetch(`${API_URL}/api/v1/settings/intake-config`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", ...auth },
        body: JSON.stringify({ packages: draft }),
      });
      if (!res.ok) throw new Error("Save failed");
      const data = await res.json();
      setSaved(data.packages ?? []);
      setDraft(data.packages ?? []);
      setSaveState("saved");
      setTimeout(() => setSaveState("idle"), 2000);
    } catch {
      setSaveState("idle");
    }
  }

  return (
    <div className="space-y-4">
      <SettingsSection
        id="intake-packages"
        icon={Package}
        accent="violet"
        title="Packages"
        description="The lead picks one of these right after accepting the offer, before any details are collected. A package can contain sub-options nested to any depth, and a leaf package can offer optional addons."
        status={{ label: `${draft.length} package${draft.length === 1 ? "" : "s"}`, tone: draft.length > 0 ? "on" : "off" }}
        dirty={isDirty}
      >
        <PackageEditor packages={draft} onChange={setDraft} canManage={canManageSettings} />

        <SectionFooter status={<SaveStatus state={saveState} dirty={isDirty} idleLabel={`${draft.length} package${draft.length === 1 ? "" : "s"} configured`} />}>
          <SaveButton state={saveState} dirty={isDirty} disabled={!canManageSettings} onClick={handleSave} />
        </SectionFooter>
      </SettingsSection>
    </div>
  );
}
