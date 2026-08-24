"use client";
import { useEffect, useState, useCallback } from "react";
import { UserCheck, Plus, Trash2 } from "lucide-react";
import { API_URL, getAuthHeaders } from "@/lib/api";
import { SaveButton, SaveStatus, SectionFooter, SettingsSection } from "./SettingsSection";
import { CheckField } from "@/components/ui/controls";

type FieldType = "text" | "date" | "choice";

interface IntakeField {
  key: string;
  label: string;
  type: FieldType;
  options?: string[];
}

// WhatsApp truncates reply-button titles past 20 chars without erroring, so a
// package whose name is longer needs an explicit short label or it drops out of
// the button menu entirely. Mirrors BUTTON_TITLE_MAX/BUTTON_COUNT_MAX in
// backend/app/services/meta_cloud.py.
const BUTTON_TITLE_MAX = 20;
const BUTTON_COUNT_MAX = 3;

interface IntakePackage {
  key: string;
  name: string;
  amount_paise: number;
  description: string;
  button_label?: string;
}

interface IntakeConfig {
  enabled: boolean;
  trigger_description: string;
  offer_message: string;
  fields: IntakeField[];
  packages: IntakePackage[];
  service_noun: string;
  amount_paise: number;
}

const DEFAULT: IntakeConfig = {
  enabled: false,
  trigger_description: "",
  offer_message: "",
  fields: [],
  packages: [],
  service_noun: "consultation",
  amount_paise: 0,
};

function slugify(label: string): string {
  return label.trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "") || "field";
}

