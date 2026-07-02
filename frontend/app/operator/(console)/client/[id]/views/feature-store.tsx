"use client";
import { useEffect, useState } from "react";
import { CreditCard, Check } from "lucide-react";
import { API_URL, getAuthHeaders } from "@/lib/api";
import { SkeletonCard } from "../components/skeleton";

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
  const json = await res.json();
  return ((json as { data?: T }).data ?? json) as T;
}

interface Plan {
  id: string;
  name: string;
  monthly_price: number;
  feature_keys: string[];
  quotas: Record<string, number>;
}

interface Subscription {
  plan_id: string | null;
  mrr: number;
  plan: Plan | null;
}

interface FeatureCatalogItem {
  feature_key: string;
  display_name: string;
  category: string;
}

export function FeatureStoreView({ tenantId }: { tenantId: string }) {
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [catalog, setCatalog] = useState<FeatureCatalogItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedPlanId, setSelectedPlanId] = useState<string>("");
  const [changing, setChanging] = useState(false);

  useEffect(() => {
    Promise.all([
      apiFetch<Subscription>(`/api/v1/operator/clients/${tenantId}/subscription`),
      apiFetch<Plan[]>("/api/v1/operator/plans"),
      apiFetch<FeatureCatalogItem[]>("/api/v1/operator/features/catalog"),
    ])
      .then(([sub, plansData, catalogData]) => {
        setSubscription(sub);
        setPlans(plansData || []);
        setCatalog(catalogData || []);
        setSelectedPlanId(sub?.plan_id || "");
      })
      .catch(e => setError(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, [tenantId]);

  async function handleChangePlan() {
    setChanging(true);
    setError(null);
    try {
      await apiFetch(`/api/v1/operator/clients/${tenantId}/subscription`, {
        method: "PATCH",
        body: JSON.stringify({ plan_id: selectedPlanId || null }),
      });
      const sub = await apiFetch<Subscription>(`/api/v1/operator/clients/${tenantId}/subscription`);
      setSubscription(sub);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to change plan");
    } finally {
      setChanging(false);
    }
  }

  if (loading) {
    return (
      <div className="space-y-4">
        <SkeletonCard />
        <SkeletonCard />
      </div>
    );
  }

  if (error) {
    return <div className="p-4 bg-red-50 border border-danger/20 rounded-xl text-sm text-danger">{error}</div>;
  }

  const catalogByKey = new Map(catalog.map(f => [f.feature_key, f]));
  const currentPlan = subscription?.plan || null;
  const isDirty = selectedPlanId !== (subscription?.plan_id || "");

  return (
    <div className="space-y-6">
      <div className="bg-white rounded-card border border-border p-5 shadow-sm">
        <h3 className="text-sm font-semibold text-ink mb-3 flex items-center gap-2">
          <CreditCard size={16} className="text-ink-muted" /> Assigned Plan
        </h3>
        {currentPlan ? (
          <div>
            <div className="flex items-baseline gap-2">
              <span className="text-xl font-bold text-ink">{currentPlan.name}</span>
              <span className="text-primary font-bold">₹{currentPlan.monthly_price.toLocaleString("en-IN")}/mo</span>
            </div>
            <div className="mt-3 grid gap-1.5 md:grid-cols-2">
              {currentPlan.feature_keys.map(key => (
                <div key={key} className="flex items-center gap-1.5 text-sm text-ink-secondary">
                  <Check size={13} className="text-success shrink-0" />
                  {catalogByKey.get(key)?.display_name || key}
                </div>
              ))}
            </div>
          </div>
        ) : (
          <p className="text-sm text-ink-muted">No plan assigned.</p>
        )}
      </div>

      <div className="bg-white rounded-card border border-border p-5 shadow-sm">
        <h3 className="text-sm font-semibold text-ink mb-3">Change Plan</h3>
        {plans.length === 0 ? (
          <p className="text-sm text-ink-muted">No plans exist yet — create one from the Subscription page.</p>
        ) : (
          <div className="flex items-center gap-3">
            <select
              value={selectedPlanId}
              onChange={e => setSelectedPlanId(e.target.value)}
              className="flex-1 border border-border rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
            >
              <option value="">No plan</option>
              {plans.map(p => (
                <option key={p.id} value={p.id}>{p.name} — ₹{p.monthly_price.toLocaleString("en-IN")}/mo</option>
              ))}
            </select>
            <button
              onClick={handleChangePlan}
              disabled={!isDirty || changing}
              className="px-4 py-2 bg-primary text-white text-sm font-medium rounded-xl hover:bg-primary-dark disabled:opacity-50"
            >
              {changing ? "Applying…" : "Apply"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
