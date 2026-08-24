"use client";
import { useEffect, useState } from "react";
import { Phone, Eye, EyeOff } from "lucide-react";
import { useRouter } from "next/navigation";
import { API_URL } from "@/lib/api";
import { useSettingsForm } from "../SettingsFormContext";
import {
  SaveButton, SaveStatus, SectionFooter, SettingsAccordion, SettingsSection,
} from "../SettingsSection";

type FieldDef = {
  key: string; label: string; placeholder?: string; secret: boolean;
  required?: boolean; hint?: string;
};

const VOICE_SECTION = {
  id: "voice",
  label: "Voice Calling (Cloud Telephony)",
  icon: Phone,
  description: "Cloud Telephony credentials for click-to-call telecalling. Per-caller Agent IDs are set on the Team page.",
  fields: [
    { key: "telecmi_secret", label: "App Secret", secret: true, required: true },
    { key: "telecmi_callerid", label: "Caller ID (DID shown to leads)", secret: false, required: false, hint: "The outbound number leads see when you call them" },
    { key: "telecmi_webhook_secret", label: "Webhook Secret", secret: true, required: false, hint: "Appended as ?webhook_secret= to your Cloud Telephony CDR webhook URL" },
  ] as FieldDef[],
};

function OutlinedField({
  label, value, onChange, placeholder, type = "text", rightSlot, hint, disabled = false,
}: {
  label: string; value: string; onChange: (v: string) => void;
  placeholder?: string; type?: "text" | "password"; rightSlot?: React.ReactNode; hint?: string; disabled?: boolean;
}) {
  return (
    <div className="space-y-1">
      <div className="relative">
        <input
          type={type}
          value={value}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder ?? " "}
          className="peer w-full px-4 pt-5 pb-2 pr-10 rounded-xl bg-white border border-border text-sm font-body text-ink placeholder:text-ink-muted/40 focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/15 transition disabled:cursor-not-allowed disabled:bg-surface-subtle disabled:text-ink-muted"
        />
        <label className="pointer-events-none absolute left-3 -top-2 px-1.5 text-[11px] font-label font-medium text-ink-muted bg-white tracking-wide">
          {label}
        </label>
        {rightSlot && (
          <div className="absolute right-2.5 top-1/2 -translate-y-1/2 flex items-center">
            {rightSlot}
          </div>
        )}
      </div>
      {hint && <p className="text-[11px] text-ink-muted font-body pl-1">{hint}</p>}
    </div>
  );
}

function SecretField({
  label, storedMask, isSet, newValue, onChange, hint, disabled = false,
}: {
  label: string; storedMask: string; isSet: boolean;
  newValue: string; onChange: (v: string) => void; hint?: string; disabled?: boolean;
}) {
  const [show, setShow] = useState(false);
  const [editing, setEditing] = useState(false);
  const showInput = editing || newValue.length > 0 || !isSet;

  return (
    <div className="space-y-1">
      {!showInput ? (
        <button type="button" disabled={disabled} onClick={() => setEditing(true)} className="relative w-full text-left group disabled:cursor-not-allowed">
          <div className="w-full px-4 pt-5 pb-2 rounded-xl bg-white border border-border font-mono text-sm text-ink-secondary cursor-text group-hover:border-primary/40 transition group-disabled:cursor-not-allowed group-disabled:bg-surface-subtle group-disabled:text-ink-muted">
            {storedMask}
          </div>
          <span className="pointer-events-none absolute left-3 -top-2 px-1.5 text-[11px] font-label font-medium text-ink-muted bg-white tracking-wide">
            {label}
          </span>
          <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[11px] font-label font-semibold text-primary opacity-0 group-hover:opacity-100 transition">
            Edit
          </span>
        </button>
      ) : (
        <OutlinedField
          label={label}
          value={newValue}
          onChange={onChange}
          type={show ? "text" : "password"}
          placeholder={isSet ? "Enter new value to replace existing" : "Paste your value here"}
          rightSlot={
            <button type="button" onClick={() => setShow(s => !s)} className="p-1 text-ink-muted hover:text-ink-secondary" tabIndex={-1}>
              {show ? <EyeOff size={14} /> : <Eye size={14} />}
            </button>
          }
          disabled={disabled}
        />
      )}
      {hint && <p className="text-[11px] text-ink-muted font-body pl-1">{hint}</p>}
    </div>
  );
}

