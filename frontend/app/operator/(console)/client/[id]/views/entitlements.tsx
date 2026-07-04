"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { CreditCard, Check, ExternalLink } from "lucide-react";
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

interface FeatureCatalogItem {
  feature_key: string;
  display_name: string;
}

interface SubscriptionItem {
  feature_key: string;
  quantity: number;
  unit_price_snapshot: number;
}

/**
 * Read-only view of what a tenant currently has entitled — replaces the old
 * plan-picker Feature Store (migration 128 removed admin-side plan
 * assignment entirely; tenants build their own itemized cart and an admin
 * approves it from the Approval Queue instead).
 */
export function EntitlementsView({ tenantId }: { tenantId: string }) {
  const router = useRouter();
  const [items, setItems] = useState<SubscriptionItem[]>([]);
  const [catalog, setCatalog] = useState<FeatureCatalogItem[]>([]);
  const [status, setStatus] = useState<string>("none");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      apiFetch<{ items: SubscriptionItem[]; status: string }>(`/api/v1/operator/clients/${tenantId}/entitlements`),
      apiFetch<FeatureCatalogItem[]>("/api/v1/operator/features/catalog"),
    ])
      .then(([ent, catalogData]) => {
        setItems(ent.items || []);
        setStatus(ent.status || "none");
        setCatalog(catalogData || []);
      })
      .catch(e => setError(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, [tenantId]);

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
  const total = items.reduce((sum, i) => sum + i.quantity * i.unit_price_snapshot, 0);

  return (
    <div className="space-y-6">
      <div className="bg-white rounded-card border border-border p-5 shadow-sm">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-ink flex items-center gap-2">
            <CreditCard size={16} className="text-ink-muted" /> Current Entitlements
          </h3>
          <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-surface-mid text-ink-secondary capitalize">
            {status.replace("_", " ")}
          </span>
        </div>
        {items.length > 0 ? (
          <div>
            <p className="text-lg font-bold text-ink mb-3">
              ₹{total.toLocaleString("en-IN")}<span className="text-xs font-medium text-ink-muted">/mo</span>
            </p>
            <div className="grid gap-1.5 md:grid-cols-2">
              {items.map(item => (
                <div key={item.feature_key} className="flex items-center gap-1.5 text-sm text-ink-secondary">
                  <Check size={13} className="text-success shrink-0" />
                  {catalogByKey.get(item.feature_key)?.display_name || item.feature_key}
                  {item.quantity > 1 && <span className="text-xs text-ink-muted">×{item.quantity}</span>}
                </div>
              ))}
            </div>
          </div>
        ) : (
          <p className="text-sm text-ink-muted">Nothing purchased yet — the tenant is either pre-existing (grandfathered) or hasn&apos;t submitted a cart.</p>
        )}
      </div>

      <button
        onClick={() => router.push(`/operator/subscription-requests?tenant_id=${tenantId}`)}
        className="flex items-center gap-1.5 text-sm font-medium text-primary hover:text-primary-dark"
      >
        View this tenant&apos;s request history <ExternalLink size={13} />
      </button>
    </div>
  );
}
