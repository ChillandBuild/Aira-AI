"use client";

import { useEffect, useState } from "react";
import { Building2, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { api, BusinessProfile } from "@/lib/api";
import { SaveButton, SaveStatus, SectionFooter, SettingsSection } from "../SettingsSection";
import { SwitchPill } from "@/components/ui/controls";
import { useSettingsForm } from "../SettingsFormContext";

const EMPTY: BusinessProfile = {
  legal_name: "",
  address: "",
  city: "",
  state: "",
  pincode: "",
  gstin: "",
  email: "",
  phone: "",
  prices_include_gst: true,
};

const GSTIN_PATTERN = /^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$/;

type FieldKey = "legal_name" | "address" | "city" | "state" | "pincode" | "email" | "phone";

const TEXT_FIELDS: { key: FieldKey; label: string; placeholder: string; span?: string }[] = [
  { key: "legal_name", label: "Legal business name", placeholder: "e.g. Aira Bakes Pvt Ltd", span: "sm:col-span-2" },
  { key: "address", label: "Address", placeholder: "Street, area", span: "sm:col-span-2" },
  { key: "city", label: "City", placeholder: "e.g. Coimbatore" },
  { key: "state", label: "State", placeholder: "e.g. Tamil Nadu" },
  { key: "pincode", label: "Pincode", placeholder: "e.g. 641001" },
  { key: "email", label: "Email", placeholder: "billing@yourbusiness.com" },
  { key: "phone", label: "Phone", placeholder: "e.g. 9876543210" },
];

export default function BusinessDetailsSettingsPage() {
  const { canManageSettings } = useSettingsForm();
  const [profile, setProfile] = useState<BusinessProfile>(EMPTY);
  const [draft, setDraft] = useState<BusinessProfile>(EMPTY);
  const [isLoading, setIsLoading] = useState(true);
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved">("idle");
  const [gstinError, setGstinError] = useState<string | null>(null);

  useEffect(() => {
    api.businessProfile
      .get()
      .then((data) => {
        setProfile(data);
        setDraft(data);
      })
      .catch((err) => {
        toast.error(err instanceof Error ? err.message : "Failed to load business details");
      })
      .finally(() => setIsLoading(false));
  }, []);

  const isDirty = JSON.stringify(draft) !== JSON.stringify(profile);

  function setField(key: FieldKey, value: string) {
    setDraft((prev) => ({ ...prev, [key]: value }));
  }

  function handleGstinChange(value: string) {
    const upper = value.toUpperCase();
    setDraft((prev) => ({ ...prev, gstin: upper }));
    setGstinError(upper.trim() && !GSTIN_PATTERN.test(upper.trim()) ? "Doesn't look like a valid GSTIN" : null);
  }

  async function handleSave() {
    if (!canManageSettings) return;
    const gstin = draft.gstin.trim();
    if (gstin && !GSTIN_PATTERN.test(gstin)) {
      setGstinError("Doesn't look like a valid GSTIN");
      return;
    }
    setSaveState("saving");
    try {
      const saved = await api.businessProfile.save({ ...draft, gstin });
      setProfile(saved);
      setDraft(saved);
      setSaveState("saved");
      toast.success("Business details saved");
      setTimeout(() => setSaveState("idle"), 2000);
    } catch (err) {
      setSaveState("idle");
      toast.error(err instanceof Error ? err.message : "Failed to save business details");
    }
  }

  if (isLoading) {
    return (
      <div className="flex min-h-[240px] items-center justify-center">
        <Loader2 size={24} className="animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-2xl font-bold text-ink sm:text-3xl">Business details</h1>
        <p className="mt-2 max-w-2xl font-body text-sm text-ink-muted">
          Printed on your monthly sales file for your auditor.
        </p>
      </div>

      <SettingsSection
        id="business-details"
        icon={Building2}
        accent="violet"
        title="Business details"
        description="Your legal name, address and GSTIN, used on the monthly export for your auditor."
        dirty={isDirty}
      >
        <div className="space-y-5">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {TEXT_FIELDS.map((field) => (
              <div key={field.key} className={field.span}>
                <label className="mb-1.5 block font-label text-[11px] font-bold uppercase tracking-wider text-ink-muted">
                  {field.label}
                </label>
                <input
                  value={draft[field.key]}
                  disabled={!canManageSettings}
                  onChange={(e) => setField(field.key, e.target.value)}
                  placeholder={field.placeholder}
                  className="w-full rounded-xl border border-border bg-white px-3 py-2.5 font-body text-sm text-ink outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/15 disabled:cursor-not-allowed disabled:opacity-60"
                />
              </div>
            ))}
            <div>
              <label className="mb-1.5 block font-label text-[11px] font-bold uppercase tracking-wider text-ink-muted">
                GSTIN
              </label>
              <input
                value={draft.gstin}
                disabled={!canManageSettings}
                onChange={(e) => handleGstinChange(e.target.value)}
                placeholder="e.g. 33AAAAA0000A1Z5"
                maxLength={15}
                className="w-full rounded-xl border border-border bg-white px-3 py-2.5 font-mono text-sm uppercase tracking-wide text-ink outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/15 disabled:cursor-not-allowed disabled:opacity-60"
              />
              {gstinError && <p className="mt-1 text-xs text-danger">{gstinError}</p>}
              {!gstinError && (
                <p className="mt-1 text-xs text-ink-muted">Leave blank if you&apos;re not GST-registered.</p>
              )}
            </div>
          </div>

          <div className="flex items-start justify-between gap-4 rounded-xl border border-border bg-surface-low p-4">
            <div>
              <p className="font-label text-sm font-semibold text-ink">My prices include GST</p>
              <p className="mt-1 max-w-md font-body text-xs leading-relaxed text-ink-muted">
                {draft.prices_include_gst
                  ? "On: a ₹499 price is what the customer pays (tax is inside)."
                  : "Off: GST is added on top at checkout."}
              </p>
            </div>
            <SwitchPill
              on={draft.prices_include_gst}
              disabled={!canManageSettings}
              onChange={(next) => setDraft((prev) => ({ ...prev, prices_include_gst: next }))}
              aria-label="Prices include GST"
            />
          </div>
        </div>

        <SectionFooter status={<SaveStatus state={saveState} dirty={isDirty} />}>
          <SaveButton state={saveState} dirty={isDirty} disabled={!canManageSettings || !!gstinError} onClick={handleSave} />
        </SectionFooter>
      </SettingsSection>
    </div>
  );
}
