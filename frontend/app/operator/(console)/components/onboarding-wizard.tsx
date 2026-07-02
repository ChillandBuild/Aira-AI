"use client";
import { useState, useEffect } from "react";
import { ChevronRight, ChevronLeft, RefreshCw } from "lucide-react";
import { API_URL, getAuthHeaders } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Plan {
  id: string;
  name: string;
  monthly_price: number;
  feature_keys: string[];
  quotas: Record<string, number>;
}

interface OnboardingWizardProps {
  open: boolean;
  onClose: () => void;
  onComplete: () => void;
}

const BUSINESS_TYPES = [
  "Coaching", "Real Estate", "Healthcare", "Agency", "E-commerce", "Other",
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

  const [planId, setPlanId] = useState<string>("");

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  useEffect(() => {
    if (open) {
      apiFetch<{ data: Plan[] }>("/api/v1/operator/plans")
        .then(res => setPlans(res.data ?? []))
        .catch(() => setPlans([]));
      setPassword(generatePassword());
    }
  }, [open]);

  function generatePassword() {
    return "Aira@" + Math.random().toString(36).slice(2, 8);
  }

  const mrr = plans.find(p => p.id === planId)?.monthly_price || 0;

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
          plan_id: planId || null,
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
              {plans.length === 0 ? (
                <div className="rounded-xl border border-dashed border-border p-6 text-center">
                  <p className="text-sm text-ink-secondary">No subscription plans exist yet.</p>
                  <p className="text-xs text-ink-muted mt-1">
                    You can create one from the Subscription page and assign it to this client later.
                  </p>
                </div>
              ) : (
                <div>
                  <label className="text-sm font-medium text-ink-secondary block mb-2">Subscription Plan (optional)</label>
                  <select
                    value={planId}
                    onChange={e => setPlanId(e.target.value)}
                    className="w-full border border-border rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
                  >
                    <option value="">No plan (assign later)</option>
                    {plans.map(p => (
                      <option key={p.id} value={p.id}>{p.name} — ₹{p.monthly_price.toLocaleString("en-IN")}/mo</option>
                    ))}
                  </select>
                </div>
              )}
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
              {/* "Require password change on first login" removed: the backend has no
                  enforcement for it yet, so the checkbox was collected but silently
                  dropped. Re-add once the API supports it. */}
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
                  <span className="text-ink-muted">Subscription Plan:</span>
                  <span className="text-ink font-medium">{plans.find(p => p.id === planId)?.name || "None"}</span>
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