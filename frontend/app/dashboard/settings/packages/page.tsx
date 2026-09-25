"use client";
import { useCallback, useEffect, useState } from "react";
import { Package, Plus, Trash2 } from "lucide-react";
import { API_URL, getAuthHeaders } from "@/lib/api";
import { CheckField } from "@/components/ui/controls";
import { useSettingsForm } from "../SettingsFormContext";
import { SaveButton, SaveStatus, SectionFooter, SettingsSection } from "../SettingsSection";
import { slugify } from "../slugify";
import { PackageEditor, type IntakePackage } from "./PackageEditor";

type FieldType = "text" | "date" | "choice";

interface IntakeField {
  key: string;
  label: string;
  type: FieldType;
  options?: string[];
}

// Everything Aira sells and collects in WhatsApp, in one config: this used to be
// split across a "Packages" page and a separate "Paid Intake" panel, which could
// save independently of each other and drift out of sync. `trigger_description`
// and `offer_message` are deliberately absent here -- they're dead fields (only
// the bypassed legacy route_intake ever read them); the backend still accepts
// them on PATCH for backward compatibility, we just never send them.
interface SellConfig {
  enabled: boolean;
  packages: IntakePackage[];
  fields: IntakeField[];
  service_noun: string;
}

const DEFAULT: SellConfig = {
  enabled: false,
  packages: [],
  fields: [],
  service_noun: "consultation",
};

