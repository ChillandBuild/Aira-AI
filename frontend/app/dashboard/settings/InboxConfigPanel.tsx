"use client";
import { useEffect, useState, useCallback } from "react";
import { Inbox } from "lucide-react";
import { API_URL, getAuthHeaders } from "@/lib/api";
import { SaveButton, SaveStatus, SectionFooter, SettingsSection } from "./SettingsSection";

type InboxConfig = {
  enabled: boolean;
  auto_assign_enabled: boolean;
  channels: string[];
  triggers: string[];
};

const DEFAULT: InboxConfig = {
  enabled: false,
  auto_assign_enabled: false,
  channels: ["whatsapp", "instagram", "facebook", "telegram"],
  triggers: ["A", "B", "C", "F"],
};

const TRIGGER_LABELS: Record<string, { label: string; always?: boolean }> = {
  A: { label: "AI couldn't answer — sent a generic holding reply" },
  B: { label: "AI failed completely (technical error)" },
  C: { label: "User explicitly asked to speak to a person", always: true },
  D: { label: "User repeated the same question (AI not resolving it)" },
  F: { label: "AI response indicated the team would follow up" },
};

const CHANNEL_LABELS: Record<string, string> = {
  whatsapp: "WhatsApp",
  instagram: "Instagram",
  facebook: "Facebook",
  telegram: "Telegram",
};

function toggle<T>(arr: T[], item: T): T[] {
  return arr.includes(item) ? arr.filter((x) => x !== item) : [...arr, item];
}

export function InboxConfigPanel({ canManage = true }: { canManage?: boolean }) {
  const [config, setConfig] = useState<InboxConfig>(DEFAULT);
  const [draft, setDraft] = useState<InboxConfig>(DEFAULT);
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved">("idle");

  const load = useCallback(async () => {
    try {
      const auth = await getAuthHeaders();
      const res = await fetch(`${API_URL}/api/v1/settings/inbox-config`, { headers: auth });
      if (res.ok) {
        const data = await res.json();
        setConfig(data);
        setDraft(data);
      }
    } catch { /* non-critical */ }
  }, []);

  useEffect(() => { load(); }, [load]);

  const isDirty = JSON.stringify(draft) !== JSON.stringify(config);

  async function handleSave() {
    if (!canManage) return;
    setSaveState("saving");
    try {
      const auth = await getAuthHeaders();
      const res = await fetch(`${API_URL}/api/v1/settings/inbox-config`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", ...auth },
        body: JSON.stringify(draft),
      });
      if (!res.ok) throw new Error("Save failed");
      const saved = await res.json();
      setConfig(saved);
      setDraft(saved);
      setSaveState("saved");
      setTimeout(() => setSaveState("idle"), 2000);
    } catch {
      setSaveState("idle");
    }
  }

  return (
    <SettingsSection
      id="inbox-escalation"
      icon={Inbox}
      accent="violet"
      title="Inbox Escalation"
      description="Configure when AI escalates leads to the omnichannel inbox for human follow-up."
      status={{ label: draft.enabled ? "Enabled" : "Disabled", tone: draft.enabled ? "on" : "off" }}
      dirty={isDirty}
    >
      <div className="space-y-6">
        {/* Master toggles */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <label className="flex items-start gap-3 p-4 rounded-2xl border border-border bg-surface-subtle cursor-pointer hover:border-violet-300 transition-colors">
            <input
              type="checkbox"
              checked={draft.enabled}
              onChange={(e) => setDraft({ ...draft, enabled: e.target.checked })}
              className="mt-0.5 accent-violet-600"
            />
            <div>
              <div className="font-label text-sm font-semibold text-ink">Enable Inbox Escalation</div>
              <div className="font-body text-xs text-ink-muted mt-0.5">Master switch — off means no handovers are created automatically</div>
            </div>
          </label>

          <label className="flex items-start gap-3 p-4 rounded-2xl border border-border bg-surface-subtle cursor-pointer hover:border-violet-300 transition-colors">
            <input
              type="checkbox"
              checked={draft.auto_assign_enabled}
              onChange={(e) => setDraft({ ...draft, auto_assign_enabled: e.target.checked })}
              className="mt-0.5 accent-violet-600"
            />
            <div>
              <div className="font-label text-sm font-semibold text-ink">Auto-Assign (Round-Robin)</div>
              <div className="font-body text-xs text-ink-muted mt-0.5">Auto-assign escalated handovers to the active telecaller with fewest leads</div>
            </div>
          </label>
        </div>

        {/* Triggers */}
        <div>
          <div className="font-label text-sm font-semibold text-ink mb-2">Escalation Triggers</div>
          <div className="space-y-2">
            {Object.entries(TRIGGER_LABELS).map(([key, { label, always }]) => (
              <label
                key={key}
                className={`flex items-start gap-3 p-3 rounded-xl border transition-colors ${
                  always ? "border-amber-200 bg-amber-50 cursor-default" : "border-border bg-surface-subtle cursor-pointer hover:border-violet-300"
                }`}
              >
                <input
                  type="checkbox"
                  checked={always ? true : draft.triggers.includes(key)}
                  disabled={always}
                  onChange={() => !always && setDraft({ ...draft, triggers: toggle(draft.triggers, key) })}
                  className="mt-0.5 accent-violet-600"
                />
                <div>
                  <span className="font-body text-sm text-ink">{label}</span>
                  {always && <div className="text-xs text-amber-600 font-label mt-0.5">Always on — cannot be disabled (direct user request)</div>}
                </div>
              </label>
            ))}
          </div>
        </div>

        {/* Channels */}
        <div>
          <div className="font-label text-sm font-semibold text-ink mb-2">Channels</div>
          <div className="flex flex-wrap gap-2">
            {Object.entries(CHANNEL_LABELS).map(([ch, label]) => (
              <label key={ch} className="flex items-center gap-2 px-3 py-2 rounded-xl border border-border bg-surface-subtle cursor-pointer hover:border-violet-300 transition-colors">
                <input
                  type="checkbox"
                  checked={draft.channels.includes(ch)}
                  onChange={() => setDraft({ ...draft, channels: toggle(draft.channels, ch) })}
                  className="accent-violet-600"
                />
                <span className="font-label text-sm font-semibold text-ink">{label}</span>
              </label>
            ))}
          </div>
        </div>

      </div>

      <SectionFooter status={<SaveStatus state={saveState} dirty={isDirty} idleLabel={draft.enabled ? "Escalation is live" : "Escalation is off"} />}>
        <SaveButton state={saveState} dirty={isDirty} disabled={!canManage} onClick={handleSave} />
      </SectionFooter>
    </SettingsSection>
  );
}
