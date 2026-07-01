"use client";
import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, Loader2, Lock, Zap, Phone, MessageSquare, Brain, Cog, Settings2 } from "lucide-react";
import { API_URL, getAuthHeaders } from "@/lib/api";
import { SkeletonCard } from "../components/skeleton";
import { EntitlementCard, ToggleState } from "../../components/entitlement-toggle";

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
  return (json as any).data ?? json;
}

interface FeatureCatalogItem {
  feature_key: string;
  display_name: string;
  category: string;
  pillar: string;
  monthly_price: number;
  is_metered: boolean;
  usage_metric: string | null;
  included_qty: number | null;
}

interface UsageCounter {
  metric: string;
  used: number;
  included: number;
  hard_cap: number | null;
}

interface TenantSubscription {
  messaging_plan_id: string | null;
  telecalling_plan_id: string | null;
  ai_tier: string | null;
  mrr: number;
  custom_overrides: Record<string, any>;
}

const CATEGORY_ICONS: Record<string, typeof MessageSquare> = {
  channels: MessageSquare,
  messaging: Zap,
  ai: Brain,
  telecalling: Phone,
  automation: Cog,
  ops: Settings2,
};

const CATEGORY_LABELS: Record<string, string> = {
  channels: "Channels",
  messaging: "Messaging",
  ai: "AI",
  telecalling: "Telecalling",
  automation: "Automation",
  ops: "Ops",
};

export function FeatureStoreView({ tenantId }: { tenantId: string }) {
  const [catalog, setCatalog] = useState<FeatureCatalogItem[]>([]);
  const [subscription, setSubscription] = useState<TenantSubscription | null>(null);
  const [usage, setUsage] = useState<Record<string, UsageCounter>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [toggling, setToggling] = useState<string | null>(null);
  const [showQuoteConfirm, setShowQuoteConfirm] = useState<{feature: string, currentPrice: number, newPrice: number} | null>(null);

  useEffect(() => {
    Promise.all([
      apiFetch<FeatureCatalogItem[]>("/api/v1/operator/features/catalog"),
      apiFetch<TenantSubscription>(`/api/v1/operator/clients/${tenantId}/subscription`),
      apiFetch<UsageCounter[]>(`/api/v1/operator/clients/${tenantId}/usage`),
    ])
      .then(([catalogData, subData, usageData]) => {
        setCatalog(catalogData || []);
        setSubscription(subData || null);
        const usageMap: Record<string, UsageCounter> = {};
        (usageData || []).forEach(u => usageMap[u.metric] = u);
        setUsage(usageMap);
      })
      .catch(e => setError(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, [tenantId]);

  const enabledFeatures = new Set<string>();
  const planFeatures: Record<string, string[]> = {};
  
  if (subscription?.messaging_plan_id) {
    const plan = catalog.find(c => c.feature_key === subscription.messaging_plan_id) || null;
  }

  const featuresByCategory = catalog.reduce<Record<string, FeatureCatalogItem[]>>((acc, f) => {
    if (!acc[f.category]) acc[f.category] = [];
    acc[f.category].push(f);
    return acc;
  }, {});

  async function handleToggle(feature_key: string, enabled: boolean) {
    setToggling(feature_key);
    try {
      await apiFetch(`/api/v1/operator/clients/${tenantId}/features/toggle`, {
        method: "POST",
        body: JSON.stringify({ feature_key, enabled }),
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update feature");
    } finally {
      setToggling(null);
    }
  }

  function getToggleState(feature: FeatureCatalogItem): ToggleState {
    const isEnabled = true;
    if (feature.is_metered) return "metered";
    return isEnabled ? "on" : "off";
  }

  function formatPrice(price: number): string {
    if (price === 0) return "Included";
    return `₹${price.toLocaleString("en-IN")}/mo`;
  }

  if (loading) {
    return (
      <div className="space-y-6">
        {Object.keys(CATEGORY_LABELS).map(cat => (
          <div key={cat}>
            <h3 className="text-sm font-semibold text-ink mb-3">{CATEGORY_LABELS[cat]}</h3>
            <div className="grid gap-4 md:grid-cols-2">
              {Array.from({ length: 2 }).map((_, i) => <SkeletonCard key={i} />)}
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 bg-red-50 border border-danger/20 rounded-xl text-sm text-danger">
        {error}
      </div>
    );
  }

  function getUsageForFeature(feature: FeatureCatalogItem): UsageCounter | undefined {
    if (!feature.is_metered) return undefined;
    if (feature.usage_metric) {
      return usage[feature.usage_metric];
    }
    const map: Record<string, string> = {
      "ai_tier.basic": "ai_reply",
      "ai_tier.standard": "ai_reply", 
      "ai_tier.premium": "ai_reply",
      "tc_recording.summary": "ai_call_summary",
      "tc_recording.scoring": "ai_call_scoring",
    };
    return usage[map[feature.feature_key]];
  }

  return (
    <div className="space-y-8">
      {Object.entries(featuresByCategory).map(([category, features]) => (
        <div key={category}>
          <h3 className="text-sm font-semibold text-ink mb-3 flex items-center gap-2">
            {CATEGORY_ICONS[category] && <CATEGORY_ICONS[category] size={16} className="text-ink-muted" />}
            {CATEGORY_LABELS[category] || category}
          </h3>
          <div className="grid gap-4 md:grid-cols-2">
            {features.map(feature => {
              const featureUsage = getUsageForFeature(feature);
              return (
                <EntitlementCard
                  key={feature.feature_key}
                  icon={CATEGORY_ICONS[category] || Zap}
                  name={feature.display_name}
                  description={`${feature.pillar} - ${feature.is_metered ? "Metered" : "Toggle"}`}
                  price={formatPrice(feature.monthly_price)}
                  state={getToggleState(feature)}
                  checked={true}
                  onToggle={(checked) => handleToggle(feature.feature_key, checked)}
                  usage={featureUsage ? {
                    used: featureUsage.used,
                    included: featureUsage.included,
                  } : undefined}
                  dependencyNote={featureUsage ? `Usage: ${featureUsage.used} / ${featureUsage.included}` : undefined}
                />
              );
            })}
          </div>
        </div>
      ))}

      <div className="bg-white rounded-card border border-border p-4">
        <h3 className="text-sm font-semibold text-ink mb-2">Current Plan Summary</h3>
        <div className="flex items-center gap-4 text-sm">
          <div>
            <span className="text-ink-muted">MRR:</span>
            <span className="text-primary font-bold ml-1">₹{(subscription?.mrr || 0).toLocaleString("en-IN")}/mo</span>
          </div>
          <div>
            <span className="text-ink-muted">AI Tier:</span>
            <span className="text-ink font-medium ml-1 capitalize">{subscription?.ai_tier || "off"}</span>
          </div>
        </div>
      </div>
    </div>
  );
}