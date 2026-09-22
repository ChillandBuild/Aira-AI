"use client";
import { Plus, Timer, X } from "lucide-react";
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

const MAX_REMINDERS = 3;

const isValidMinutes = (s: string) => /^\d+$/.test(s) && +s >= 1 && +s <= 1440;

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
  const capNum = parseInt(value(SILENCE_NUDGE_KEYS.cap), 10);
  const capValid = /^\d+$/.test(value(SILENCE_NUDGE_KEYS.cap)) && capNum >= 1 && capNum <= 10;

  // Stored as "5,60"; edited as one row per reminder. Blank rows are kept (not
  // filtered) so a half-typed row stays on screen and blocks save.
  const reminders = value(SILENCE_NUDGE_KEYS.delays).split(",").map(s => s.trim());
  const setReminders = (next: string[]) =>
    setDrafts(d => ({ ...d, [SILENCE_NUDGE_KEYS.delays]: next.join(",") }));
  const setReminder = (i: number, mins: string) => setReminders(reminders.map((m, j) => (j === i ? mins : m)));
  const removeReminder = (i: number) => setReminders(reminders.filter((_, j) => j !== i));
  const addReminder = () => setReminders([...reminders, "60"]);

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
            <div className="sm:col-span-2">
              <span className="font-label text-[11px] font-bold uppercase tracking-wider text-ink-muted">Reminders</span>
              <ol className="mt-1.5 space-y-2">
                {reminders.map((mins, i) => {
                  const rowValid = isValidMinutes(mins);
                  return (
                    <li key={i} className="flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded-xl border border-border-subtle bg-white px-3 py-2.5">
                      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-emerald-50 font-label text-[11px] font-bold text-emerald-700">
                        {i + 1}
                      </span>
                      <span className="font-body text-sm text-ink">Send</span>
                      <input
                        type="text"
                        inputMode="numeric"
                        aria-label={`Minutes before reminder ${i + 1}`}
                        disabled={!canManageSettings}
                        value={mins}
                        onChange={e => setReminder(i, e.target.value.replace(/\D/g, ""))}
                        className={`w-16 rounded-lg border bg-white px-2 py-1 text-center font-body text-sm text-ink transition focus:outline-none focus:ring-2 focus:ring-primary/15 disabled:opacity-60 ${
                          rowValid ? "border-border focus:border-primary" : "border-red-400 focus:ring-red-200"
                        }`}
                      />
                      <span className="min-w-0 flex-1 font-body text-sm text-ink">
                        minutes after {i === 0 ? "the AI's reply" : `reminder ${i}`}
                      </span>
                      {reminders.length > 1 && canManageSettings && (
                        <button
                          type="button"
                          onClick={() => removeReminder(i)}
                          aria-label={`Remove reminder ${i + 1}`}
                          className="rounded-lg p-1 text-ink-muted transition hover:bg-surface-subtle hover:text-red-600"
                        >
                          <X className="h-4 w-4" />
                        </button>
                      )}
                      {!rowValid && (
                        <span className="basis-full font-body text-[11px] text-red-600">Enter a whole number from 1 to 1440 (24 hours).</span>
                      )}
                    </li>
                  );
                })}
              </ol>
              {reminders.length < MAX_REMINDERS && canManageSettings && (
                <button
                  type="button"
                  onClick={addReminder}
                  className="mt-2 inline-flex items-center gap-1.5 rounded-lg px-2 py-1 font-body text-xs font-semibold text-primary transition hover:bg-primary/5"
                >
                  <Plus className="h-3.5 w-3.5" /> Add another reminder
                </button>
              )}
              <p className="mt-1.5 font-body text-[11px] text-ink-muted">
                Each reminder only goes out if the lead still hasn&apos;t replied. If they reply, the rest are cancelled. Up to {MAX_REMINDERS}.
              </p>
              {capValid && reminders.length > capNum && (
                <p className="mt-1 font-body text-[11px] text-amber-700">
                  Your daily limit is {capNum}, so only {capNum} of these {reminders.length} reminders can go out to a lead in 24 hours.
                </p>
              )}
            </div>

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
