"use client";
import { useEffect, useState, useCallback, useMemo } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  Phone, Sparkles, Eye, EyeOff, AlertCircle, Loader2, Crown, Timer
} from "lucide-react";
import { API_URL, getAuthHeaders } from "@/lib/api";
import { useAuthRole } from "../contexts/AuthRoleContext";
import ChangePasswordCard from "./ChangePasswordCard";
import ConnectChannelsPanel from "./ConnectChannelsPanel";
import { TelecallingConfigPanel } from "./TelecallingConfigPanel";
import { IntakeConfigPanel } from "./IntakeConfigPanel";
import { QuickRepliesPanel } from "./QuickRepliesPanel";
import { InboxConfigPanel } from "./InboxConfigPanel";
import { NotificationConfigPanel } from "./NotificationConfigPanel";
import { BusinessHoursPanel } from "./BusinessHoursPanel";
import {
  SaveButton,
  SaveStatus,
  SectionFooter,
  SettingsAccordion,
  SettingsSection,
  SwitchPill,
} from "./SettingsSection";
import { createClient } from "@/lib/supabase/client";
import { cn } from "@/lib/utils";

type Setting = {
  key: string;
  display_value: string;
  is_secret: boolean;
  is_set: boolean;
  updated_at: string;
};

type SettingsMap = Record<string, string>;

type FieldDef = {
  key: string;
  label: string;
  placeholder?: string;
  secret: boolean;
  required?: boolean;
  hint?: string;
};

type ToggleDef = { key: string; label: string; description: string; defaultEnabled?: boolean };

type SectionDef = {
  id: string;
  label: string;
  icon: typeof Phone;
  color: string;
  bg: string;
  description: string;
  fields: FieldDef[];
  toggles?: ToggleDef[];
};

const SECTIONS: SectionDef[] = [
  {
    id: "voice",
    label: "Voice Calling (Cloud Telephony)",
    icon: Phone,
    color: "#d97706",
    bg: "#fef3c7",
    description: "Cloud Telephony credentials for click-to-call telecalling. Per-caller Agent IDs are set on the Team page.",
    fields: [
      { key: "telecmi_secret", label: "App Secret", secret: true, required: true },
      { key: "telecmi_callerid", label: "Caller ID (DID shown to leads)", secret: false, required: false, hint: "The outbound number leads see when you call them" },
      { key: "telecmi_webhook_secret", label: "Webhook Secret", secret: true, required: false, hint: "Appended as ?webhook_secret= to your Cloud Telephony CDR webhook URL" },
    ],
  },
];

const AI_AUTO_REPLY_TOGGLE: ToggleDef = {
  key: "ai_auto_reply_enabled",
  label: "AI Auto-Reply",
  description: "Allow Aira to automatically reply to inbound WhatsApp messages using AI.",
  defaultEnabled: true,
};

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

const SILENCE_MAX_RUNGS = 3;

/** Mirrors _parse_delays in backend/app/services/silence_nudge.py: up to three
 *  whole minutes, 1-1440, strictly increasing. Returns null when invalid so the
 *  UI can reject on save rather than let the backend silently fall back. */
function parseSilenceDelays(raw: string): number[] | null {
  const parts = raw.split(",").map(s => s.trim()).filter(Boolean);
  if (parts.length === 0 || parts.length > SILENCE_MAX_RUNGS) return null;
  const nums: number[] = [];
  for (const part of parts) {
    if (!/^\d+$/.test(part)) return null;
    const n = parseInt(part, 10);
    if (n < 1 || n > 1440) return null;
    if (nums.length > 0 && n <= nums[nums.length - 1]) return null;
    nums.push(n);
  }
  return nums;
}

