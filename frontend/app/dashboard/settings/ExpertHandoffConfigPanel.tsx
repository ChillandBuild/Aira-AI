"use client";
import { useEffect, useState, useCallback } from "react";
import { UserCheck, ChevronDown, Save, Loader2, CheckCircle2, Plus, Trash2 } from "lucide-react";
import { API_URL, getAuthHeaders } from "@/lib/api";

type FieldType = "text" | "date" | "choice";

interface HandoffField {
  key: string;
  label: string;
  type: FieldType;
  options?: string[];
}

interface ExpertHandoffConfig {
  enabled: boolean;
  trigger_description: string;
  offer_message: string;
  fields: HandoffField[];
  amount_paise: number;
}

const DEFAULT: ExpertHandoffConfig = {
  enabled: false,
  trigger_description: "",
  offer_message: "",
  fields: [],
  amount_paise: 0,
};

function slugify(label: string): string {
  return label.trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "") || "field";
}

export function ExpertHandoffConfigPanel({ canManage = true }: { canManage?: boolean }) {
  const [config, setConfig] = useState<ExpertHandoffConfig>(DEFAULT);
  const [draft, setDraft] = useState<ExpertHandoffConfig>(DEFAULT);
  const [collapsed, setCollapsed] = useState(true);
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved">("idle");

  const load = useCallback(async () => {
    try {
      const auth = await getAuthHeaders();
      const res = await fetch(`${API_URL}/api/v1/settings/expert-handoff-config`, { headers: auth });
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
      const res = await fetch(`${API_URL}/api/v1/settings/expert-handoff-config`, {
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

  function updateField(index: number, patch: Partial<HandoffField>) {
    const fields = draft.fields.map((f, i) => (i === index ? { ...f, ...patch } : f));
    setDraft({ ...draft, fields });
  }

  function removeField(index: number) {
    setDraft({ ...draft, fields: draft.fields.filter((_, i) => i !== index) });
  }

  return (
    <div className="card rounded-3xl">
      <button type="button" onClick={() => setCollapsed((c) => !c)} className="w-full flex items-center gap-3 text-left">
        <div className="w-10 h-10 rounded-2xl flex items-center justify-center flex-shrink-0 bg-violet-100">
          <UserCheck size={18} className="text-violet-600" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h2 className="font-display font-bold text-ink" style={{ fontSize: "1rem", letterSpacing: "-0.02em" }}>
              Paid Expert Handoff
            </h2>
            {draft.enabled ? (
              <span className="badge badge-green inline-flex items-center gap-1">
                <CheckCircle2 size={10} /> Enabled
              </span>
            ) : (
              <span className="badge badge-gray">Disabled</span>
            )}
          </div>
          <p className="font-body text-sm text-ink-muted mt-0.5">
            Offer a paid consultation in WhatsApp when a lead&apos;s message needs a real human expert.
          </p>
        </div>
        <ChevronDown size={18} className={`text-ink-muted transition-transform flex-shrink-0 ${collapsed ? "" : "rotate-180"}`} />
      </button>

      {!collapsed && (
        <div className="mt-6 space-y-6">
          <label className="flex items-start gap-3 p-4 rounded-2xl border border-border bg-surface-subtle cursor-pointer hover:border-violet-300 transition-colors">
            <input
              type="checkbox"
              checked={draft.enabled}
              onChange={(e) => setDraft({ ...draft, enabled: e.target.checked })}
              className="mt-0.5 accent-violet-600"
            />
            <div>
              <div className="font-label text-sm font-semibold text-ink">Enable Paid Expert Handoff</div>
              <div className="font-body text-xs text-ink-muted mt-0.5">
                Off by default. Turn on once trigger, fields, and fee below are configured.
              </div>
            </div>
          </label>

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

          <div>
            <div className="font-label text-sm font-semibold text-ink mb-1">Consultation fee (₹)</div>
            <input
              type="number"
              min={0}
              value={draft.amount_paise / 100}
              onChange={(e) => setDraft({ ...draft, amount_paise: Math.round(Number(e.target.value) * 100) })}
              className="w-32 px-3 py-1.5 rounded-lg border border-border text-sm font-body text-ink bg-white"
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
              Collected in free-flowing conversation, in any order — no fixed script.
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

          <div className="flex justify-end pt-2 border-t border-border">
            <button
              onClick={handleSave}
              disabled={!canManage || saveState === "saving" || saveState === "saved" || !isDirty}
              className={`inline-flex items-center gap-2 px-4 py-2 rounded-xl font-label text-sm font-semibold transition-all ${
                saveState === "saved"
                  ? "bg-emerald-100 text-emerald-700 cursor-default"
                  : canManage && isDirty
                  ? "bg-primary text-white hover:bg-primary/90"
                  : "bg-surface-subtle text-ink-muted cursor-default"
              }`}
            >
              {saveState === "saving" ? (
                <>
                  <Loader2 size={14} className="animate-spin" />
                  Saving…
                </>
              ) : saveState === "saved" ? (
                <>
                  <CheckCircle2 size={14} />
                  Saved
                </>
              ) : (
                <>
                  <Save size={14} />
                  Save Changes
                </>
              )}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
