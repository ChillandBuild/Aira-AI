"use client";
import { useEffect, useState } from "react";
import { AlertTriangle, Zap, Phone, MessageSquare, Brain, Cog, Settings2 } from "lucide-react";
import { API_URL, getAuthHeaders } from "@/lib/api";
import { SkeletonCard } from "../components/skeleton";
import { EntitlementCard, ToggleState } from "../../../components/entitlement-toggle";

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

interface ClientConfig {
  enabled_features: string[];
  credentials_status: Record<string, string>;
  settings: Record<string, any>;
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
  const [enabledFeatures, setEnabledFeatures] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [toggling, setToggling] = useState<string | null>(null);
  const [showQuoteConfirm, setShowQuoteConfirm] = useState<{ feature: FeatureCatalogItem; currentMrr: number; newMrr: number } | null>(null);

  useEffect(() => {
    Promise.all([
      apiFetch<FeatureCatalogItem[]>("/api/v1/operator/features/catalog"),
      apiFetch<TenantSubscription>(`/api/v1/operator/clients/${tenantId}/subscription`),
      apiFetch<UsageCounter[]>(`/api/v1/operator/clients/${tenantId}/usage`),
      apiFetch<ClientConfig>(`/api/v1/operator/clients/${tenantId}/config`),
    ])
      .then(([catalogData, subData, usageData, configData]) => {
        setCatalog(catalogData || []);
        setSubscription(subData || null);
        const usageMap: Record<string, UsageCounter> = {};
        (usageData || []).forEach(u => usageMap[u.metric] = u);
        setUsage(usageMap);
        setEnabledFeatures(new Set(configData?.enabled_features || []));
      })
      .catch(e => setError(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, [tenantId]);

  const featuresByCategory = catalog.reduce<Record<string, FeatureCatalogItem[]>>((acc, f) => {
    if (!acc[f.category]) acc[f.category] = [];
    acc[f.category].push(f);
    return acc;
  }, {});

  function isPillarOwned(pillar: string): boolean {
    if (pillar === "shared") return true;
    if (pillar === "messaging") return !!subscription?.messaging_plan_id;
    if (pillar === "telecalling") return !!subscription?.telecalling_plan_id;
    return true;
  }

  function getToggleState(feature: FeatureCatalogItem): ToggleState {
    if (!isPillarOwned(feature.pillar)) return "locked";
    if (feature.is_metered) return "metered";
    return enabledFeatures.has(feature.feature_key) ? "on" : "off";
  }

  async function doToggle(feature_key: string, enabled: boolean) {
    setToggling(feature_key);
    try {
      const res = await apiFetch<{ tenant_id: string; enabled_features: string[] }>(
        `/api/v1/operator/clients/${tenantId}/features/toggle`,
        {
          method: "POST",
          body: JSON.stringify({ feature_key, enabled }),
        }
      );
      if (res?.enabled_features) {
        setEnabledFeatures(new Set(res.enabled_features));
      } else {
        setEnabledFeatures(prev => {
          const next = new Set(prev);
          if (enabled) next.add(feature_key);
          else next.delete(feature_key);
          return next;
        });
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update feature");
    } finally {
      setToggling(null);
    }
  }

  function handleToggle(feature: FeatureCatalogItem, enabled: boolean) {
    const state = getToggleState(feature);
    if (state === "locked" || state === "metered") return;

    if (enabled && feature.monthly_price > 0 && !feature.is_metered) {
      const currentMrr = subscription?.mrr || 0;
      setShowQuoteConfirm({ feature, currentMrr, newMrr: currentMrr + feature.monthly_price });
      return;
    }

    void doToggle(feature.feature_key, enabled);
  }

  function confirmQuote() {
    if (!showQuoteConfirm) return;
    const { feature } = showQuoteConfirm;
    setShowQuoteConfirm(null);
    void doToggle(feature.feature_key, true);
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
      {Object.entries(featuresByCategory).map(([category, features]) => {
        const CatIcon = CATEGORY_ICONS[category];
        return (
          <div key={category}>
            <h3 className="text-sm font-semibold text-ink mb-3 flex items-center gap-2">
              {CatIcon && <CatIcon size={16} className="text-ink-muted" />}
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
                    checked={enabledFeatures.has(feature.feature_key)}
                    onToggle={(checked) => handleToggle(feature, checked)}
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
        );
      })}

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

      {showQuoteConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-card bg-white p-6 shadow-xl">
            <div className="flex items-start gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-warning/10 text-warning">
                <AlertTriangle size={20} />
              </div>
              <div>
                <h3 className="text-lg font-bold text-ink">Enable {showQuoteConfirm.feature.display_name}?</h3>
                <p className="mt-2 text-sm leading-relaxed text-ink-secondary">
                  New monthly estimate: ₹{showQuoteConfirm.currentMrr.toLocaleString("en-IN")} → ₹{showQuoteConfirm.newMrr.toLocaleString("en-IN")}
                </p>
              </div>
            </div>
            <div className="mt-6 flex gap-3">
              <button
                type="button"
                onClick={() => setShowQuoteConfirm(null)}
                disabled={!!toggling}
                className="flex-1 rounded-xl border border-border px-4 py-2.5 text-sm font-medium text-ink-secondary transition-colors hover:bg-surface-mid disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={confirmQuote}
                disabled={!!toggling}
                className="flex-1 rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-primary/90 disabled:opacity-50"
              >
                Confirm
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}