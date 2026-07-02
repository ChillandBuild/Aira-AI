"use client";
import { useCallback, useEffect, useState } from "react";
import { CreditCard, Plus, Pencil, Trash2, Users, MessageSquare, Zap, Brain, Phone, Cog, Settings2 } from "lucide-react";
import { operatorFetch } from "@/lib/operator";

interface FeatureCatalogItem {
  feature_key: string;
  display_name: string;
  category: string;
}

interface Plan {
  id: string;
  name: string;
  monthly_price: number;
  feature_keys: string[];
  quotas: Record<string, number>;
  active: boolean;
  created_at: string;
  tenant_count: number;
}

const CATEGORY_LABELS: Record<string, string> = {
  channels: "Channels",
  messaging: "Messaging",
  ai: "AI",
  telecalling: "Telecalling",
  automation: "Automation",
  ops: "Ops",
};

const CATEGORY_ICONS: Record<string, typeof MessageSquare> = {
  channels: MessageSquare,
  messaging: Zap,
  ai: Brain,
  telecalling: Phone,
  automation: Cog,
  ops: Settings2,
};

const QUOTA_METRICS: { key: string; label: string }[] = [
  { key: "message_sent", label: "Messages / mo" },
  { key: "ai_reply", label: "AI Replies / mo" },
  { key: "call_minute", label: "Call Minutes / mo" },
  { key: "team_seat_active", label: "Team Seats" },
  { key: "storage_gb", label: "Storage (GB)" },
  { key: "ai_call_summary", label: "AI Call Summaries / mo" },
  { key: "ai_call_scoring", label: "AI Call Scoring / mo" },
];

interface PlanFormState {
  id: string | null;
  name: string;
  monthly_price: string;
  feature_keys: Set<string>;
  quotas: Record<string, string>;
}

function emptyForm(): PlanFormState {
  return { id: null, name: "", monthly_price: "", feature_keys: new Set(), quotas: {} };
}

