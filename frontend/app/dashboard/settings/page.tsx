"use client";
import { useEffect, useState, useCallback, useMemo } from "react";
import {
  Phone, Sparkles, Eye, EyeOff, Save, AlertCircle, Loader2, CheckCircle2, ChevronDown, BarChart2
} from "lucide-react";
import { API_URL, getAuthHeaders } from "@/lib/api";
import { useAuthRole } from "../contexts/AuthRoleContext";
import ChangePasswordCard from "./ChangePasswordCard";

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
  const { role, loading: roleLoading } = useAuthRole();
  const [settings, setSettings] = useState<Setting[]>([]);
  const [drafts, setDrafts] = useState<SettingsMap>({});
  const [saveStates, setSaveStates] = useState<Record<string, SaveState>>({});
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

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
        Object.keys(updates).forEach(k => {
          if (settingFor(k)?.is_secret) next[k] = "";
        });
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

  return (
    <div>

      {error && (
        <div className="mb-5 flex items-center gap-2 p-3.5 rounded-2xl bg-red-50 text-red-700 border border-red-100">
          <AlertCircle size={15} />
          <span className="font-body text-sm">{error}</span>
        </div>
      )}

      {loading ? (
        <div className="space-y-5">
          {[...Array(3)].map((_, i) => <div key={i} className="card rounded-3xl h-56 animate-pulse bg-border-subtle" />)}
        </div>
      ) : (
        <div className="space-y-5">
          <ChangePasswordCard />

          {/* Lead Scoring Thresholds */}
          {(() => {
            const isOrderValid = scoringThresholds.A > scoringThresholds.B && scoringThresholds.B > scoringThresholds.C;
            const thresholdColors: Record<string, string> = {
              A: "text-red-700 bg-red-50 border-red-200",
              B: "text-amber-700 bg-amber-50 border-amber-200",
              C: "text-blue-700 bg-blue-50 border-blue-200",
            };
            const thresholdLabels: Record<string, string> = { A: "A — HOT", B: "B — WARM", C: "C — COLD" };
            return (
              <div className="card rounded-3xl">
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

          {SECTIONS.map((section) => {
            const isCollapsed = !!collapsed[section.id];
            const allKeys = [...section.fields.map(f => f.key), ...(section.toggles?.map(t => t.key) ?? [])];
            const requiredFields = section.fields.filter(f => f.required !== false);
            const isConfigured = requiredFields.every(f => settingFor(f.key)?.is_set);
            const saveState = saveStates[section.id] ?? "idle";
            const isDirty = sectionDirty[section.id] ?? false;

            return (
              <div key={section.id} className="card rounded-3xl">
                {/* Header */}
                <button
                  type="button"
                  onClick={() => setCollapsed(c => ({ ...c, [section.id]: !c[section.id] }))}
                  className="w-full flex items-center gap-3 text-left"
                >
                  <div className="w-10 h-10 rounded-2xl flex items-center justify-center flex-shrink-0" style={{ background: section.bg }}>
                    <section.icon size={18} style={{ color: section.color }} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <h2 className="font-display font-bold text-ink" style={{ fontSize: "1rem", letterSpacing: "-0.02em" }}>
                        {section.label}
                      </h2>
                      {isConfigured ? (
                        <span className="badge badge-green inline-flex items-center gap-1">
                          <CheckCircle2 size={10} /> Configured
                        </span>
                      ) : (
                        <span className="badge badge-gray">Not configured</span>
                      )}
                    </div>
                    <p className="font-body text-sm text-ink-muted mt-0.5">{section.description}</p>
                  </div>
                  <ChevronDown size={18} className={`text-ink-muted transition-transform flex-shrink-0 ${isCollapsed ? "" : "rotate-180"}`} />
                </button>

                {!isCollapsed && (
                  <>
                    <div className="mt-6 grid grid-cols-1 md:grid-cols-2 gap-4">
                      {section.fields.map((field) => {
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

                    {section.toggles && section.toggles.length > 0 && (
                      <div className="mt-4 space-y-3">
                        {section.toggles.map((toggle) => {
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

                    {/* Save row */}
                    <div className="mt-6 flex items-center justify-between border-t border-border-subtle pt-5 gap-3 flex-wrap">
                      <div className="min-h-[20px]">
                        {saveState === "saved" && (
                          <span className="inline-flex items-center gap-1.5 text-emerald-600 font-body text-sm font-medium">
                            <CheckCircle2 size={15} /> Saved successfully
                          </span>
                        )}
                        {!isDirty && saveState === "idle" && isConfigured && (
                          <span className="text-[11px] text-ink-muted font-body">No unsaved changes</span>
                        )}
                        {isDirty && saveState !== "saved" && (
                          <span className="text-[11px] text-amber-600 font-body font-medium">Unsaved changes</span>
                        )}
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => handleSave(section.id, allKeys)}
                          disabled={saveState === "saving" || saveState === "saved" || !isDirty}
                          className={`inline-flex items-center gap-2 px-4 py-2 rounded-xl font-label text-sm font-semibold transition-all ${
                            saveState === "saved"
                              ? "bg-emerald-100 text-emerald-700 cursor-default"
                              : isDirty
                              ? "bg-primary text-white hover:bg-primary/90"
                              : "bg-surface-subtle text-ink-muted cursor-default"
                          }`}
                        >
                          {saveState === "saving" ? (
                            <><Loader2 size={14} className="animate-spin" />Saving…</>
                          ) : saveState === "saved" ? (
                            <><CheckCircle2 size={14} />Saved</>
                          ) : (
                            <><Save size={14} />Save Changes</>
                          )}
                        </button>
                      </div>
                    </div>
                  </>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
