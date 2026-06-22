"use client";
import { useEffect, useState, useCallback, useMemo } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  Phone, Sparkles, Eye, EyeOff, Save, AlertCircle, Loader2, CheckCircle2, ChevronDown, BarChart2, Crown
} from "lucide-react";
import { API_URL, getAuthHeaders } from "@/lib/api";
import { useAuthRole } from "../contexts/AuthRoleContext";
import ChangePasswordCard from "./ChangePasswordCard";
import ConnectChannelsPanel from "./ConnectChannelsPanel";
import { TelecallingConfigPanel } from "./TelecallingConfigPanel";
import { InboxConfigPanel } from "./InboxConfigPanel";
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
    label: "Voice Calling (TeleCMI)",
    icon: Phone,
    color: "#d97706",
    bg: "#fef3c7",
    description: "TeleCMI credentials for click-to-call telecalling. Per-caller Agent IDs are set on the Team page.",
    fields: [
      { key: "telecmi_secret", label: "App Secret", secret: true, required: true },
      { key: "telecmi_callerid", label: "Caller ID (DID shown to leads)", secret: false, required: false, hint: "The outbound number leads see when you call them" },
      { key: "telecmi_webhook_secret", label: "Webhook Secret", secret: true, required: false, hint: "Appended as ?webhook_secret= to your TeleCMI CDR webhook URL" },
    ],
  },
  {
    id: "ai",
    label: "AI Configuration",
    icon: Sparkles,
    color: "#7c3aed",
    bg: "#ede9fe",
    description: "Groq powers WhatsApp auto-reply, lead scoring, call summaries, and AI coaching.",
    fields: [
      { key: "groq_api_key", label: "Groq API Key", secret: true, required: true },
    ],
    toggles: [
      { key: "ai_auto_reply_enabled", label: "AI Auto-Reply", description: "Automatically reply to inbound WhatsApp messages using AI", defaultEnabled: true },
    ],
  },
];