export default function SubscriptionPage() {
  const [plans, setPlans] = useState<Plan[]>([]);
  const [catalog, setCatalog] = useState<FeatureCatalogItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<PlanFormState | null>(null);
  const [saving, setSaving] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Plan | null>(null);
  const [deleting, setDeleting] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    return Promise.all([
      operatorFetch<{ data: Plan[] }>("/api/v1/operator/plans"),
      operatorFetch<{ data: FeatureCatalogItem[] } | FeatureCatalogItem[]>("/api/v1/operator/features/catalog"),
    ])
      .then(([plansRes, catalogRes]) => {
        setPlans(plansRes.data ?? []);
        setCatalog(Array.isArray(catalogRes) ? catalogRes : catalogRes.data ?? []);
        setError(null);
      })
      .catch(e => setError(e instanceof Error ? e.message : "Request failed"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const catalogByCategory = catalog.reduce<Record<string, FeatureCatalogItem[]>>((acc, f) => {
    if (!acc[f.category]) acc[f.category] = [];
    acc[f.category].push(f);
    return acc;
  }, {});

  function openCreate() {
    setForm(emptyForm());
  }

  function openEdit(plan: Plan) {
    const quotas: Record<string, string> = {};
    for (const metric of QUOTA_METRICS) {
      const value = plan.quotas[metric.key];
      quotas[metric.key] = value ? String(value) : "";
    }
    setForm({
      id: plan.id,
      name: plan.name,
      monthly_price: String(plan.monthly_price),
      feature_keys: new Set(plan.feature_keys),
      quotas,
    });
  }

  function toggleFeature(key: string) {
    setForm(prev => {
      if (!prev) return prev;
      const next = new Set(prev.feature_keys);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return { ...prev, feature_keys: next };
    });
  }

  function setQuota(key: string, value: string) {
    setForm(prev => (prev ? { ...prev, quotas: { ...prev.quotas, [key]: value } } : prev));
  }

  async function handleSave() {
    if (!form || !form.name.trim()) return;
    setSaving(true);
    setError(null);
    const quotas: Record<string, number> = {};
    for (const metric of QUOTA_METRICS) {
      const raw = form.quotas[metric.key];
      const parsed = raw ? parseInt(raw, 10) : 0;
      if (parsed > 0) quotas[metric.key] = parsed;
    }
    const payload = {
      name: form.name.trim(),
      monthly_price: parseFloat(form.monthly_price) || 0,
      feature_keys: Array.from(form.feature_keys),
      quotas,
    };
    try {
      if (form.id) {
        await operatorFetch(`/api/v1/operator/plans/${form.id}`, { method: "PATCH", body: JSON.stringify(payload) });
      } else {
        await operatorFetch("/api/v1/operator/plans", { method: "POST", body: JSON.stringify(payload) });
      }
      setForm(null);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save plan");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await operatorFetch(`/api/v1/operator/plans/${deleteTarget.id}`, { method: "DELETE" });
      setDeleteTarget(null);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete plan");
    } finally {
      setDeleting(false);
    }
  }

  if (loading) {
    return <div className="p-7 text-sm text-ink-muted">Loading plans…</div>;
  }

  return (
    <div className="p-7 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-lg font-bold text-ink">Subscription Plans</h1>
          <p className="text-xs text-ink-muted mt-0.5">Create and edit the plans tenants can be assigned to.</p>
        </div>
        <button
          onClick={openCreate}
          className="flex items-center gap-1.5 px-4 py-2 bg-primary text-white text-sm font-medium rounded-xl hover:bg-primary-dark transition-colors"
        >
          <Plus size={15} /> New Plan
        </button>
      </div>

      {error && (
        <div className="p-3 bg-red-50 border border-danger/20 rounded-xl text-sm text-danger">{error}</div>
      )}

      {plans.length === 0 ? (
        <div className="rounded-card border border-dashed border-border p-10 text-center">
          <CreditCard size={28} className="mx-auto text-ink-muted mb-3" />
          <p className="text-sm font-medium text-ink">No plans yet</p>
          <p className="text-xs text-ink-muted mt-1">Create the first plan to start assigning it to tenants.</p>
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {plans.map(plan => (
            <div key={plan.id} className="bg-white rounded-card border border-border p-5 shadow-sm">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <h3 className="text-sm font-semibold text-ink">{plan.name}</h3>
                  <p className="text-lg font-bold text-primary mt-1">
                    ₹{plan.monthly_price.toLocaleString("en-IN")}
                    <span className="text-xs font-medium text-ink-muted">/mo</span>
                  </p>
                </div>
                <div className="flex items-center gap-1">
                  <button onClick={() => openEdit(plan)} className="p-1.5 rounded-lg text-ink-muted hover:bg-surface-mid hover:text-ink" title="Edit plan">
                    <Pencil size={14} />
                  </button>
                  <button onClick={() => setDeleteTarget(plan)} className="p-1.5 rounded-lg text-ink-muted hover:bg-red-50 hover:text-danger" title="Delete plan">
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
              <p className="text-xs text-ink-muted mt-3">{plan.feature_keys.length} features included</p>
              <p className="text-xs text-ink-muted mt-1 flex items-center gap-1">
                <Users size={12} /> {plan.tenant_count} tenant{plan.tenant_count === 1 ? "" : "s"} assigned
              </p>
            </div>
          ))}
        </div>
      )}

      {form && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-card shadow-xl w-full max-w-2xl max-h-[85vh] overflow-y-auto p-6">
            <h2 className="text-lg font-bold text-ink mb-4">{form.id ? "Edit Plan" : "New Plan"}</h2>
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-sm font-medium text-ink-secondary block mb-1">Plan Name *</label>
                  <input
                    value={form.name}
                    onChange={e => setForm(prev => (prev ? { ...prev, name: e.target.value } : prev))}
                    className="w-full border border-border rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
                    placeholder="Growth"
                  />
                </div>
                <div>
                  <label className="text-sm font-medium text-ink-secondary block mb-1">Monthly Price (₹) *</label>
                  <input
                    type="number"
                    min="0"
                    value={form.monthly_price}
                    onChange={e => setForm(prev => (prev ? { ...prev, monthly_price: e.target.value } : prev))}
                    className="w-full border border-border rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
                    placeholder="9999"
                  />
                </div>
              </div>

              <div>
                <label className="text-sm font-medium text-ink-secondary block mb-2">Usage Quotas</label>
                <div className="grid grid-cols-2 gap-3">
                  {QUOTA_METRICS.map(metric => (
                    <div key={metric.key}>
                      <label className="text-xs text-ink-muted block mb-1">{metric.label}</label>
                      <input
                        type="number"
                        min="0"
                        value={form.quotas[metric.key] ?? ""}
                        onChange={e => setQuota(metric.key, e.target.value)}
                        className="w-full border border-border rounded-xl px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
                        placeholder="0"
                      />
                    </div>
                  ))}
                </div>
              </div>

              <div>
                <label className="text-sm font-medium text-ink-secondary block mb-2">Features Included</label>
                <div className="space-y-4 max-h-64 overflow-y-auto border border-border rounded-xl p-3">
                  {Object.entries(catalogByCategory).map(([category, features]) => {
                    const Icon = CATEGORY_ICONS[category] || Zap;
                    return (
                      <div key={category}>
                        <p className="text-xs font-semibold text-ink-muted uppercase tracking-wide flex items-center gap-1.5 mb-1.5">
                          <Icon size={12} /> {CATEGORY_LABELS[category] || category}
                        </p>
                        <div className="grid grid-cols-2 gap-1.5">
                          {features.map(f => (
                            <label key={f.feature_key} className="flex items-center gap-2 text-sm text-ink-secondary cursor-pointer">
                              <input
                                type="checkbox"
                                checked={form.feature_keys.has(f.feature_key)}
                                onChange={() => toggleFeature(f.feature_key)}
                                className="rounded border-border"
                              />
                              {f.display_name}
                            </label>
                          ))}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>

            <div className="flex gap-3 pt-6 mt-4 border-t border-border">
              <button
                onClick={() => setForm(null)}
                className="flex-1 px-4 py-2.5 border border-border text-sm text-ink-secondary rounded-xl hover:bg-surface-mid"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={saving || !form.name.trim()}
                className="flex-1 px-4 py-2.5 bg-primary text-white text-sm font-medium rounded-xl hover:bg-primary-dark disabled:opacity-50"
              >
                {saving ? "Saving…" : form.id ? "Save Changes" : "Create Plan"}
              </button>
            </div>
          </div>
        </div>
      )}

      {deleteTarget && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-card shadow-xl w-full max-w-sm p-6">
            <h3 className="text-lg font-bold text-ink mb-2">Delete {deleteTarget.name}?</h3>
            <p className="text-sm text-ink-secondary mb-6">
              {deleteTarget.tenant_count > 0
                ? `${deleteTarget.tenant_count} tenant${deleteTarget.tenant_count === 1 ? "" : "s"} currently on this plan will keep their entitlements, but this plan will no longer be assignable to new tenants.`
                : "This plan is not assigned to any tenant."}
            </p>
            <div className="flex gap-3">
              <button onClick={() => setDeleteTarget(null)} className="flex-1 px-4 py-2.5 border border-border text-sm text-ink-secondary rounded-xl hover:bg-surface-mid">
                Cancel
              </button>
              <button onClick={handleDelete} disabled={deleting} className="flex-1 px-4 py-2.5 bg-danger text-white text-sm font-medium rounded-xl hover:bg-danger/90 disabled:opacity-50">
                {deleting ? "Deleting…" : "Delete"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