export default function TelecallingSettingsPage() {
  const router = useRouter();
  const { settingFor, drafts, setDrafts, saveStates, canManageSettings, tenantId, hasTelecmiConfig, handleSave } = useSettingsForm();

  useEffect(() => {
    if (hasTelecmiConfig === false) router.replace("/dashboard/settings?tab=automations", { scroll: false });
  }, [hasTelecmiConfig, router]);

  if (hasTelecmiConfig !== true) return null;

  const voiceConfigured = VOICE_SECTION.fields.filter(f => f.required !== false).every(f => settingFor(f.key)?.is_set);
  const dirty = VOICE_SECTION.fields.some(f => {
    const meta = settingFor(f.key);
    const draft = drafts[f.key] ?? "";
    if (f.secret) return draft.length > 0;
    const stored = meta?.display_value === "Not set" ? "" : (meta?.display_value ?? "");
    return draft !== stored;
  });
  const secretMap = Object.fromEntries(VOICE_SECTION.fields.map(f => [f.key, f.secret]));

  return (
    <SettingsAccordion>
      <SettingsSection
        id="voice-credentials"
        icon={VOICE_SECTION.icon}
        accent="amber"
        title={VOICE_SECTION.label}
        description={VOICE_SECTION.description}
        status={{ label: voiceConfigured ? "Configured" : "Not configured", tone: voiceConfigured ? "on" : "warn" }}
        dirty={dirty}
      >
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {VOICE_SECTION.fields.map((field) => {
            const meta = settingFor(field.key);
            const draft = drafts[field.key] ?? "";
            const labelWithOptional = field.required === false ? `${field.label} (optional)` : field.label;
            if (field.secret) {
              return (
                <SecretField
                  key={field.key}
                  label={labelWithOptional}
                  storedMask={meta?.display_value ?? "Not set"}
                  isSet={!!meta?.is_set}
                  newValue={draft}
                  onChange={v => setDrafts(d => ({ ...d, [field.key]: v }))}
                  hint={field.hint}
                  disabled={!canManageSettings}
                />
              );
            }
            return (
              <OutlinedField
                key={field.key}
                label={labelWithOptional}
                value={draft}
                onChange={v => setDrafts(d => ({ ...d, [field.key]: v }))}
                placeholder={field.placeholder}
                hint={field.hint}
                disabled={!canManageSettings}
              />
            );
          })}
        </div>

        {/* Webhook URL + setup guide */}
        {(() => {
          const cdrUrl = tenantId
            ? `${API_URL}/api/v1/calls/telecmi-cdr/${tenantId}`
            : null;
          return (
            <div className="mt-5 space-y-2 rounded-2xl border border-border bg-surface-subtle p-4 font-body text-xs">
              <p className="font-label text-[10px] font-bold uppercase tracking-wider text-ink-secondary">Setup Guide</p>
              <ol className="list-inside list-decimal space-y-1 text-ink-secondary">
                <li>Log in to your <span className="font-semibold">Cloud Telephony dashboard</span> → Settings → Webhook</li>
                <li>Set CDR Webhook URL to:<br />
                  <code className="mt-1 inline-block select-all break-all rounded border border-border bg-white px-2 py-1 font-mono text-[11px] text-ink">
                    {cdrUrl ?? "Retrieving webhook URL…"}
                  </code>
                </li>
                <li>If using a Webhook Secret, append it: <code className="rounded border border-border bg-white px-1 py-0.5 font-mono text-[10px]">?webhook_secret=YOUR_SECRET</code></li>
                <li>Set your <span className="font-semibold">App Secret</span> above (from Cloud Telephony dashboard → API Keys)</li>
                <li>Per-caller <span className="font-semibold">Agent IDs</span> are configured on the <span className="font-semibold">Team page</span></li>
              </ol>
            </div>
          );
        })()}

        <SectionFooter
          status={<SaveStatus state={saveStates.voice ?? "idle"} dirty={dirty} idleLabel={voiceConfigured ? "Credentials are set" : "Credentials not set yet"} />}
        >
          <SaveButton
            state={saveStates.voice ?? "idle"}
            dirty={dirty}
            disabled={!canManageSettings}
            onClick={() => handleSave("voice", VOICE_SECTION.fields.map(f => f.key), secretMap)}
          />
        </SectionFooter>
      </SettingsSection>
    </SettingsAccordion>
  );
}
