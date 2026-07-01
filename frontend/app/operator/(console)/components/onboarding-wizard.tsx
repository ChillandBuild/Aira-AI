"use client";
import { useState, useEffect } from "react";
import { ChevronRight, ChevronLeft, RefreshCw } from "lucide-react";
import { API_URL, getAuthHeaders } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Plan {
  id: string;
  name: string;
  pillar: string;
  tier: string;
  monthly_price: number;
  ai_tier?: string;
  included: {
    feature_keys: string[];
    quotas: Record<string, number>;
  };
}

interface OnboardingWizardProps {
  open: boolean;
  onClose: () => void;
  onComplete: () => void;
}

const BUSINESS_TYPES = [
  "Coaching", "Real Estate", "Healthcare", "Agency", "E-commerce", "Other",
];

const AI_TIERS = [
  { value: "off", label: "Off" },
  { value: "basic", label: "Basic (₹500/1k replies)" },
  { value: "standard", label: "Standard (₹900/1k replies)" },
  { value: "premium", label: "Premium (₹1,500/1k replies)" },
  { value: "byo", label: "BYO Key (₹999/mo)" },
];

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const auth = await getAuthHeaders();
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...auth, ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail || "Request failed");
  }
  return res.json() as Promise<T>;
}

export function OnboardingWizard({ open, onClose, onComplete }: OnboardingWizardProps) {
  const [step, setStep] = useState(1);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [companyName, setCompanyName] = useState("");
  const [businessType, setBusinessType] = useState("");
  const [contactName, setContactName] = useState("");
  const [contactPhone, setContactPhone] = useState("");
  const [billingRegion, setBillingRegion] = useState("");

  const [selectedPillar, setSelectedPillar] = useState<"messaging" | "telecalling" | "both">("messaging");
  const [messagingTier, setMessagingTier] = useState<"basic" | "standard" | "pro">("standard");
  const [telecallingTier, setTelecallingTier] = useState<"basic" | "standard" | "pro">("standard");
  const [aiTier, setAiTier] = useState<string>("off");

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [requireChange, setRequireChange] = useState(true);

  useEffect(() => {
    if (open) {
      apiFetch<Plan[]>("/api/v1/operator/plans").then(setPlans).catch(() => setPlans([]));
      setPassword(generatePassword());
    }
  }, [open]);

  function generatePassword() {
    return "Aira@" + Math.random().toString(36).slice(2, 8);
  }

  function getPrice(pillar: string, tier: string) {
    const plan = plans.find(p => p.pillar === pillar && p.tier === tier);
    return plan?.monthly_price || 0;
  }

  const mrr = (selectedPillar === "messaging" || selectedPillar === "both" ? getPrice("messaging", messagingTier) : 0) +
              (selectedPillar === "telecalling" || selectedPillar === "both" ? getPrice("telecalling", telecallingTier) : 0) +
              (aiTier !== "off" && aiTier !== "byo" ? (aiTier === "basic" ? 500 : aiTier === "standard" ? 900 : 1500) : aiTier === "byo" ? 999 : 0);

  const messagingPlan = plans.find(p => p.pillar === "messaging" && p.tier === messagingTier);
  const telecallingPlan = plans.find(p => p.pillar === "telecalling" && p.tier === telecallingTier);

  async function handleCreate() {
    setSubmitting(true);
    setError(null);
    try {
      await apiFetch("/api/v1/operator/clients", {
        method: "POST",
        body: JSON.stringify({
          company_name: companyName,
          business_type: businessType,
          contact_name: contactName,
          contact_phone: contactPhone,
          billing_region: billingRegion || null,
          email,
          password,
          messaging_plan_id: (selectedPillar === "messaging" || selectedPillar === "both") ? messagingPlan?.id : null,
          telecalling_plan_id: (selectedPillar === "telecalling" || selectedPillar === "both") ? telecallingPlan?.id : null,
          ai_tier: aiTier,
        }),
      });
      onComplete();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create client");
    } finally {
      setSubmitting(false);
    }
  }

  if (!open) return null;

  return (
    <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-card shadow-xl w-full max-w-2xl p-6">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-lg font-bold text-ink">New Client</h2>
          <div className="flex items-center gap-1 text-sm">
            {[1, 2, 3, 4].map(s => (
              <div key={s} className={cn(
                "w-8 h-8 rounded-full flex items-center justify-center text-xs font-medium",
                step === s ? "bg-primary text-white" : step > s ? "bg-success/20 text-success" : "bg-surface-mid text-ink-muted"
              )}>
                {s}
              </div>
            ))}
          </div>
        </div>

        {error && (
          <div className="mb-4 p-3 bg-red-50 border border-danger/20 rounded-lg text-sm text-danger">
            {error}
          </div>
        )}

        <div className="space-y-6">
          {step === 1 && (
            <div className="space-y-4">
              <div>
                <label className="text-sm font-medium text-ink-secondary block mb-1">Company Name *</label>
                <input
                  value={companyName} onChange={e => setCompanyName(e.target.value)} required
                  className="w-full border border-border rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
                  placeholder="ABC Coaching"
                />
              </div>
              <div>
                <label className="text-sm font-medium text-ink-secondary block mb-1">Business Type *</label>
                <select
                  value={businessType} onChange={e => setBusinessType(e.target.value)} required
                  className="w-full border border-border rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
                >
                  <option value="">Select business type</option>
                  {BUSINESS_TYPES.map(bt => <option key={bt} value={bt}>{bt}</option>)}
                </select>
              </div>
              <div>
                <label className="text-sm font-medium text-ink-secondary block mb-1">Primary Contact *</label>
                <input
                  value={contactName} onChange={e => setContactName(e.target.value)} required
                  className="w-full border border-border rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
                  placeholder="John Doe"
                />
              </div>
              <div>
                <label className="text-sm font-medium text-ink-secondary block mb-1">Contact Phone *</label>
                <input
                  value={contactPhone} onChange={e => setContactPhone(e.target.value)} required
                  className="w-full border border-border rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
                  placeholder="+91 98765 43210"
                />
              </div>
              <div>
                <label className="text-sm font-medium text-ink-secondary block mb-1">Billing Region (GST State)</label>
                <input
                  value={billingRegion} onChange={e => setBillingRegion(e.target.value)}
                  className="w-full border border-border rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
                  placeholder="Tamil Nadu"
                />
              </div>
            </div>
          )}

          {step === 2 && (
            <div className="space-y-4">
              <div>
                <label className="text-sm font-medium text-ink-secondary block mb-2">Select Pillar *</label>
                <div className="flex gap-2">
                  {["messaging", "telecalling", "both"].map(p => (
                    <button
                      key={p} type="button"
                      onClick={() => setSelectedPillar(p as any)}
                      className={cn(
                        "flex-1 px-4 py-2 rounded-xl text-sm font-medium transition-all",
                        selectedPillar === p ? "bg-primary text-white" : "bg-surface-mid text-ink-secondary hover:bg-border"
                      )}
                    >
                      {p === "messaging" ? "Messaging Only" : p === "telecalling" ? "Telecalling Only" : "Both"}
                    </button>
                  ))}
                </div>
              </div>

              {(selectedPillar === "messaging" || selectedPillar === "both") && (
                <div>
                  <label className="text-sm font-medium text-ink-secondary block mb-2">Messaging Tier *</label>
                  <div className="grid grid-cols-3 gap-3">
                    {["basic", "standard", "pro"].map(t => (
                      <button
                        key={t} type="button"
                        onClick={() => setMessagingTier(t as any)}
                        className={cn(
                          "p-3 rounded-xl border text-center transition-all",
                          messagingTier === t ? "border-primary bg-primary-light" : "border-border bg-white hover:border-primary-muted"
                        )}
                      >
                        <p className="text-sm font-semibold text-ink capitalize">{t}</p>
                        <p className="text-xs text-primary mt-1">₹{getPrice("messaging", t).toLocaleString("en-IN")}/mo</p>
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {(selectedPillar === "telecalling" || selectedPillar === "both") && (
                <div>
                  <label className="text-sm font-medium text-ink-secondary block mb-2">Telecalling Tier *</label>
                  <div className="grid grid-cols-3 gap-3">
                    {["basic", "standard", "pro"].map(t => (
                      <button
                        key={t} type="button"
                        onClick={() => setTelecallingTier(t as any)}
                        className={cn(
                          "p-3 rounded-xl border text-center transition-all",
                          telecallingTier === t ? "border-primary bg-primary-light" : "border-border bg-white hover:border-primary-muted"
                        )}
                      >
                        <p className="text-sm font-semibold text-ink capitalize">{t}</p>
                        <p className="text-xs text-primary mt-1">₹{getPrice("telecalling", t).toLocaleString("en-IN")}/mo</p>
                      </button>
                    ))}
                  </div>
                </div>
              )}

              <div>
                <label className="text-sm font-medium text-ink-secondary block mb-2">AI Tier *</label>
                <div className="flex gap-2 flex-wrap">
                  {AI_TIERS.map(at => (
                    <button
                      key={at.value} type="button"
                      onClick={() => setAiTier(at.value)}
                      className={cn(
                        "px-3 py-1.5 rounded-full text-xs font-medium transition-all",
                        aiTier === at.value ? "bg-primary text-white" : "bg-surface-mid text-ink-secondary hover:bg-border"
                      )}
                    >
                      {at.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {step === 3 && (
            <div className="space-y-4">
              <div>
                <label className="text-sm font-medium text-ink-secondary block mb-1">Owner Email *</label>
                <input
                  type="email" value={email} onChange={e => setEmail(e.target.value)} required
                  className="w-full border border-border rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
                  placeholder="owner@client.com"
                />
              </div>
              <div>
                <label className="text-sm font-medium text-ink-secondary block mb-1">Temporary Password *</label>
                <div className="flex gap-2">
                  <input
                    type="text" value={password} onChange={e => setPassword(e.target.value)} required
                    className="flex-1 border border-border rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 font-mono"
                  />
                  <button
                    type="button" onClick={() => setPassword(generatePassword())}
                    className="px-3 py-2 border border-border rounded-xl text-sm text-ink-secondary hover:bg-surface-mid"
                    title="Generate new password"
                  >
                    <RefreshCw size={14} />
                  </button>
                </div>
              </div>
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={requireChange} onChange={e => setRequireChange(e.target.checked)}
                  className="rounded border-border" />
                Require password change on first login
              </label>
            </div>
          )}

          {step === 4 && (
            <div className="bg-surface-mid rounded-xl p-4">
              <h3 className="text-sm font-semibold text-ink mb-3">Summary</h3>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-ink-muted">Company:</span>
                  <span className="text-ink font-medium">{companyName || "—"}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-ink-muted">Business Type:</span>
                  <span className="text-ink font-medium">{businessType || "—"}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-ink-muted">Pillar:</span>
                  <span className="text-ink font-medium">{selectedPillar}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-ink-muted">Messaging Tier:</span>
                  <span className="text-ink font-medium capitalize">{messagingTier}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-ink-muted">Telecalling Tier:</span>
                  <span className="text-ink font-medium capitalize">{telecallingTier}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-ink-muted">AI Tier:</span>
                  <span className="text-ink font-medium capitalize">{aiTier}</span>
                </div>
                <div className="border-t border-border pt-2 mt-2">
                  <div className="flex justify-between">
                    <span className="text-ink font-semibold">Estimated MRR:</span>
                    <span className="text-primary font-bold">₹{mrr.toLocaleString("en-IN")}</span>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="flex gap-2 pt-6 mt-6 border-t border-border">
          <button
            type="button"
            onClick={() => step > 1 ? setStep(step - 1) : onClose()}
            className="px-4 py-2 border border-border text-sm text-ink-secondary rounded-lg hover:bg-surface-mid"
          >
            {step > 1 ? <ChevronLeft size={14} className="inline mr-1" /> : null}
            {step > 1 ? "Back" : "Cancel"}
          </button>
          {step < 4 ? (
            <button
              type="button"
              onClick={() => setStep(step + 1)}
              disabled={step === 1 && (!companyName || !businessType || !contactName || !contactPhone)}
              className="flex-1 px-4 py-2 bg-primary text-white text-sm font-medium rounded-lg hover:bg-primary-dark disabled:opacity-50"
            >
              Next <ChevronRight size={14} className="inline ml-1" />
            </button>
          ) : (
            <button
              type="button"
              onClick={handleCreate}
              disabled={submitting || !email || !password}
              className="flex-1 px-4 py-2 bg-primary text-white text-sm font-medium rounded-lg hover:bg-primary-dark disabled:opacity-50"
            >
              {submitting ? "Creating…" : "Create Client"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}