async function fetchSettings(): Promise<Setting[]> {
  const auth = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/v1/settings/`, { headers: auth });
  if (!res.ok) throw new Error("Failed to load settings");
  return (await res.json()).settings;
}

async function saveSettings(updates: SettingsMap): Promise<void> {
  const auth = await getAuthHeaders();
  for (let attempt = 1; attempt <= 2; attempt++) {
    try {
      const res = await fetch(`${API_URL}/api/v1/settings/`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", ...auth },
        body: JSON.stringify({ updates }),
      });
      if (!res.ok) throw new Error("Failed to save settings");
      return;
    } catch {
      if (attempt === 2) throw new Error("Server unreachable — please try again");
    }
  }
}

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

type SaveState = "idle" | "dirty" | "saving" | "saved";

export default function SettingsPage() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const requestedTab = searchParams.get("tab") || "general";
  const activeTab = requestedTab === "ai" ? "automations" : requestedTab;

  const { role, permissions, loading: roleLoading } = useAuthRole();
  const canViewSettings = role === "owner" || permissions.includes("settings.view") || permissions.includes("settings.manage");
  const canManageSettings = role === "owner" || permissions.includes("settings.manage");
  const [settings, setSettings] = useState<Setting[]>([]);
  const [drafts, setDrafts] = useState<SettingsMap>({});
  const [saveStates, setSaveStates] = useState<Record<string, SaveState>>({});
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // User Profile details
  const [email, setEmail] = useState<string>("");
  const [fullName, setFullName] = useState<string>("");
  const [createdAt, setCreatedAt] = useState<string>("");

  // Tenant ID (for tenant-scoped webhook URLs)
  const [tenantId, setTenantId] = useState<string | null>(null);

  // Purchased subscription items (for gating the Notifications tab on purchase, not quota)
  const [purchasedFeatures, setPurchasedFeatures] = useState<string[]>([]);
  const [callingProvider, setCallingProvider] = useState<"telecmi" | "sim_basic" | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const auth = await getAuthHeaders();
        const res = await fetch(`${API_URL}/api/v1/subscriptions/me`, { headers: auth });
        if (res.ok) {
          const data = await res.json();
          setPurchasedFeatures((data.items ?? []).map((i: { feature_key: string }) => i.feature_key));
        }
      } catch { /* fail open — pre-existing tenants have no items rows at all */ }
    })();
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const auth = await getAuthHeaders();
        const res = await fetch(`${API_URL}/api/v1/settings/telecalling-config`, { headers: auth });
        if (res.ok) {
          const data = await res.json();
          setCallingProvider((data.calling_provider as "telecmi" | "sim_basic" | undefined) ?? "telecmi");
        } else {
          setCallingProvider("telecmi");
        }
      } catch {
        setCallingProvider("telecmi");
      }
    })();
  }, []);

  const hasNotifications = purchasedFeatures.length === 0 || purchasedFeatures.includes("inbound_messaging") || purchasedFeatures.includes("outbound_messaging");
  const hasTelecmiConfig = callingProvider === "telecmi";

  useEffect(() => {
    if (callingProvider === "sim_basic" && activeTab === "telecalling") {
      router.replace(`${pathname}?tab=automations`, { scroll: false });
    }
  }, [activeTab, callingProvider, pathname, router]);

  const load = useCallback(async () => {
    try {
      const s = await fetchSettings();
      setSettings(s);
      setDrafts((prev) => {
        const next: SettingsMap = { ...prev };
        s.forEach((row) => {
          if (!row.is_secret) {
            const value = row.display_value === "Not set" ? "" : row.display_value;
            if (!(row.key in next) || next[row.key] === "") next[row.key] = value;
          } else {
            if (!(row.key in next)) next[row.key] = "";
          }
        });
        return next;
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    (async () => {
      try {
        const auth = await getAuthHeaders();
        const res = await fetch(`${API_URL}/api/v1/onboarding/status`, { headers: auth });
        if (res.ok) {
          const data = await res.json();
          if (data.tenant_id) setTenantId(data.tenant_id);
        }
      } catch {}
    })();
    const supabase = createClient();
    const loadUser = async () => {
      const { data } = await supabase.auth.getUser();
      const userEmail = data.user?.email ?? "";
      setEmail(userEmail);
      setCreatedAt(data.user?.created_at ?? "");
      
      const metaName = data.user?.user_metadata?.full_name;
      if (metaName) {
        setFullName(metaName);
      } else {
        const parts = userEmail.split("@")[0].split(/[._-]/);
        const capitalized = parts.map((p: string) => p.charAt(0).toUpperCase() + p.slice(1)).join(" ");
        setFullName(capitalized || "Admin User");
      }
    };
    loadUser();
  }, [load]);

  const initials = fullName.split(" ").map((n) => n[0]).join("").toUpperCase().slice(0, 2) || "AD";
  const memberSince = createdAt ? new Date(createdAt).toLocaleDateString("en-IN", { month: "long", year: "numeric" }) : null;

  function settingFor(key: string) {
    return settings.find(s => s.key === key);
  }

  const sectionDirty = useMemo(() => {
    const map: Record<string, boolean> = {};
    SECTIONS.forEach(section => {
      const dirty = section.fields.some(f => {
        const meta = settingFor(f.key);
        const draft = drafts[f.key] ?? "";
        if (f.secret) return draft.length > 0;
        const stored = meta?.display_value === "Not set" ? "" : (meta?.display_value ?? "");
        return draft !== stored;
      }) || (section.toggles ?? []).some(t => {
        const meta = settingFor(t.key);
        const draft = drafts[t.key];
        if (draft === undefined) return false;
        const isDefaultEnabled = t.defaultEnabled !== false;
        const storedVal = meta?.display_value;
        const stored = storedVal === "Not set" || !storedVal
          ? (isDefaultEnabled ? "true" : "false")
          : (storedVal === "true" ? "true" : "false");
        return draft !== stored;
      });
      map[section.id] = dirty;
    });
    return map;
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [drafts, settings]);

  const aiAutoReplyStored = settingFor(AI_AUTO_REPLY_TOGGLE.key)?.display_value;
  const aiAutoReplyEnabled = drafts[AI_AUTO_REPLY_TOGGLE.key] !== undefined
    ? drafts[AI_AUTO_REPLY_TOGGLE.key] === "true"
    : (aiAutoReplyStored === "Not set" || !aiAutoReplyStored
      ? AI_AUTO_REPLY_TOGGLE.defaultEnabled !== false
      : aiAutoReplyStored === "true");
  const aiAutomationDirty = (() => {
    const draft = drafts[AI_AUTO_REPLY_TOGGLE.key];
    if (draft === undefined) return false;
    const stored = aiAutoReplyStored === "Not set" || !aiAutoReplyStored
      ? (AI_AUTO_REPLY_TOGGLE.defaultEnabled !== false ? "true" : "false")
      : (aiAutoReplyStored === "true" ? "true" : "false");
    return draft !== stored;
  })();

  const silenceStored = (key: string) => {
    const stored = settingFor(key)?.display_value;
    return !stored || stored === "Not set" ? SILENCE_NUDGE_DEFAULTS[key] : stored;
  };
  const silenceValue = (key: string) => drafts[key] ?? silenceStored(key);
  const silenceEnabled = silenceValue(SILENCE_NUDGE_KEYS.enabled) === "true";
  const silenceDirty = Object.values(SILENCE_NUDGE_KEYS).some(
    key => drafts[key] !== undefined && drafts[key] !== silenceStored(key)
  );
  const silenceDelaysValid = parseSilenceDelays(silenceValue(SILENCE_NUDGE_KEYS.delays)) !== null;
  const silenceCapValid = (() => {
    const raw = silenceValue(SILENCE_NUDGE_KEYS.cap);
    if (!/^\d+$/.test(raw)) return false;
    const n = parseInt(raw, 10);
    return n >= 1 && n <= 10;
  })();

  async function handleSave(sectionId: string, allKeys: string[]) {
    if (!canManageSettings) return;
    setSaveStates(s => ({ ...s, [sectionId]: "saving" }));
    setError(null);
    const sectionDef = SECTIONS.find(s => s.id === sectionId);
    const updates: SettingsMap = {};
    allKeys.forEach(k => {
      const draft = drafts[k];
      const current = settingFor(k);
      const fieldDef = sectionDef?.fields.find(f => f.key === k);
      const isSecret = fieldDef?.secret ?? current?.is_secret ?? false;
      if (isSecret) {
        if (draft && draft.length > 0) updates[k] = draft;
      } else {
        const stored = current ? (current.display_value === "Not set" ? "" : current.display_value) : "";
        if (draft !== undefined && draft !== stored) updates[k] = draft;
      }
    });

    try {
      if (Object.keys(updates).length > 0) await saveSettings(updates);
      setDrafts(prev => {
        const next = { ...prev };
        allKeys.forEach(k => delete next[k]);
        return next;
      });
      await load();
      setSaveStates(s => ({ ...s, [sectionId]: "saved" }));
      setTimeout(() => setSaveStates(s => ({ ...s, [sectionId]: "idle" })), 2500);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
      setSaveStates(s => ({ ...s, [sectionId]: "idle" }));
    }
  }

  if (roleLoading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Loader2 size={24} className="animate-spin text-primary" />
      </div>
    );
  }

  if (!canViewSettings) {
    return (
      <div>
        <ChangePasswordCard />
      </div>
    );
  }

  // Find Configured/Not configured statuses for sections
  const voiceSection = SECTIONS.find(s => s.id === "voice")!;
  const voiceConfigured = voiceSection.fields.filter(f => f.required !== false).every(f => settingFor(f.key)?.is_set);

  return (
    <div className="min-w-0">
      {/* Curved Tab Switcher */}
      <div className="-mx-1 mb-5 overflow-x-auto px-1 pb-1 sm:mx-0 sm:mb-6 sm:overflow-visible sm:p-0 lg:hidden">
      <div className="flex w-max gap-1 rounded-2xl bg-[#e8e3db]/60 p-1 sm:w-fit">
        <button
          onClick={() => router.push(`${pathname}?tab=general`)}
          className={cn(
            "shrink-0 rounded-xl px-3 py-2.5 font-label text-xs font-bold transition-all sm:px-5",
            activeTab === "general"
              ? "bg-white text-primary shadow-sm"
              : "text-[#78716c] hover:text-[#292524]"
          )}
        >
          General Settings
        </button>
        <button
          onClick={() => router.push(`${pathname}?tab=channels`)}
          className={cn(
            "shrink-0 rounded-xl px-3 py-2.5 font-label text-xs font-bold transition-all sm:px-5",
            activeTab === "channels"
              ? "bg-white text-primary shadow-sm"
              : "text-[#78716c] hover:text-[#292524]"
          )}
        >
          Channels
        </button>
        {hasTelecmiConfig && (
          <button
            onClick={() => router.push(`${pathname}?tab=telecalling`)}
            className={cn(
              "shrink-0 rounded-xl px-3 py-2.5 font-label text-xs font-bold transition-all sm:px-5",
              activeTab === "telecalling"
                ? "bg-white text-primary shadow-sm"
                : "text-[#78716c] hover:text-[#292524]"
            )}
          >
            Telecalling Config
          </button>
        )}
        <button
          onClick={() => router.push(`${pathname}?tab=automations`)}
          className={cn(
            "shrink-0 rounded-xl px-3 py-2.5 font-label text-xs font-bold transition-all sm:px-5",
            activeTab === "automations"
              ? "bg-white text-primary shadow-sm"
              : "text-[#78716c] hover:text-[#292524]"
          )}
        >
          Automations
        </button>
        {hasNotifications && (
          <button
            onClick={() => router.push(`${pathname}?tab=notifications`)}
            className={cn(
              "shrink-0 rounded-xl px-3 py-2.5 font-label text-xs font-bold transition-all sm:px-5",
              activeTab === "notifications"
                ? "bg-white text-primary shadow-sm"
                : "text-[#78716c] hover:text-[#292524]"
            )}
          >
            Notifications
          </button>
        )}
      </div>
      </div>

      {error && (
        <div className="mb-5 flex items-center gap-2 p-3.5 rounded-2xl bg-red-50 text-red-700 border border-red-100">
          <AlertCircle size={15} />
          <span className="font-body text-sm">{error}</span>
        </div>
      )}

      {loading ? (
        <div className="space-y-5">
          <div className="card rounded-3xl h-56 animate-pulse bg-border-subtle" />
        </div>
      ) : (
        <div className="space-y-6">
          {/* TAB 1: General Settings */}
          {activeTab === "general" && (
            <div className="space-y-6">
              {/* Admin Identity Card */}
              <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-[#1c1917] via-[#292524] to-[#1c1917] p-5 shadow-xl sm:rounded-[2rem] sm:p-8">
                <div className="absolute top-0 right-0 w-64 h-64 bg-gradient-to-bl from-primary/10 to-transparent rounded-full -translate-y-1/2 translate-x-1/3" />
                <div className="absolute bottom-0 left-0 w-48 h-48 bg-gradient-to-tr from-amber-500/10 to-transparent rounded-full translate-y-1/2 -translate-x-1/4" />

                <div className="relative flex min-w-0 flex-col gap-4 sm:flex-row sm:items-center sm:gap-6">
                  <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-[#2e1065] to-primary shadow-lg shadow-primary/25 sm:h-20 sm:w-20">
                    <span className="font-display text-2xl font-bold text-white sm:text-3xl">{initials}</span>
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-3 flex-wrap">
                      <h2 className="break-words font-display text-xl font-bold text-white sm:text-2xl">{fullName}</h2>
                      <span className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-amber-500/15 border border-amber-500/30">
                        <Crown size={12} className="text-amber-400" />
                        <span className="font-label text-xs font-bold text-amber-300 uppercase tracking-wider">Admin</span>
                      </span>
                    </div>
                    {email && (
                      <p className="mt-1 break-all font-body text-sm text-[#a8a29e]">{email}</p>
                    )}
                    <div className="mt-3 flex flex-wrap items-center gap-3 sm:gap-4">
                      {memberSince && (
                        <span className="font-label text-xs text-[#78716c]">Member since {memberSince}</span>
                      )}
                      <span className="flex items-center gap-1.5 font-label text-xs text-emerald-400">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                        All systems online
                      </span>
                    </div>
                  </div>
                </div>

                <div className="relative mt-6 pt-6 border-t border-[#44403c]/50">
                  <p className="font-body text-sm text-[#a8a29e] italic leading-relaxed">
                    &quot;The best leaders don&apos;t create followers — they create more leaders.&quot;
                  </p>
                  <p className="font-label text-[10px] text-[#57534e] mt-1 uppercase tracking-widest">Your role: Empower your team</p>
                </div>
              </div>

              <ChangePasswordCard />
            </div>
          )}

          {/* TAB 2: Integrations — messaging channels, Meta Ads, Razorpay */}
          {activeTab === "channels" && <ConnectChannelsPanel canManage={canManageSettings} />}

          {/* TAB 3: Telecalling Config */}
          {activeTab === "telecalling" && hasTelecmiConfig && (
            <SettingsAccordion>
              <SettingsSection
                id="voice-credentials"
                icon={voiceSection.icon}
                accent="amber"
                title={voiceSection.label}
                description={voiceSection.description}
                status={{
                  label: voiceConfigured ? "Configured" : "Not configured",
                  tone: voiceConfigured ? "on" : "warn",
                }}
                dirty={sectionDirty.voice ?? false}
              >
                <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                  {voiceSection.fields.map((field) => {
                    const meta = settingFor(field.key);
                    const draft = drafts[field.key] ?? "";
                    const labelWithOptional = field.required === false
                      ? `${field.label} (optional)`
                      : field.label;
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
                  status={
                    <SaveStatus
                      state={saveStates.voice ?? "idle"}
                      dirty={sectionDirty.voice ?? false}
                      idleLabel={voiceConfigured ? "Credentials are set" : "Credentials not set yet"}
                    />
                  }
                >
                  <SaveButton
                    state={saveStates.voice ?? "idle"}
                    dirty={sectionDirty.voice ?? false}
                    disabled={!canManageSettings}
                    onClick={() => handleSave("voice", voiceSection.fields.map(f => f.key))}
                  />
                </SectionFooter>
              </SettingsSection>
            </SettingsAccordion>
          )}

          {/* TAB 4: Automations */}
          {activeTab === "automations" && (
            <SettingsAccordion>
              <SettingsSection
                id="ai-auto-reply"
                icon={Sparkles}
                accent="violet"
                title="AI Auto-Reply"
                description="Turn on automatic AI replies for inbound WhatsApp messages. Voice delivery is controlled by your operator plan settings."
                status={{ label: aiAutoReplyEnabled ? "On" : "Off", tone: aiAutoReplyEnabled ? "on" : "off" }}
                dirty={aiAutomationDirty}
              >
                <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-border-subtle bg-surface-subtle p-4">
                  <div className="min-w-0">
                    <p className="font-body text-sm font-semibold text-ink">Reply automatically with AI</p>
                    <p className="mt-0.5 font-body text-xs text-ink-muted">
                      When off, inbound messages sit in the inbox until a teammate answers them.
                    </p>
                  </div>
                  <SwitchPill
                    on={aiAutoReplyEnabled}
                    disabled={!canManageSettings}
                    onChange={(next) => setDrafts(d => ({ ...d, [AI_AUTO_REPLY_TOGGLE.key]: next ? "true" : "false" }))}
                  />
                </div>

                <SectionFooter
                  status={
                    <SaveStatus
                      state={saveStates.automations_ai ?? "idle"}
                      dirty={aiAutomationDirty}
                      idleLabel={aiAutoReplyEnabled ? "AI replies are enabled" : "AI replies are disabled"}
                    />
                  }
                >
                  <SaveButton
                    state={saveStates.automations_ai ?? "idle"}
                    dirty={aiAutomationDirty}
                    disabled={!canManageSettings}
                    onClick={() => handleSave("automations_ai", [AI_AUTO_REPLY_TOGGLE.key])}
                  />
                </SectionFooter>
              </SettingsSection>

              <SettingsSection
                id="silence-nudge"
                icon={Timer}
                accent="emerald"
                title="Auto follow-up when a lead goes quiet"
                description="After the AI answers, if the lead stays silent, send one short message about what they were discussing. Never sent while your team has taken over the chat, or during a paid consultation."
                status={{ label: silenceEnabled ? "On" : "Off", tone: silenceEnabled ? "on" : "off" }}
                dirty={silenceDirty}
              >
                <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-border-subtle bg-surface-subtle p-4">
                  <div className="min-w-0">
                    <p className="font-body text-sm font-semibold text-ink">Send a quiet-lead follow-up</p>
                    <p className="mt-0.5 font-body text-xs text-ink-muted">
                      One short nudge per lead, on the topic they were already asking about.
                    </p>
                  </div>
                  <SwitchPill
                    on={silenceEnabled}
                    disabled={!canManageSettings}
                    onChange={(next) => setDrafts(d => ({ ...d, [SILENCE_NUDGE_KEYS.enabled]: next ? "true" : "false" }))}
                  />
                </div>

                {silenceEnabled && (
                  <div className="mt-4 grid gap-4 sm:grid-cols-2">
                    <label className="block">
                      <span className="font-label text-[11px] font-bold uppercase tracking-wider text-ink-muted">
                        Wait time (minutes)
                      </span>
                      <input
                        type="text"
                        inputMode="numeric"
                        disabled={!canManageSettings}
                        value={silenceValue(SILENCE_NUDGE_KEYS.delays)}
                        onChange={e => setDrafts(d => ({ ...d, [SILENCE_NUDGE_KEYS.delays]: e.target.value }))}
                        className={`mt-1.5 w-full rounded-xl border bg-white px-3 py-2 font-body text-sm text-ink transition focus:outline-none focus:ring-2 focus:ring-primary/15 disabled:opacity-60 ${
                          silenceDelaysValid ? "border-border focus:border-primary" : "border-red-400 focus:ring-red-200"
                        }`}
                      />
                      <span className={`mt-1 block font-body text-[11px] ${silenceDelaysValid ? "text-ink-muted" : "text-red-600"}`}>
                        {silenceDelaysValid
                          ? "5 sends one message after 5 minutes. 5,60 adds a second an hour later."
                          : "Up to 3 whole numbers, 1–1440, increasing. e.g. 5 or 5,60"}
                      </span>
                    </label>

                    <label className="block">
                      <span className="font-label text-[11px] font-bold uppercase tracking-wider text-ink-muted">
                        Daily limit per lead
                      </span>
                      <input
                        type="number"
                        min={1}
                        max={10}
                        disabled={!canManageSettings}
                        value={silenceValue(SILENCE_NUDGE_KEYS.cap)}
                        onChange={e => setDrafts(d => ({ ...d, [SILENCE_NUDGE_KEYS.cap]: e.target.value }))}
                        className={`mt-1.5 w-full rounded-xl border bg-white px-3 py-2 font-body text-sm text-ink transition focus:outline-none focus:ring-2 focus:ring-primary/15 disabled:opacity-60 ${
                          silenceCapValid ? "border-border focus:border-primary" : "border-red-400 focus:ring-red-200"
                        }`}
                      />
                      <span className={`mt-1 block font-body text-[11px] ${silenceCapValid ? "text-ink-muted" : "text-red-600"}`}>
                        {silenceCapValid
                          ? "Most follow-ups one lead can get in 24 hours."
                          : "Must be a whole number between 1 and 10."}
                      </span>
                    </label>

                    <label className="block">
                      <span className="font-label text-[11px] font-bold uppercase tracking-wider text-ink-muted">
                        Quiet hours start (IST)
                      </span>
                      <input
                        type="time"
                        disabled={!canManageSettings}
                        value={silenceValue(SILENCE_NUDGE_KEYS.quietStart)}
                        onChange={e => setDrafts(d => ({ ...d, [SILENCE_NUDGE_KEYS.quietStart]: e.target.value }))}
                        className="mt-1.5 w-full rounded-xl border border-border bg-white px-3 py-2 font-body text-sm text-ink transition focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/15 disabled:opacity-60"
                      />
                    </label>

                    <label className="block">
                      <span className="font-label text-[11px] font-bold uppercase tracking-wider text-ink-muted">
                        Quiet hours end (IST)
                      </span>
                      <input
                        type="time"
                        disabled={!canManageSettings}
                        value={silenceValue(SILENCE_NUDGE_KEYS.quietEnd)}
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
                  status={
                    <SaveStatus
                      state={saveStates.automations_silence ?? "idle"}
                      dirty={silenceDirty}
                      idleLabel={silenceEnabled ? "Quiet-lead follow-ups are enabled" : "Quiet-lead follow-ups are off"}
                    />
                  }
                >
                  <SaveButton
                    state={saveStates.automations_silence ?? "idle"}
                    dirty={silenceDirty && silenceDelaysValid && silenceCapValid}
                    disabled={!canManageSettings}
                    onClick={() => handleSave("automations_silence", Object.values(SILENCE_NUDGE_KEYS))}
                  />
                </SectionFooter>
              </SettingsSection>

              <InboxConfigPanel canManage={canManageSettings} />

              <TelecallingConfigPanel canManage={canManageSettings} />

              <IntakeConfigPanel canManage={canManageSettings} />

              <QuickRepliesPanel canManage={canManageSettings} />
            </SettingsAccordion>
          )}

          {/* TAB 6: Notifications */}
          {activeTab === "notifications" && hasNotifications && (
            <SettingsAccordion>
              <BusinessHoursPanel canManage={canManageSettings} />
              <NotificationConfigPanel canManage={canManageSettings} />
            </SettingsAccordion>
          )}

        </div>
      )}
    </div>
  );
}