export function IntakeConfigPanel({ canManage = true }: { canManage?: boolean }) {
  const [config, setConfig] = useState<IntakeConfig>(DEFAULT);
  const [draft, setDraft] = useState<IntakeConfig>(DEFAULT);
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved">("idle");

  const load = useCallback(async () => {
    try {
      const auth = await getAuthHeaders();
      const res = await fetch(`${API_URL}/api/v1/settings/intake-config`, { headers: auth });
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
      const res = await fetch(`${API_URL}/api/v1/settings/intake-config`, {
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

  function addField() {
    setDraft({
      ...draft,
      fields: [...draft.fields, { key: `field_${draft.fields.length + 1}`, label: "", type: "text" }],
    });
  }

  function updateField(index: number, patch: Partial<IntakeField>) {
    const fields = draft.fields.map((f, i) => (i === index ? { ...f, ...patch } : f));
    setDraft({ ...draft, fields });
  }

  function removeField(index: number) {
    setDraft({ ...draft, fields: draft.fields.filter((_, i) => i !== index) });
  }

  function addPackage() {
    setDraft({
      ...draft,
      packages: [
        ...draft.packages,
        { key: `package_${draft.packages.length + 1}`, name: "", amount_paise: 0, description: "" },
      ],
    });
  }

  function updatePackage(index: number, patch: Partial<IntakePackage>) {
    const packages = draft.packages.map((p, i) => (i === index ? { ...p, ...patch } : p));
    setDraft({ ...draft, packages });
  }

  function removePackage(index: number) {
    setDraft({ ...draft, packages: draft.packages.filter((_, i) => i !== index) });
  }

  function commitPackageName(index: number, name: string) {
    updatePackage(index, { name, key: slugify(name) || `package_${index + 1}` });
  }

  return (
    <SettingsSection
      id="paid-intake"
      icon={UserCheck}
      accent="violet"
      title="Paid Intake"
      description="Offer a paid consultation in WhatsApp when a lead's message needs a real human expert."
      status={{ label: draft.enabled ? "Enabled" : "Disabled", tone: draft.enabled ? "on" : "off" }}
      dirty={isDirty}
    >
      <div className="space-y-6">
        <CheckField
          checked={draft.enabled}
          disabled={!canManage}
          onChange={(v) => setDraft({ ...draft, enabled: v })}
          label="Enable Paid Intake"
          description="Off by default. Turn on once trigger, fields, and at least one package below are configured."
        />

        <div>
          <div className="font-label text-sm font-semibold text-ink mb-1">When should this trigger?</div>
          <div className="font-body text-xs text-ink-muted mb-2">
            Describe the kind of message that should offer a paid consultation, e.g. &quot;Lead asks a personal astrology question about marriage, career, health, or timing.&quot;
          </div>
          <textarea
            value={draft.trigger_description}
            onChange={(e) => setDraft({ ...draft, trigger_description: e.target.value })}
            rows={3}
            className="w-full px-3 py-2 rounded-xl border border-border text-sm font-body text-ink bg-white"
          />
        </div>

        <div>
          <div className="font-label text-sm font-semibold text-ink mb-1">Offer message</div>
          <div className="font-body text-xs text-ink-muted mb-2">Sent to the lead when the trigger matches.</div>
          <textarea
            value={draft.offer_message}
            onChange={(e) => setDraft({ ...draft, offer_message: e.target.value })}
            rows={2}
            className="w-full px-3 py-2 rounded-xl border border-border text-sm font-body text-ink bg-white"
          />
        </div>

        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <div className="font-label text-sm font-semibold text-ink">Packages</div>
            {canManage && (
              <button
                type="button"
                onClick={addPackage}
                className="inline-flex items-center gap-1 text-xs font-label font-semibold text-violet-600 hover:text-violet-700"
              >
                <Plus size={14} /> Add package
              </button>
            )}
          </div>
          <div className="font-body text-xs text-ink-muted">
            The lead picks one of these right after accepting the offer, before any details are collected.
          </div>

          <div className="space-y-2">
            {draft.packages.map((pkg, index) => (
              <div key={index} className="rounded-2xl border border-border bg-surface-subtle p-3 space-y-2">
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={pkg.name}
                    onChange={(e) => updatePackage(index, { name: e.target.value })}
                    onBlur={(e) => commitPackageName(index, e.target.value)}
                    placeholder="Package name (e.g. VIP)"
                    disabled={!canManage}
                    className="flex-1 px-3 py-1.5 rounded-lg border border-border text-sm font-body text-ink bg-white"
                  />
                  <input
                    type="number"
                    min={1}
                    value={pkg.amount_paise ? pkg.amount_paise / 100 : ""}
                    onChange={(e) =>
                      updatePackage(index, { amount_paise: Math.round(Number(e.target.value) * 100) })
                    }
                    placeholder="₹"
                    disabled={!canManage}
                    className="w-28 px-3 py-1.5 rounded-lg border border-border text-sm font-body text-ink bg-white"
                  />
                  {canManage && (
                    <button type="button" onClick={() => removePackage(index)} aria-label="Remove package" className="text-ink-muted hover:text-red-600">
                      <Trash2 size={16} />
                    </button>
                  )}
                </div>
                <input
                  type="text"
                  value={pkg.description}
                  onChange={(e) => updatePackage(index, { description: e.target.value })}
                  placeholder="What's included (shown to the lead with the price)"
                  disabled={!canManage}
                  className="w-full px-3 py-1.5 rounded-lg border border-border text-sm font-body text-ink bg-white"
                />
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    value={pkg.button_label ?? ""}
                    onChange={(e) =>
                      updatePackage(index, {
                        button_label: e.target.value.slice(0, BUTTON_TITLE_MAX),
                      })
                    }
                    placeholder={
                      pkg.name.length > BUTTON_TITLE_MAX
                        ? "Short button label (required — name is too long)"
                        : "Short button label (optional)"
                    }
                    disabled={!canManage}
                    className="flex-1 px-3 py-1.5 rounded-lg border border-border text-sm font-body text-ink bg-white"
                  />
                  <span
                    className={`font-label text-xs tabular-nums ${
                      (pkg.button_label ?? "").length >= BUTTON_TITLE_MAX
                        ? "text-red-600"
                        : "text-ink-muted"
                    }`}
                  >
                    {(pkg.button_label ?? "").length}/{BUTTON_TITLE_MAX}
                  </span>
                </div>
              </div>
            ))}
            {draft.packages.length > BUTTON_COUNT_MAX && (
              <p className="font-body text-xs text-ink-muted">
                With more than {BUTTON_COUNT_MAX} packages, WhatsApp can&apos;t show tap buttons —
                leads will see the priced list as text and type their choice.
              </p>
            )}
            {draft.packages.length >= 2 &&
              draft.packages.length <= BUTTON_COUNT_MAX &&
              draft.packages.some(
                (p) => !(p.button_label ?? "").trim() && p.name.length > BUTTON_TITLE_MAX,
              ) && (
                <p className="font-body text-xs text-amber-700">
                  One or more package names are longer than {BUTTON_TITLE_MAX} characters and have
                  no short button label — leads will see the text list instead of tap buttons.
                </p>
              )}
            {draft.packages.length === 0 && (
              <p className="font-body text-xs text-ink-muted italic">
                No packages yet — add at least one before enabling.
              </p>
            )}
          </div>
        </div>

        <div className="space-y-1">
          <div className="font-label text-sm font-semibold text-ink">What you call it</div>
          <p className="font-body text-xs text-ink-muted">
            The word used in messages the customer receives — the payment receipt, the Razorpay
            description, and how the assistant refers to it. Example: consultation, reading, session.
          </p>
          <input
            type="text"
            value={draft.service_noun}
            onChange={(e) => setDraft({ ...draft, service_noun: e.target.value })}
            disabled={!canManage}
            className="w-full px-3 py-1.5 rounded-lg border border-border text-sm font-body text-ink bg-white"
          />
        </div>

        <div>
          <div className="flex items-center justify-between mb-2">
            <div className="font-label text-sm font-semibold text-ink">Fields to collect</div>
            <button
              type="button"
              onClick={addField}
              className="inline-flex items-center gap-1 text-xs font-label font-semibold text-violet-600 hover:text-violet-700"
            >
              <Plus size={14} /> Add field
            </button>
          </div>
          <div className="font-body text-xs text-ink-muted mb-3">
            Collected in free-flowing conversation, in any order — no fixed script. Applies to every package.
          </div>
          <div className="space-y-2">
            {draft.fields.map((field, index) => (
              <div key={index} className="flex items-center gap-2 p-3 rounded-xl border border-border bg-surface-subtle">
                <input
                  type="text"
                  placeholder="Label (e.g. Date of birth)"
                  value={field.label}
                  onChange={(e) => updateField(index, { label: e.target.value, key: slugify(e.target.value) })}
                  className="flex-1 px-3 py-1.5 rounded-lg border border-border text-sm font-body text-ink bg-white"
                />
                <select
                  value={field.type}
                  onChange={(e) => updateField(index, { type: e.target.value as FieldType })}
                  className="px-3 py-1.5 rounded-lg border border-border text-sm font-body text-ink bg-white"
                >
                  <option value="text">Text</option>
                  <option value="date">Date</option>
                  <option value="choice">Choice</option>
                </select>
                <button type="button" onClick={() => removeField(index)} className="text-ink-muted hover:text-red-600">
                  <Trash2 size={16} />
                </button>
              </div>
            ))}
            {draft.fields.length === 0 && (
              <p className="font-body text-xs text-ink-muted italic">No fields yet — add at least one before enabling.</p>
            )}
          </div>
        </div>

      </div>

      <SectionFooter status={<SaveStatus state={saveState} dirty={isDirty} idleLabel={draft.enabled ? "Paid intake is live" : "Paid intake is off"} />}>
        <SaveButton state={saveState} dirty={isDirty} disabled={!canManage} onClick={handleSave} />
      </SectionFooter>
    </SettingsSection>
  );
}