async function fetchSettings(): Promise<Setting[]> {
  const auth = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/v1/settings`, { headers: auth });
  if (!res.ok) throw new Error("Failed to load settings");
  return (await res.json()).settings;
}

async function saveSettings(updates: SettingsMap): Promise<void> {
  const auth = await getAuthHeaders();
  for (let attempt = 1; attempt <= 2; attempt++) {
    try {
      const res = await fetch(`${API_URL}/api/v1/settings`, {
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
  label, value, onChange, placeholder, type = "text", rightSlot, hint,
}: {
  label: string; value: string; onChange: (v: string) => void;
  placeholder?: string; type?: "text" | "password"; rightSlot?: React.ReactNode; hint?: string;
}) {
  return (
    <div className="space-y-1">
      <div className="relative">
        <input
          type={type}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder ?? " "}
          className="peer w-full px-4 pt-5 pb-2 pr-10 rounded-xl bg-white border border-border text-sm font-body text-ink placeholder:text-ink-muted/40 focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/15 transition"
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
  label, storedMask, isSet, newValue, onChange, hint,
}: {
  label: string; storedMask: string; isSet: boolean;
  newValue: string; onChange: (v: string) => void; hint?: string;
}) {
  const [show, setShow] = useState(false);
  const [editing, setEditing] = useState(false);
  const showInput = editing || newValue.length > 0 || !isSet;

  return (
    <div className="space-y-1">
      {!showInput ? (
        <button type="button" onClick={() => setEditing(true)} className="relative w-full text-left group">
          <div className="w-full px-4 pt-5 pb-2 rounded-xl bg-white border border-border font-mono text-sm text-ink-secondary cursor-text group-hover:border-primary/40 transition">
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
  const activeTab = searchParams.get("tab") || "general";

  const { role, loading: roleLoading } = useAuthRole();
  const [settings, setSettings] = useState<Setting[]>([]);
  const [drafts, setDrafts] = useState<SettingsMap>({});
  const [saveStates, setSaveStates] = useState<Record<string, SaveState>>({});
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  // User Profile details
  const [email, setEmail] = useState<string>("");
  const [fullName, setFullName] = useState<string>("");
  const [createdAt, setCreatedAt] = useState<string>("");

  // Lead Scoring thresholds
  const [scoringThresholds, setScoringThresholds] = useState({ A: 9, B: 7, C: 5 });
  const [scoringState, setScoringState] = useState<SaveState>("idle");
  const [scoringCollapsed, setScoringCollapsed] = useState(false);

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

  useEffect(() => {
    const row = settings.find(s => s.key === "scoring_segment_thresholds");
    if (row && row.display_value && row.display_value !== "Not set") {
      try {
        const t = JSON.parse(row.display_value);
        setScoringThresholds({ A: t.A ?? 9, B: t.B ?? 7, C: t.C ?? 5 });
      } catch { /* ignore parse error */ }
    }
  }, [settings]);

  const initials = fullName.split(" ").map((n) => n[0]).join("").toUpperCase().slice(0, 2) || "AD";
  const memberSince = createdAt ? new Date(createdAt).toLocaleDateString("en-IN", { month: "long", year: "numeric" }) : null;

  async function handleScoringThresholdsSave() {
    const isOrderValid = scoringThresholds.A > scoringThresholds.B && scoringThresholds.B > scoringThresholds.C;
    if (!isOrderValid) return;
    setScoringState("saving");
    try {
      await saveSettings({ scoring_segment_thresholds: JSON.stringify(scoringThresholds) });
      await load();
      setScoringState("saved");
      setTimeout(() => setScoringState("idle"), 2500);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
      setScoringState("idle");
    }
  }

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

  async function handleSave(sectionId: string, allKeys: string[]) {
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

  if (role !== "owner") {
    return (
      <div>
        <ChangePasswordCard />
      </div>
    );
  }

  // Find Configured/Not configured statuses for sections
  const voiceSection = SECTIONS.find(s => s.id === "voice")!;
  const voiceConfigured = voiceSection.fields.filter(f => f.required !== false).every(f => settingFor(f.key)?.is_set);

  const aiSection = SECTIONS.find(s => s.id === "ai")!;
  const aiConfigured = aiSection.fields.filter(f => f.required !== false).every(f => settingFor(f.key)?.is_set);

  return (
    <div>
      {/* Curved Tab Switcher */}
      <div className="mb-6 flex gap-1 p-1 bg-[#e8e3db]/60 rounded-2xl self-start w-fit">
        <button
          onClick={() => router.push(`${pathname}?tab=general`)}
          className={cn(
            "px-5 py-2.5 rounded-xl font-label text-xs font-bold transition-all",
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
            "px-5 py-2.5 rounded-xl font-label text-xs font-bold transition-all",
            activeTab === "channels"
              ? "bg-white text-primary shadow-sm"
              : "text-[#78716c] hover:text-[#292524]"
          )}
        >
          Messaging Channels
        </button>
        <button
          onClick={() => router.push(`${pathname}?tab=telecalling`)}
          className={cn(
            "px-5 py-2.5 rounded-xl font-label text-xs font-bold transition-all",
            activeTab === "telecalling"
              ? "bg-white text-primary shadow-sm"
              : "text-[#78716c] hover:text-[#292524]"
          )}
        >
          Telecalling Config
        </button>
        <button
          onClick={() => router.push(`${pathname}?tab=ai`)}
          className={cn(
            "px-5 py-2.5 rounded-xl font-label text-xs font-bold transition-all",
            activeTab === "ai"
              ? "bg-white text-primary shadow-sm"
              : "text-[#78716c] hover:text-[#292524]"
          )}
        >
          AI Settings
        </button>
        <button
          onClick={() => router.push(`${pathname}?tab=automations`)}
          className={cn(
            "px-5 py-2.5 rounded-xl font-label text-xs font-bold transition-all",
            activeTab === "automations"
              ? "bg-white text-primary shadow-sm"
              : "text-[#78716c] hover:text-[#292524]"
          )}
        >
          Automations
        </button>
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
              <div className="bg-gradient-to-br from-[#1c1917] via-[#292524] to-[#1c1917] rounded-[2rem] p-8 shadow-xl relative overflow-hidden">
                <div className="absolute top-0 right-0 w-64 h-64 bg-gradient-to-bl from-primary/10 to-transparent rounded-full -translate-y-1/2 translate-x-1/3" />
                <div className="absolute bottom-0 left-0 w-48 h-48 bg-gradient-to-tr from-amber-500/10 to-transparent rounded-full translate-y-1/2 -translate-x-1/4" />

                <div className="relative flex items-center gap-6">
                  <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-[#2e1065] to-primary flex items-center justify-center shadow-lg shadow-primary/25">
                    <span className="font-display text-3xl font-bold text-white">{initials}</span>
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-3 flex-wrap">
                      <h2 className="font-display text-2xl font-bold text-white">{fullName}</h2>
                      <span className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-amber-500/15 border border-amber-500/30">
                        <Crown size={12} className="text-amber-400" />
                        <span className="font-label text-xs font-bold text-amber-300 uppercase tracking-wider">Admin</span>
                      </span>
                    </div>
                    {email && (
                      <p className="font-body text-sm text-[#a8a29e] mt-1">{email}</p>
                    )}
                    <div className="flex items-center gap-4 mt-3">
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

          {/* TAB 2: Messaging Channels */}
          {activeTab === "channels" && <ConnectChannelsPanel />}

          {/* TAB 3: Telecalling Config */}
          {activeTab === "telecalling" && (
            <div className="space-y-6">
              {/* TeleCMI Credentials Card */}
              <div className="card rounded-3xl animate-slide-up">
                <button
                  type="button"
                  onClick={() => setCollapsed(c => ({ ...c, voice: !c.voice }))}
                  className="w-full flex items-center gap-3 text-left"
                >
                  <div className="w-10 h-10 rounded-2xl flex items-center justify-center flex-shrink-0" style={{ background: voiceSection.bg }}>
                    <voiceSection.icon size={18} style={{ color: voiceSection.color }} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <h2 className="font-display font-bold text-ink" style={{ fontSize: "1rem", letterSpacing: "-0.02em" }}>
                        {voiceSection.label}
                      </h2>
                      {voiceConfigured ? (
                        <span className="badge badge-green inline-flex items-center gap-1">
                          <CheckCircle2 size={10} /> Configured
                        </span>
                      ) : (
                        <span className="badge badge-gray">Not configured</span>
                      )}
                    </div>
                    <p className="font-body text-sm text-ink-muted mt-0.5">{voiceSection.description}</p>
                  </div>
                  <ChevronDown size={18} className={`text-ink-muted transition-transform flex-shrink-0 ${collapsed.voice ? "" : "rotate-180"}`} />
                </button>

                {!collapsed.voice && (
                  <>
                    <div className="mt-6 grid grid-cols-1 md:grid-cols-2 gap-4">
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
                          />
                        );
                      })}
                    </div>

                    {/* TeleCMI Webhook URL + Setup Guide */}
                    <div className="mt-5 p-3.5 rounded-2xl bg-[#faf8f5] border border-[#e8e3db] text-xs font-body space-y-2">
                      <p className="font-label font-bold text-[#44403c] uppercase text-[10px] tracking-wider">Setup Guide</p>
                      <ol className="list-decimal list-inside space-y-1 text-[#57534e]">
                        <li>Log in to your <span className="font-semibold">TeleCMI dashboard</span> → Settings → Webhook</li>
                        <li>Set CDR Webhook URL to:<br />
                          <code className="mt-1 inline-block px-2 py-1 bg-white border border-[#e8e3db] rounded text-[11px] text-[#292524] font-mono select-all break-all">
                            https://aira-ai-5tfr.onrender.com/api/v1/calls/telecmi-cdr
                          </code>
                        </li>
                        <li>If using a Webhook Secret, append it: <code className="px-1 py-0.5 bg-white border border-[#e8e3db] rounded text-[10px] font-mono">?webhook_secret=YOUR_SECRET</code></li>
                        <li>Set your <span className="font-semibold">App Secret</span> above (from TeleCMI dashboard → API Keys)</li>
                        <li>Per-caller <span className="font-semibold">Agent IDs</span> are configured on the <span className="font-semibold">Team page</span></li>
                      </ol>
                    </div>

                    <div className="mt-6 flex items-center justify-between border-t border-border-subtle pt-5 gap-3 flex-wrap">
                      <div className="min-h-[20px]">
                        {(saveStates.voice ?? "idle") === "saved" && (
                          <span className="inline-flex items-center gap-1.5 text-emerald-600 font-body text-sm font-medium">
                            <CheckCircle2 size={15} /> Saved successfully
                          </span>
                        )}
                        {!(sectionDirty.voice ?? false) && (saveStates.voice ?? "idle") === "idle" && voiceConfigured && (
                          <span className="text-[11px] text-ink-muted font-body">No unsaved changes</span>
                        )}
                        {(sectionDirty.voice ?? false) && (saveStates.voice ?? "idle") !== "saved" && (
                          <span className="text-[11px] text-amber-600 font-body font-medium">Unsaved changes</span>
                        )}
                      </div>
                      <button
                        onClick={() => handleSave("voice", voiceSection.fields.map(f => f.key))}
                        disabled={(saveStates.voice ?? "idle") === "saving" || (saveStates.voice ?? "idle") === "saved" || !(sectionDirty.voice ?? false)}
                        className={`inline-flex items-center gap-2 px-4 py-2 rounded-xl font-label text-sm font-semibold transition-all ${
                          (saveStates.voice ?? "idle") === "saved"
                            ? "bg-emerald-100 text-emerald-700 cursor-default"
                            : (sectionDirty.voice ?? false)
                            ? "bg-primary text-white hover:bg-primary/90"
                            : "bg-surface-subtle text-ink-muted cursor-default"
                        }`}
                      >
                        {(saveStates.voice ?? "idle") === "saving" ? (
                          <><Loader2 size={14} className="animate-spin" />Saving…</>
                        ) : (saveStates.voice ?? "idle") === "saved" ? (
                          <><CheckCircle2 size={14} />Saved</>
                        ) : (
                          <><Save size={14} />Save Changes</>
                        )}
                      </button>
                    </div>
                  </>
                )}
              </div>
            </div>
          )}

          {/* TAB 4: AI Settings */}
          {activeTab === "ai" && (
            <div className="space-y-6">
              {/* Groq AI Credentials Card */}
              <div className="card rounded-3xl animate-slide-up">
                <button
                  type="button"
                  onClick={() => setCollapsed(c => ({ ...c, ai: !c.ai }))}
                  className="w-full flex items-center gap-3 text-left"
                >
                  <div className="w-10 h-10 rounded-2xl flex items-center justify-center flex-shrink-0" style={{ background: aiSection.bg }}>
                    <aiSection.icon size={18} style={{ color: aiSection.color }} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <h2 className="font-display font-bold text-ink" style={{ fontSize: "1rem", letterSpacing: "-0.02em" }}>
                        {aiSection.label}
                      </h2>
                      {aiConfigured ? (
                        <span className="badge badge-green inline-flex items-center gap-1">
                          <CheckCircle2 size={10} /> Configured
                        </span>
                      ) : (
                        <span className="badge badge-gray">Not configured</span>
                      )}
                    </div>
                    <p className="font-body text-sm text-ink-muted mt-0.5">{aiSection.description}</p>
                  </div>
                  <ChevronDown size={18} className={`text-ink-muted transition-transform flex-shrink-0 ${collapsed.ai ? "" : "rotate-180"}`} />
                </button>

                {!collapsed.ai && (
                  <>
                    <div className="mt-6 grid grid-cols-1 md:grid-cols-2 gap-4">
                      {aiSection.fields.map((field) => {
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
                          />
                        );
                      })}
                    </div>

                    {aiSection.toggles && aiSection.toggles.length > 0 && (
                      <div className="mt-4 space-y-3">
                        {aiSection.toggles.map((toggle) => {
                          const val = drafts[toggle.key];
                          const stored = settingFor(toggle.key)?.display_value;
                          const isDefaultEnabled = toggle.defaultEnabled !== false;
                          const enabled = val !== undefined
                            ? val === "true"
                            : (stored === "Not set" || !stored ? isDefaultEnabled : stored === "true");
                          return (
                            <div key={toggle.key} className="flex items-center justify-between p-4 rounded-2xl bg-surface-subtle border border-border-subtle">
                              <div>
                                <p className="font-body text-sm font-semibold text-ink">{toggle.label}</p>
                                <p className="font-body text-xs text-ink-muted mt-0.5">{toggle.description}</p>
                              </div>
                              <button
                                type="button"
                                onClick={() => {
                                  const nextVal = enabled ? "false" : "true";
                                  setDrafts(d => ({ ...d, [toggle.key]: nextVal }));
                                }}
                                className={`relative w-11 h-6 rounded-full transition-colors duration-200 flex-shrink-0 ${enabled ? "bg-green-600" : "bg-gray-300"}`}
                              >
                                <span className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow-sm transition-transform duration-200 ${enabled ? "translate-x-5" : "translate-x-0"}`} />
                              </button>
                            </div>
                          );
                        })}
                      </div>
                    )}

                    <div className="mt-6 flex items-center justify-between border-t border-border-subtle pt-5 gap-3 flex-wrap">
                      <div className="min-h-[20px]">
                        {(saveStates.ai ?? "idle") === "saved" && (
                          <span className="inline-flex items-center gap-1.5 text-emerald-600 font-body text-sm font-medium">
                            <CheckCircle2 size={15} /> Saved successfully
                          </span>
                        )}
                        {!(sectionDirty.ai ?? false) && (saveStates.ai ?? "idle") === "idle" && aiConfigured && (
                          <span className="text-[11px] text-ink-muted font-body">No unsaved changes</span>
                        )}
                        {(sectionDirty.ai ?? false) && (saveStates.ai ?? "idle") !== "saved" && (
                          <span className="text-[11px] text-amber-600 font-body font-medium">Unsaved changes</span>
                        )}
                      </div>
                      <button
                        onClick={() => handleSave("ai", [...aiSection.fields.map(f => f.key), ...(aiSection.toggles?.map(t => t.key) ?? [])])}
                        disabled={(saveStates.ai ?? "idle") === "saving" || (saveStates.ai ?? "idle") === "saved" || !(sectionDirty.ai ?? false)}
                        className={`inline-flex items-center gap-2 px-4 py-2 rounded-xl font-label text-sm font-semibold transition-all ${
                          (saveStates.ai ?? "idle") === "saved"
                            ? "bg-emerald-100 text-emerald-700 cursor-default"
                            : (sectionDirty.ai ?? false)
                            ? "bg-primary text-white hover:bg-primary/90"
                            : "bg-surface-subtle text-ink-muted cursor-default"
                        }`}
                      >
                        {(saveStates.ai ?? "idle") === "saving" ? (
                          <><Loader2 size={14} className="animate-spin" />Saving…</>
                        ) : (saveStates.ai ?? "idle") === "saved" ? (
                          <><CheckCircle2 size={14} />Saved</>
                        ) : (
                          <><Save size={14} />Save Changes</>
                        )}
                      </button>
                    </div>
                  </>
                )}
              </div>
            </div>
          )}

          {/* TAB 5: Automations */}
          {activeTab === "automations" && (
            <div className="space-y-6">
              {/* Lead Scoring thresholds */}
              {(() => {
                const isOrderValid = scoringThresholds.A > scoringThresholds.B && scoringThresholds.B > scoringThresholds.C;
                const thresholdColors: Record<string, string> = {
                  A: "text-red-700 bg-red-50 border-red-200",
                  B: "text-amber-700 bg-amber-50 border-amber-200",
                  C: "text-blue-700 bg-blue-50 border-blue-200",
                };
                const thresholdLabels: Record<string, string> = { A: "A — HOT", B: "B — WARM", C: "C — COLD" };
                return (
                  <div className="card rounded-3xl animate-slide-up">
                    <button
                      type="button"
                      onClick={() => setScoringCollapsed(c => !c)}
                      className="w-full flex items-center gap-3 text-left"
                    >
                      <div className="w-10 h-10 rounded-2xl flex items-center justify-center flex-shrink-0" style={{ background: "#ede9fe" }}>
                        <BarChart2 size={18} style={{ color: "#7c3aed" }} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <h2 className="font-display font-bold text-ink" style={{ fontSize: "1rem", letterSpacing: "-0.02em" }}>
                            Lead Scoring
                          </h2>
                          <span className="badge badge-green inline-flex items-center gap-1">
                            <CheckCircle2 size={10} /> Configured
                          </span>
                        </div>
                        <p className="font-body text-sm text-ink-muted mt-0.5">Segment thresholds for A/B/C lead classification. Scoring rubric is in AI Tune.</p>
                      </div>
                      <ChevronDown size={18} className={`text-ink-muted transition-transform flex-shrink-0 ${scoringCollapsed ? "" : "rotate-180"}`} />
                    </button>

                    {!scoringCollapsed && (
                      <>
                        <div className="mt-6 space-y-3">
                          <p className="font-body text-xs text-ink-muted">
                            Leads are grouped when score is ≥ threshold. Default: A≥9, B≥7, C≥5, D&lt;5.
                          </p>
                          <div className="grid grid-cols-1 gap-2">
                            {(["A", "B", "C"] as const).map((seg) => (
                              <div key={seg} className={`rounded-xl border p-3 flex items-center justify-between ${thresholdColors[seg]}`}>
                                <label className="font-label text-xs font-bold uppercase">{thresholdLabels[seg]}</label>
                                <div className="flex items-center gap-1.5">
                                  <span className="font-label text-xs">Score ≥</span>
                                  <input
                                    type="number"
                                    min={1}
                                    max={10}
                                    value={scoringThresholds[seg]}
                                    onChange={(e) => {
                                      const v = Math.max(1, Math.min(10, parseInt(e.target.value) || 1));
                                      setScoringThresholds(prev => ({ ...prev, [seg]: v }));
                                      setScoringState("dirty");
                                    }}
                                    className="w-12 px-1.5 py-0.5 rounded border bg-white font-mono text-xs font-bold text-center focus:outline-none focus:ring-1 focus:ring-current text-ink"
                                  />
                                </div>
                              </div>
                            ))}
                          </div>
                          {!isOrderValid && (
                            <div className="flex items-start gap-1.5 p-3 rounded-xl bg-red-50 border border-red-200 text-red-700 font-label text-xs font-semibold">
                              <AlertCircle size={13} className="mt-0.5 shrink-0" />
                              <span>Thresholds must be in order: A &gt; B &gt; C.</span>
                            </div>
                          )}
                          <p className="font-label text-[10px] text-ink-muted">
                            D (Disqualified) = score below C threshold ({scoringThresholds.C - 1} or less).
                          </p>
                        </div>

                        <div className="mt-6 flex items-center justify-between border-t border-border-subtle pt-5 gap-3 flex-wrap">
                          <div className="min-h-[20px]">
                            {scoringState === "saved" && (
                              <span className="inline-flex items-center gap-1.5 text-emerald-600 font-body text-sm font-medium">
                                <CheckCircle2 size={15} /> Saved successfully
                              </span>
                            )}
                            {scoringState === "dirty" && (
                              <span className="text-[11px] text-amber-600 font-body font-medium">Unsaved changes</span>
                            )}
                            {(scoringState === "idle" || scoringState === "saving") && (
                              <span className="text-[11px] text-ink-muted font-body">Default: A≥9, B≥7, C≥5</span>
                            )}
                          </div>
                          <button
                            onClick={handleScoringThresholdsSave}
                            disabled={scoringState === "saving" || scoringState === "saved" || !isOrderValid || scoringState === "idle"}
                            className={`inline-flex items-center gap-2 px-4 py-2 rounded-xl font-label text-sm font-semibold transition-all ${
                              scoringState === "saved"
                                ? "bg-emerald-100 text-emerald-700 cursor-default"
                                : scoringState === "dirty" && isOrderValid
                                ? "bg-primary text-white hover:bg-primary/90"
                                : "bg-surface-subtle text-ink-muted cursor-default"
                            }`}
                          >
                            {scoringState === "saving" ? (
                              <><Loader2 size={14} className="animate-spin" />Saving…</>
                            ) : scoringState === "saved" ? (
                              <><CheckCircle2 size={14} />Saved</>
                            ) : (
                              <><Save size={14} />Save Changes</>
                            )}
                          </button>
                        </div>
                      </>
                    )}
                  </div>
                );
              })()}

              <InboxConfigPanel />

              <TelecallingConfigPanel />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
