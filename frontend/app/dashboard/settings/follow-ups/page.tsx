"use client";

import { useMemo } from "react";
import {
  ArrowRight,
  Bell,
  Clock,
  Minus,
  Moon,
  Plus,
  Shield,
  Timer,
  X,
  Zap,
} from "lucide-react";
import { useSettingsForm } from "../SettingsFormContext";
import { parseSilenceDelays } from "../parseSilenceDelays";
import {
  SaveButton,
  SaveStatus,
  SectionFooter,
  SettingsAccordion,
  SettingsSection,
  SwitchPill,
} from "../SettingsSection";

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

const DURATION_PRESETS = [
  { label: "5m", mins: "5" },
  { label: "15m", mins: "15" },
  { label: "30m", mins: "30" },
  { label: "1h", mins: "60" },
  { label: "2h", mins: "120" },
  { label: "24h", mins: "1440" },
];

const CAP_PRESETS = ["1", "2", "3", "5"];

function formatDuration(minsStr: string): string {
  const mins = parseInt(minsStr, 10);
  if (isNaN(mins) || mins <= 0) return "";
  if (mins < 60) return `${mins} min${mins > 1 ? "s" : ""}`;
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  if (m === 0) return `${h} hr${h > 1 ? "s" : ""}`;
  return `${h}h ${m}m`;
}

function formatTime12h(timeStr: string): string {
  if (!timeStr || !timeStr.includes(":")) return timeStr || "--:--";
  const [hStr, mStr] = timeStr.split(":");
  let h = parseInt(hStr, 10);
  const m = mStr || "00";
  if (isNaN(h)) return timeStr;
  const ampm = h >= 12 ? "PM" : "AM";
  h = h % 12 || 12;
  return `${h}:${m.padStart(2, "0")} ${ampm}`;
}

