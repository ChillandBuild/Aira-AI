"use client";
import { useEffect, useState, useCallback } from "react";
import { Clock } from "lucide-react";
import { API_URL, getAuthHeaders } from "@/lib/api";
import { SaveButton, SaveStatus, SectionFooter, SettingsSection } from "./SettingsSection";

type BusinessHours = {
  enabled: boolean;
  timezone: string;
  open_time: string;
  close_time: string;
  working_days: number[];
};

const DEFAULT: BusinessHours = {
  enabled: true,
  timezone: "Asia/Kolkata",
  open_time: "09:00",
  close_time: "19:00",
  working_days: [1, 2, 3, 4, 5, 6],
};

const DAYS: { value: number; label: string }[] = [
  { value: 1, label: "Mon" },
  { value: 2, label: "Tue" },
  { value: 3, label: "Wed" },
  { value: 4, label: "Thu" },
  { value: 5, label: "Fri" },
  { value: 6, label: "Sat" },
  { value: 7, label: "Sun" },
];

const TIMEZONES = ["Asia/Kolkata", "Asia/Dubai", "Asia/Singapore", "Europe/London", "UTC"];

export function BusinessHoursPanel({ canManage = true }: { canManage?: boolean }) {
  const [config, setConfig] = useState<BusinessHours>(DEFAULT);
  const [draft, setDraft] = useState<BusinessHours>(DEFAULT);
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved">("idle");

  const load = useCallback(async () => {
    try {
      const auth = await getAuthHeaders();
      const res = await fetch(`${API_URL}/api/v1/settings/business-hours`, { headers: auth });
      if (res.ok) {
        const data = await res.json();
        setConfig(data);
        setDraft(data);
      }
    } catch {
      /* non-critical */
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const isDirty = JSON.stringify(draft) !== JSON.stringify(config);

  async function handleSave() {
    if (!canManage) return;
    setSaveState("saving");
    try {
      const auth = await getAuthHeaders();
      const res = await fetch(`${API_URL}/api/v1/settings/business-hours`, {
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

  function toggleDay(day: number) {
    setDraft({
      ...draft,
      working_days: draft.working_days.includes(day)
        ? draft.working_days.filter((d) => d !== day)
        : [...draft.working_days, day].sort((a, b) => a - b),
    });
  }

  const dayLabel = draft.working_days.length === 7
    ? "Every day"
    : draft.working_days.length === 0
    ? "No working days"
    : DAYS.filter((d) => draft.working_days.includes(d.value)).map((d) => d.label).join(", ");

  return (
    <SettingsSection
      id="business-hours"
      icon={Clock}
      accent="sky"
      title="Business Hours"
      description="When your team is reachable. The AI uses this to tell escalated customers when to expect a call."
      status={
        draft.enabled
          ? { label: `${draft.open_time}-${draft.close_time}`, tone: "on" }
          : { label: "Always closed", tone: "off" }
      }
      dirty={isDirty}
    >
      <div className="space-y-5">
        <label className="flex items-start gap-3 p-4 rounded-2xl border border-border bg-surface-subtle cursor-pointer hover:border-violet-300 transition-colors">
          <input
            type="checkbox"
            checked={draft.enabled}
            disabled={!canManage}
            onChange={(e) => setDraft({ ...draft, enabled: e.target.checked })}
            className="mt-0.5 accent-violet-600"
          />
          <div>
            <div className="font-label text-sm font-semibold text-ink">Enable business hours</div>
            <div className="font-body text-xs text-ink-muted mt-0.5">
              When off, the AI always treats the office as closed.
            </div>
          </div>
        </label>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div>
            <label className="font-label text-[11px] font-bold uppercase tracking-wider text-ink-muted mb-2 block">
              Opens
            </label>
            <input
              type="time"
              value={draft.open_time}
              disabled={!canManage}
              onChange={(e) => setDraft({ ...draft, open_time: e.target.value })}
              className="w-full px-3 py-2 rounded-xl bg-white border border-border text-sm font-mono text-ink focus:outline-none focus:border-primary"
            />
          </div>
          <div>
            <label className="font-label text-[11px] font-bold uppercase tracking-wider text-ink-muted mb-2 block">
              Closes
            </label>
            <input
              type="time"
              value={draft.close_time}
              disabled={!canManage}
              onChange={(e) => setDraft({ ...draft, close_time: e.target.value })}
              className="w-full px-3 py-2 rounded-xl bg-white border border-border text-sm font-mono text-ink focus:outline-none focus:border-primary"
            />
          </div>
          <div>
            <label className="font-label text-[11px] font-bold uppercase tracking-wider text-ink-muted mb-2 block">
              Timezone
            </label>
            <select
              value={draft.timezone}
              disabled={!canManage}
              onChange={(e) => setDraft({ ...draft, timezone: e.target.value })}
              className="w-full px-3 py-2 rounded-xl bg-white border border-border text-sm text-ink focus:outline-none focus:border-primary"
            >
              {TIMEZONES.map((tz) => (
                <option key={tz} value={tz}>
                  {tz}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div>
          <div className="font-label text-sm font-semibold text-ink mb-2">Working days</div>
          <div className="flex flex-wrap gap-2">
            {DAYS.map(({ value, label }) => {
              const active = draft.working_days.includes(value);
              return (
                <button
                  key={value}
                  type="button"
                  aria-pressed={active}
                  disabled={!canManage}
                  onClick={() => toggleDay(value)}
                  className={`px-3 py-1.5 rounded-full font-label text-xs font-semibold border transition-colors ${
                    active
                      ? "bg-primary text-white border-primary"
                      : "bg-white text-ink-muted border-border hover:border-violet-300"
                  }`}
                >
                  {label}
                </button>
              );
            })}
          </div>
          {draft.working_days.length === 0 && (
            <p className="font-body text-[11px] text-amber-600 mt-2">
              No working days selected — the AI will always treat the office as closed.
            </p>
          )}
        </div>

      </div>

      <SectionFooter
        status={<SaveStatus state={saveState} dirty={isDirty} idleLabel={draft.enabled ? dayLabel : "Business hours are off"} />}
      >
        <SaveButton state={saveState} dirty={isDirty} disabled={!canManage} onClick={handleSave} />
      </SectionFooter>
    </SettingsSection>
  );
}