export default function PackagesSettingsPage() {
  const { canManageSettings } = useSettingsForm();
  const [saved, setSaved] = useState<SellConfig>(DEFAULT);
  const [draft, setDraft] = useState<SellConfig>(DEFAULT);
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved">("idle");
  // A failed load leaves saved/draft at DEFAULT (packages: [], fields: []), and an
  // edit on top of that would be a real PATCH that replaces the tenant's actual
  // config with that empty state. Save stays disabled until the GET succeeds.
  const [loaded, setLoaded] = useState(false);
  const [loadFailed, setLoadFailed] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const auth = await getAuthHeaders();
      const res = await fetch(`${API_URL}/api/v1/settings/intake-config`, { headers: auth });
      if (res.ok) {
        const data = await res.json();
        const next: SellConfig = {
          enabled: !!data.enabled,
          packages: data.packages ?? [],
          fields: data.fields ?? [],
          service_noun: data.service_noun ?? "consultation",
        };
        setSaved(next);
        setDraft(next);
        setLoaded(true);
        setLoadFailed(false);
      } else {
        setLoadFailed(true);
      }
    } catch {
      setLoadFailed(true);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const isDirty = JSON.stringify(draft) !== JSON.stringify(saved);

  async function handleSave() {
    if (!canManageSettings || !loaded) return;
    setSaveState("saving");
    setSaveError(null);
    try {
      const auth = await getAuthHeaders();
      const res = await fetch(`${API_URL}/api/v1/settings/intake-config`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", ...auth },
        body: JSON.stringify(draft),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(typeof body?.detail === "string" ? body.detail : "Couldn't save. Please try again.");
      }
      const data = await res.json();
      const next: SellConfig = {
        enabled: !!data.enabled,
        packages: data.packages ?? [],
        fields: data.fields ?? [],
        service_noun: data.service_noun ?? "consultation",
      };
      setSaved(next);
      setDraft(next);
      setSaveState("saved");
      setTimeout(() => setSaveState("idle"), 2000);
    } catch (err: unknown) {
      setSaveError(err instanceof Error ? err.message : "Couldn't save. Please try again.");
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

  return (
    <div className="space-y-4">
      <SettingsSection
        id="what-aira-sells"
        icon={Package}
        accent="violet"
        title="What Aira Sells"
        description="Everything Aira offers and collects in WhatsApp before taking payment — packages, required details, and what to call it, in one place."
        status={{ label: draft.enabled ? "Selling live" : "Off", tone: draft.enabled ? "on" : "off" }}
        dirty={isDirty}
      >
        <div className="space-y-6">
          <div className="rounded-xl border border-primary/15 bg-primary-light/40 p-3.5">
            <p className="font-body text-xs leading-relaxed text-ink-secondary">
              Aira shows the active packages below as tappable buttons the moment a customer is
              ready to buy, and answers any questions they ask in between. It collects the
              details you list here in whatever order the conversation goes — no fixed script —
              and only sends the Razorpay payment link once every detail is in. Prices charged
              are taken exactly from the amounts set below.
            </p>
          </div>

          <CheckField
            checked={draft.enabled}
            disabled={!canManageSettings}
            onChange={(v) => setDraft({ ...draft, enabled: v })}
            label="Let Aira sell these in chat"
            description="Off by default. Turn on once at least one package below is active."
          />

          <div>
            <div className="font-label text-sm font-semibold text-ink mb-1">Packages</div>
            <p className="font-body text-xs text-ink-muted mb-2">
              Aira offers these when the customer shows interest and quotes these exact prices. A
              package can contain sub-options nested to any depth, and a leaf package can offer
              optional addons.
            </p>
            <PackageEditor
              packages={draft.packages}
              onChange={(packages) => setDraft({ ...draft, packages })}
              canManage={canManageSettings}
            />
          </div>

          <div>
            <div className="flex items-center justify-between mb-2">
              <div className="font-label text-sm font-semibold text-ink">Details to collect before payment</div>
              {canManageSettings && (
                <button
                  type="button"
                  onClick={addField}
                  className="inline-flex items-center gap-1 text-xs font-label font-semibold text-primary-600 hover:text-primary-700"
                >
                  <Plus size={14} /> Add field
                </button>
              )}
            </div>
            <p className="font-body text-xs text-ink-muted mb-3">
              Collected in free-flowing conversation, in any order — no fixed script. Applies to
              every package, and the payment link is only sent once all of these are filled in.
            </p>
            <div className="space-y-2">
              {draft.fields.map((field, index) => (
                <div key={index} className="space-y-2 p-3 rounded-xl border border-border bg-surface-subtle">
                  <div className="flex items-center gap-2">
                    <input
                      type="text"
                      placeholder="Label (e.g. Date of birth)"
                      value={field.label}
                      onChange={(e) => updateField(index, { label: e.target.value, key: slugify(e.target.value) })}
                      disabled={!canManageSettings}
                      className="flex-1 px-3 py-1.5 rounded-lg border border-border text-sm font-body text-ink bg-white"
                    />
                    <select
                      value={field.type}
                      onChange={(e) => updateField(index, { type: e.target.value as FieldType })}
                      disabled={!canManageSettings}
                      className="px-3 py-1.5 rounded-lg border border-border text-sm font-body text-ink bg-white"
                    >
                      <option value="text">Text</option>
                      <option value="date">Date</option>
                      <option value="choice">Choice</option>
                    </select>
                    {canManageSettings && (
                      <button type="button" onClick={() => removeField(index)} className="text-ink-muted hover:text-red-600">
                        <Trash2 size={16} />
                      </button>
                    )}
                  </div>
                  {field.type === "choice" && (
                    <input
                      type="text"
                      placeholder="Options, comma separated (e.g. Yes, No, Not sure)"
                      value={(field.options ?? []).join(", ")}
                      onChange={(e) =>
                        updateField(index, {
                          options: e.target.value.split(",").map((s) => s.trim()).filter(Boolean),
                        })
                      }
                      disabled={!canManageSettings}
                      className="w-full px-3 py-1.5 rounded-lg border border-border text-sm font-body text-ink bg-white"
                    />
                  )}
                </div>
              ))}
              {draft.fields.length === 0 && (
                <p className="font-body text-xs text-ink-muted italic">No details needed — Aira sends the payment link as soon as the customer chooses a package.</p>
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
              disabled={!canManageSettings}
              className="w-full px-3 py-1.5 rounded-lg border border-border text-sm font-body text-ink bg-white"
            />
          </div>
        </div>

        <SectionFooter
          status={
            loadFailed || saveError ? (
              <span className="font-body text-[11px] font-semibold text-red-600">
                {loadFailed ? "Couldn't load settings — reload the page before editing." : saveError}
              </span>
            ) : (
              <SaveStatus
                state={saveState}
                dirty={isDirty}
                idleLabel={
                  draft.enabled
                    ? `Selling ${draft.packages.length} package${draft.packages.length === 1 ? "" : "s"}`
                    : "Off"
                }
              />
            )
          }
        >
          <SaveButton state={saveState} dirty={isDirty} disabled={!canManageSettings || !loaded} onClick={handleSave} />
        </SectionFooter>
      </SettingsSection>
    </div>
  );
}