export default function FollowUpsSettingsPage() {
  const { settingFor, drafts, setDrafts, saveStates, canManageSettings, handleSave } =
    useSettingsForm();

  const stored = (key: string) => {
    const s = settingFor(key)?.display_value;
    return !s || s === "Not set" ? SILENCE_NUDGE_DEFAULTS[key] : s;
  };
  const value = (key: string) => drafts[key] ?? stored(key);
  const enabled = value(SILENCE_NUDGE_KEYS.enabled) === "true";
  const dirty = Object.values(SILENCE_NUDGE_KEYS).some(
    (key) => drafts[key] !== undefined && drafts[key] !== stored(key)
  );
  const delaysValid = parseSilenceDelays(value(SILENCE_NUDGE_KEYS.delays)) !== null;
  const capNum = parseInt(value(SILENCE_NUDGE_KEYS.cap), 10);
  const capValid =
    /^\d+$/.test(value(SILENCE_NUDGE_KEYS.cap)) && capNum >= 1 && capNum <= 10;

  // Stored as "5,60"; edited as one item per reminder. Blank entries stay on screen to block save.
  const rawDelays = value(SILENCE_NUDGE_KEYS.delays);
  const reminders = useMemo(
    () => rawDelays.split(",").map((s) => s.trim()),
    [rawDelays]
  );

  const setReminders = (next: string[]) =>
    setDrafts((d) => ({ ...d, [SILENCE_NUDGE_KEYS.delays]: next.join(",") }));

  const setReminder = (i: number, mins: string) =>
    setReminders(reminders.map((m, j) => (j === i ? mins : m)));

  const removeReminder = (i: number) =>
    setReminders(reminders.filter((_, j) => j !== i));

  const addReminder = () => {
    if (reminders.length >= MAX_REMINDERS) return;
    const defaultNext = reminders.length === 1 ? "60" : "1440";
    setReminders([...reminders, defaultNext]);
  };

  const setCap = (newCap: number) => {
    const clamped = Math.min(10, Math.max(1, newCap));
    setDrafts((d) => ({ ...d, [SILENCE_NUDGE_KEYS.cap]: String(clamped) }));
  };

  const quietStart = value(SILENCE_NUDGE_KEYS.quietStart);
  const quietEnd = value(SILENCE_NUDGE_KEYS.quietEnd);

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
        <div className="space-y-6">
          {/* Master Enable Card */}
          <div className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-border-subtle bg-gradient-to-r from-surface-subtle via-white to-surface-subtle p-4 sm:p-5 shadow-sm">
            <div className="flex items-center gap-3.5">
              <div
                className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl transition-colors ${
                  enabled
                    ? "bg-emerald-100 text-emerald-700"
                    : "bg-surface-mid text-ink-muted"
                }`}
              >
                <Zap className="h-5 w-5" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="font-display text-sm font-bold text-ink">
                    Quiet-Lead Follow-up Automation
                  </h3>
                  <span
                    className={`inline-flex items-center rounded-full px-2 py-0.5 font-label text-[10px] font-bold uppercase tracking-wider ${
                      enabled
                        ? "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200"
                        : "bg-stone-100 text-stone-600 ring-1 ring-stone-200"
                    }`}
                  >
                    {enabled ? "Active" : "Paused"}
                  </span>
                </div>
                <p className="mt-0.5 font-body text-xs text-ink-muted">
                  Sends friendly, contextual follow-ups automatically if a customer stops responding.
                </p>
              </div>
            </div>
            <SwitchPill
              on={enabled}
              disabled={!canManageSettings}
              onChange={(next) =>
                setDrafts((d) => ({
                  ...d,
                  [SILENCE_NUDGE_KEYS.enabled]: next ? "true" : "false",
                }))
              }
            />
          </div>

          {enabled && (
            <div className="space-y-6">
              {/* Cadence Timeline Section */}
              <div className="rounded-2xl border border-border bg-white p-4 sm:p-6 shadow-sm">
                <div className="flex flex-wrap items-center justify-between gap-2 pb-4 border-b border-border-subtle">
                  <div className="flex items-center gap-2.5">
                    <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-50 text-emerald-700">
                      <Bell className="h-4 w-4" />
                    </div>
                    <div>
                      <h4 className="font-display text-sm font-bold text-ink">
                        Follow-up Sequence
                      </h4>
                      <p className="font-body text-xs text-ink-muted">
                        Configure delays between silent intervals before triggering a nudge.
                      </p>
                    </div>
                  </div>
                  <span className="font-label text-xs font-semibold text-ink-secondary bg-surface-subtle border border-border-subtle px-2.5 py-1 rounded-full">
                    {reminders.length} of {MAX_REMINDERS} steps configured
                  </span>
                </div>

                {/* Timeline flow */}
                <div className="relative mt-5 pl-2 sm:pl-3">
                  {/* Subtle vertical connection line */}
                  <div className="absolute left-[1.125rem] sm:left-[1.375rem] top-4 bottom-8 w-[2px] bg-gradient-to-b from-emerald-400 via-emerald-200 to-border" />

                  {/* Initial Trigger Node */}
                  <div className="relative mb-5 flex items-center gap-3">
                    <div className="z-10 flex h-6 w-6 items-center justify-center rounded-full bg-emerald-600 text-white shadow-sm ring-4 ring-white">
                      <Zap className="h-3 w-3" />
                    </div>
                    <span className="font-body text-xs font-medium text-ink-secondary">
                      Lead goes silent after AI reply
                    </span>
                  </div>

                  {/* Reminder Steps */}
                  <div className="space-y-4">
                    {reminders.map((mins, i) => {
                      const rowValid = isValidMinutes(mins);
                      const durationDisplay = rowValid ? formatDuration(mins) : "";

                      return (
                        <div key={i} className="relative flex items-start gap-3">
                          {/* Step Number Badge */}
                          <div className="z-10 mt-2 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-emerald-100 font-label text-xs font-bold text-emerald-800 shadow-sm ring-4 ring-white">
                            {i + 1}
                          </div>

                          {/* Step Card */}
                          <div
                            className={`flex-1 rounded-xl border p-3.5 sm:p-4 transition-all duration-200 ${
                              rowValid
                                ? "border-border-subtle bg-surface-subtle/40 hover:bg-surface-subtle/80 hover:border-border"
                                : "border-red-300 bg-red-50/30"
                            }`}
                          >
                            <div className="flex items-center justify-between gap-2 mb-2.5">
                              <div className="flex items-center gap-2">
                                <span className="font-display text-xs font-bold text-ink">
                                  {i === 0
                                    ? "1st Follow-up"
                                    : i === 1
                                    ? "2nd Follow-up"
                                    : "3rd Follow-up"}
                                </span>
                                {durationDisplay && (
                                  <span className="font-label text-[11px] font-medium text-emerald-700 bg-emerald-50 border border-emerald-200/60 px-2 py-0.5 rounded-md">
                                    {durationDisplay}
                                  </span>
                                )}
                              </div>
                              {reminders.length > 1 && canManageSettings && (
                                <button
                                  type="button"
                                  onClick={() => removeReminder(i)}
                                  aria-label={`Remove reminder ${i + 1}`}
                                  className="rounded-lg p-1 text-ink-muted transition-colors hover:bg-white hover:text-red-600 hover:shadow-xs"
                                >
                                  <X className="h-4 w-4" />
                                </button>
                              )}
                            </div>

                            {/* Delay control row */}
                            <div className="flex flex-wrap items-center gap-2.5">
                              <span className="font-body text-xs text-ink-secondary">
                                Wait
                              </span>

                              <div className="relative inline-flex items-center">
                                <input
                                  type="text"
                                  inputMode="numeric"
                                  aria-label={`Minutes before reminder ${i + 1}`}
                                  disabled={!canManageSettings}
                                  value={mins}
                                  onChange={(e) =>
                                    setReminder(i, e.target.value.replace(/\D/g, ""))
                                  }
                                  className={`w-20 rounded-lg border bg-white px-2.5 py-1.5 pr-8 text-center font-display text-xs font-semibold text-ink shadow-xs transition focus:outline-none focus:ring-2 focus:ring-primary/20 disabled:opacity-60 ${
                                    rowValid
                                      ? "border-border focus:border-primary"
                                      : "border-red-400 focus:ring-red-200"
                                  }`}
                                />
                                <span className="pointer-events-none absolute right-2 font-body text-[11px] text-ink-muted">
                                  min
                                </span>
                              </div>

                              <span className="font-body text-xs text-ink-secondary">
                                after {i === 0 ? "the AI's reply" : `reminder ${i}`}
                              </span>

                              {/* Presets */}
                              {canManageSettings && (
                                <div className="flex flex-wrap items-center gap-1 sm:ml-auto">
                                  <span className="text-[10px] font-label text-ink-muted mr-0.5 hidden sm:inline">
                                    Preset:
                                  </span>
                                  {DURATION_PRESETS.map((p) => (
                                    <button
                                      key={p.mins}
                                      type="button"
                                      onClick={() => setReminder(i, p.mins)}
                                      className={`rounded-md px-1.5 py-0.5 font-label text-[11px] font-medium transition ${
                                        mins === p.mins
                                          ? "bg-emerald-600 text-white shadow-xs"
                                          : "bg-white text-ink-secondary border border-border hover:border-emerald-300 hover:text-emerald-700"
                                      }`}
                                    >
                                      {p.label}
                                    </button>
                                  ))}
                                </div>
                              )}
                            </div>

                            {!rowValid && (
                              <p className="mt-2 font-body text-[11px] text-red-600">
                                Enter a whole number from 1 to 1440 (up to 24 hours).
                              </p>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>

                  {/* Add Reminder Button Node */}
                  {reminders.length < MAX_REMINDERS && canManageSettings && (
                    <div className="relative mt-4 flex items-center gap-3">
                      <div className="z-10 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-dashed border-emerald-400 bg-white text-emerald-600">
                        <Plus className="h-3 w-3" />
                      </div>
                      <button
                        type="button"
                        onClick={addReminder}
                        className="inline-flex items-center gap-1.5 rounded-xl border border-dashed border-emerald-300 bg-emerald-50/40 px-3 py-1.5 font-body text-xs font-semibold text-emerald-700 transition hover:bg-emerald-50 hover:border-emerald-400"
                      >
                        <Plus className="h-3.5 w-3.5" />
                        Add another reminder ({reminders.length + 1} of {MAX_REMINDERS})
                      </button>
                    </div>
                  )}
                </div>

                <div className="mt-6 rounded-xl bg-surface-subtle border border-border-subtle p-3 text-ink-secondary">
                  <p className="font-body text-xs flex items-center gap-2">
                    <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-emerald-100 text-emerald-700 font-bold text-[10px]">
                      ✓
                    </span>
                    <span>
                      Each reminder is sent only if the lead has not replied. If the lead
                      replies at any time, the remaining follow-ups are cancelled immediately.
                    </span>
                  </p>
                </div>
              </div>

              {/* Delivery Guards & Boundaries Grid */}
              <div className="grid gap-4 sm:grid-cols-2">
                {/* Daily Limit Card */}
                <div className="flex flex-col justify-between rounded-2xl border border-border bg-white p-4 sm:p-5 shadow-sm">
                  <div>
                    <div className="flex items-center gap-2.5 mb-2">
                      <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-amber-50 text-amber-700">
                        <Shield className="h-4 w-4" />
                      </div>
                      <div>
                        <h4 className="font-display text-sm font-bold text-ink">
                          Daily Limit per Lead
                        </h4>
                        <p className="font-body text-xs text-ink-muted">
                          Max follow-ups one lead can get in 24 hours
                        </p>
                      </div>
                    </div>

                    <div className="mt-4 flex items-center gap-3">
                      {/* Interactive Stepper */}
                      <div className="inline-flex items-center rounded-xl border border-border bg-surface-subtle p-1 shadow-xs">
                        <button
                          type="button"
                          disabled={!canManageSettings || capNum <= 1}
                          onClick={() => setCap(capNum - 1)}
                          className="flex h-8 w-8 items-center justify-center rounded-lg bg-white text-ink transition hover:bg-surface hover:text-primary disabled:opacity-40 disabled:hover:bg-white"
                          aria-label="Decrease daily limit"
                        >
                          <Minus className="h-3.5 w-3.5" />
                        </button>
                        <div className="w-14 text-center">
                          <span className="font-display text-base font-bold text-ink">
                            {capValid ? capNum : value(SILENCE_NUDGE_KEYS.cap)}
                          </span>
                        </div>
                        <button
                          type="button"
                          disabled={!canManageSettings || capNum >= 10}
                          onClick={() => setCap(capNum + 1)}
                          className="flex h-8 w-8 items-center justify-center rounded-lg bg-white text-ink transition hover:bg-surface hover:text-primary disabled:opacity-40 disabled:hover:bg-white"
                          aria-label="Increase daily limit"
                        >
                          <Plus className="h-3.5 w-3.5" />
                        </button>
                      </div>

                      <span className="font-label text-xs font-semibold text-ink-secondary bg-surface-subtle border border-border-subtle px-2.5 py-1 rounded-lg">
                        nudges / 24 hrs
                      </span>
                    </div>

                    {/* Quick cap chips */}
                    {canManageSettings && (
                      <div className="mt-3 flex items-center gap-1.5">
                        <span className="font-label text-[11px] text-ink-muted">
                          Quick set:
                        </span>
                        {CAP_PRESETS.map((preset) => (
                          <button
                            key={preset}
                            type="button"
                            onClick={() => setCap(parseInt(preset, 10))}
                            className={`rounded-md px-2 py-0.5 font-label text-xs font-semibold transition ${
                              String(capNum) === preset
                                ? "bg-amber-600 text-white shadow-xs"
                                : "bg-surface-subtle text-ink-secondary border border-border-subtle hover:border-amber-400 hover:text-amber-800"
                            }`}
                          >
                            {preset}
                          </button>
                        ))}
                      </div>
                    )}

                    {!capValid && (
                      <p className="mt-2 font-body text-[11px] text-red-600">
                        Must be a whole number between 1 and 10.
                      </p>
                    )}
                  </div>

                  {capValid && reminders.length > capNum && (
                    <div className="mt-4 rounded-xl bg-amber-50 border border-amber-200/80 p-2.5">
                      <p className="font-body text-xs text-amber-800">
                        ⚠️ Limit is set to <strong>{capNum}</strong>, so only {capNum} of your{" "}
                        {reminders.length} follow-ups will send to a single lead per day.
                      </p>
                    </div>
                  )}
                </div>

                {/* Quiet Hours Card */}
                <div className="flex flex-col justify-between rounded-2xl border border-border bg-white p-4 sm:p-5 shadow-sm">
                  <div>
                    <div className="flex items-center justify-between gap-2 mb-2">
                      <div className="flex items-center gap-2.5">
                        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-50 text-indigo-700">
                          <Moon className="h-4 w-4" />
                        </div>
                        <div>
                          <h4 className="font-display text-sm font-bold text-ink">
                            Quiet Hours
                          </h4>
                          <p className="font-body text-xs text-ink-muted">
                            Pause automated messages during rest hours
                          </p>
                        </div>
                      </div>
                      <span className="font-label text-[10px] font-bold uppercase tracking-wider text-indigo-700 bg-indigo-50 border border-indigo-200/60 px-2 py-0.5 rounded-full">
                        IST (UTC+5:30)
                      </span>
                    </div>

                    {/* Inline Time Range Selector */}
                    <div className="mt-4 rounded-xl border border-border bg-surface-subtle p-3">
                      <div className="flex items-center justify-between gap-2">
                        {/* Start time */}
                        <div className="flex-1">
                          <label className="block font-label text-[10px] font-bold uppercase tracking-wider text-ink-muted mb-1">
                            Mute From
                          </label>
                          <div className="relative flex items-center">
                            <input
                              type="time"
                              disabled={!canManageSettings}
                              value={quietStart}
                              onChange={(e) =>
                                setDrafts((d) => ({
                                  ...d,
                                  [SILENCE_NUDGE_KEYS.quietStart]: e.target.value,
                                }))
                              }
                              className="w-full rounded-lg border border-border bg-white px-2.5 py-1.5 font-mono text-xs font-semibold text-ink shadow-xs transition focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20 disabled:opacity-60"
                            />
                          </div>
                        </div>

                        {/* Arrow separator */}
                        <div className="flex flex-col items-center justify-center pt-3 text-ink-muted">
                          <ArrowRight className="h-4 w-4" />
                        </div>

                        {/* End time */}
                        <div className="flex-1">
                          <label className="block font-label text-[10px] font-bold uppercase tracking-wider text-ink-muted mb-1">
                            Resume At
                          </label>
                          <div className="relative flex items-center">
                            <input
                              type="time"
                              disabled={!canManageSettings}
                              value={quietEnd}
                              onChange={(e) =>
                                setDrafts((d) => ({
                                  ...d,
                                  [SILENCE_NUDGE_KEYS.quietEnd]: e.target.value,
                                }))
                              }
                              className="w-full rounded-lg border border-border bg-white px-2.5 py-1.5 font-mono text-xs font-semibold text-ink shadow-xs transition focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20 disabled:opacity-60"
                            />
                          </div>
                        </div>
                      </div>

                      {/* Live 12-hour summary */}
                      <div className="mt-2.5 flex items-center gap-1.5 font-body text-xs text-ink-secondary">
                        <Clock className="h-3.5 w-3.5 text-indigo-600 shrink-0" />
                        <span>
                          Messages held between{" "}
                          <strong className="text-ink">{formatTime12h(quietStart)}</strong> and{" "}
                          <strong className="text-ink">{formatTime12h(quietEnd)} IST</strong>
                        </span>
                      </div>
                    </div>
                  </div>

                  <p className="mt-3 font-body text-[11px] text-ink-muted leading-relaxed">
                    ⚡ <strong>First follow-up sends immediately</strong> — quiet hours only
                    pause and delay subsequent follow-ups until the quiet window ends.
                  </p>
                </div>
              </div>
            </div>
          )}

          <SectionFooter
            status={
              <SaveStatus
                state={saveStates.automations_silence ?? "idle"}
                dirty={dirty}
                idleLabel={
                  enabled
                    ? "Quiet-lead follow-ups are enabled"
                    : "Quiet-lead follow-ups are off"
                }
              />
            }
          >
            <SaveButton
              state={saveStates.automations_silence ?? "idle"}
              dirty={dirty && delaysValid && capValid}
              disabled={!canManageSettings}
              onClick={() =>
                handleSave("automations_silence", Object.values(SILENCE_NUDGE_KEYS))
              }
            />
          </SectionFooter>
        </div>
      </SettingsSection>
    </SettingsAccordion>
  );
}

