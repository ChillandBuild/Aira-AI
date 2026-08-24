"use client";
import { Timer } from "lucide-react";
import { useSettingsForm } from "../SettingsFormContext";
import { parseSilenceDelays } from "../parseSilenceDelays";
import { SaveButton, SaveStatus, SectionFooter, SettingsAccordion, SettingsSection, SwitchPill } from "../SettingsSection";

const SILENCE_NUDGE_KEYS = {
  enabled: "silence_nudge_enabled",
  delays: "silence_nudge_delays",
  cap: "silence_nudge_daily_cap",
  quietStart: "silence_nudge_quiet_start",
  quietEnd: "silence_nudge_quiet_end",
} as const;

const SILENCE_NUDGE_DEFAULTS: Record<string, string> = {
  [SILENCE_NUDGE_KEYS.enabled]: "false",
  [SILENCE_NUDGE_KEYS.delays]: "5",
  [SILENCE_NUDGE_KEYS.cap]: "1",
  [SILENCE_NUDGE_KEYS.quietStart]: "21:00",
  [SILENCE_NUDGE_KEYS.quietEnd]: "09:00",
};

export default function FollowUpsSettingsPage() {
  const { settingFor, drafts, setDrafts, saveStates, canManageSettings, handleSave } = useSettingsForm();

  const stored = (key: string) => {
    const s = settingFor(key)?.display_value;
    return !s || s === "Not set" ? SILENCE_NUDGE_DEFAULTS[key] : s;
  };
  const value = (key: string) => drafts[key] ?? stored(key);
  const enabled = value(SILENCE_NUDGE_KEYS.enabled) === "true";
  const dirty = Object.values(SILENCE_NUDGE_KEYS).some(key => drafts[key] !== undefined && drafts[key] !== stored(key));
  const delaysValid = parseSilenceDelays(value(SILENCE_NUDGE_KEYS.delays)) !== null;
  const capValid = (() => {
    const raw = value(SILENCE_NUDGE_KEYS.cap);
    if (!/^\d+$/.test(raw)) return false;
    const n = parseInt(raw, 10);
    return n >= 1 && n <= 10;
  })();

  return (
    <SettingsAccordion>
      <SettingsSection
        id="silence-nudge"
        icon={Timer}
        accent="emerald"
        title="Auto follow-up when a lead goes quiet"
        description="After the AI answers, if the lead stays silent, send one short message about what they were discussing. Never sent while your team has taken over the chat, or during a paid consultation."
        status={{ label: enabled ? "On" : "Off", tone: enabled ? "on" : "off" }}
        dirty={dirty}
      >
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-border-subtle bg-surface-subtle p-4">
          <div className="min-w-0">
            <p className="font-body text-sm font-semibold text-ink">Send a quiet-lead follow-up</p>
            <p className="mt-0.5 font-body text-xs text-ink-muted">
              One short nudge per lead, on the topic they were already asking about.
            </p>
          </div>
          <SwitchPill
            on={enabled}
            disabled={!canManageSettings}
            onChange={(next) => setDrafts(d => ({ ...d, [SILENCE_NUDGE_KEYS.enabled]: next ? "true" : "false" }))}
          />
        </div>

        {enabled && (
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <label className="block">
              <span className="font-label text-[11px] font-bold uppercase tracking-wider text-ink-muted">Wait time (minutes)</span>
              <input
                type="text"
                inputMode="numeric"
                disabled={!canManageSettings}
                value={value(SILENCE_NUDGE_KEYS.delays)}
                onChange={e => setDrafts(d => ({ ...d, [SILENCE_NUDGE_KEYS.delays]: e.target.value }))}
                className={`mt-1.5 w-full rounded-xl border bg-white px-3 py-2 font-body text-sm text-ink transition focus:outline-none focus:ring-2 focus:ring-primary/15 disabled:opacity-60 ${
                  delaysValid ? "border-border focus:border-primary" : "border-red-400 focus:ring-red-200"
                }`}
              />
              <span className={`mt-1 block font-body text-[11px] ${delaysValid ? "text-ink-muted" : "text-red-600"}`}>
                {delaysValid ? "5 sends one message after 5 minutes. 5,60 adds a second an hour later." : "Up to 3 whole numbers, 1–1440, increasing. e.g. 5 or 5,60"}
              </span>
            </label>

            <label className="block">
              <span className="font-label text-[11px] font-bold uppercase tracking-wider text-ink-muted">Daily limit per lead</span>
              <input
                type="number"
                min={1}
                max={10}
                disabled={!canManageSettings}
                value={value(SILENCE_NUDGE_KEYS.cap)}
                onChange={e => setDrafts(d => ({ ...d, [SILENCE_NUDGE_KEYS.cap]: e.target.value }))}
                className={`mt-1.5 w-full rounded-xl border bg-white px-3 py-2 font-body text-sm text-ink transition focus:outline-none focus:ring-2 focus:ring-primary/15 disabled:opacity-60 ${
                  capValid ? "border-border focus:border-primary" : "border-red-400 focus:ring-red-200"
                }`}
              />
              <span className={`mt-1 block font-body text-[11px] ${capValid ? "text-ink-muted" : "text-red-600"}`}>
                {capValid ? "Most follow-ups one lead can get in 24 hours." : "Must be a whole number between 1 and 10."}
              </span>
            </label>

            <label className="block">
              <span className="font-label text-[11px] font-bold uppercase tracking-wider text-ink-muted">Quiet hours start (IST)</span>
              <input
                type="time"
                disabled={!canManageSettings}
                value={value(SILENCE_NUDGE_KEYS.quietStart)}
                onChange={e => setDrafts(d => ({ ...d, [SILENCE_NUDGE_KEYS.quietStart]: e.target.value }))}
                className="mt-1.5 w-full rounded-xl border border-border bg-white px-3 py-2 font-body text-sm text-ink transition focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/15 disabled:opacity-60"
              />
              <span className="mt-1 block font-body text-[11px] text-ink-muted">
                The first follow-up always sends — quiet hours only delay later ones.
              </span>
            </label>

            <label className="block">
              <span className="font-label text-[11px] font-bold uppercase tracking-wider text-ink-muted">Quiet hours end (IST)</span>
              <input
                type="time"
                disabled={!canManageSettings}
                value={value(SILENCE_NUDGE_KEYS.quietEnd)}
                onChange={e => setDrafts(d => ({ ...d, [SILENCE_NUDGE_KEYS.quietEnd]: e.target.value }))}
                className="mt-1.5 w-full rounded-xl border border-border bg-white px-3 py-2 font-body text-sm text-ink transition focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/15 disabled:opacity-60"
              />
              <span className="mt-1 block font-body text-[11px] text-ink-muted">
                The first follow-up always sends — quiet hours only delay later ones.
              </span>
            </label>
          </div>
        )}

        <SectionFooter
          status={<SaveStatus state={saveStates.automations_silence ?? "idle"} dirty={dirty} idleLabel={enabled ? "Quiet-lead follow-ups are enabled" : "Quiet-lead follow-ups are off"} />}
        >
          <SaveButton
            state={saveStates.automations_silence ?? "idle"}
            dirty={dirty && delaysValid && capValid}
            disabled={!canManageSettings}
            onClick={() => handleSave("automations_silence", Object.values(SILENCE_NUDGE_KEYS))}
          />
        </SectionFooter>
      </SettingsSection>
    </SettingsAccordion>
  );
}
