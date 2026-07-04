"use client";
import { useEffect, useState } from "react";
import { API_URL, getAuthHeaders } from "@/lib/api";

interface CatalogRow {
  feature_key: string;
  display_name: string;
  category: string;
  monthly_price: number;
  unit_price: number | null;
  included_qty: number | null;
  usage_metric: string | null;
}

interface PackageRow {
  id: string;
  name: string;
  monthly_price: number;
  feature_keys: { feature_key: string; quantity: number }[];
  discount_percent: number;
}

export interface SubscriptionItem {
  feature_key: string;
  quantity: number;
}

const SELLABLE_KEYS = [
  "inbound_messaging", "outbound_messaging", "telecalling_sim", "telecalling_telecmi",
  "bulk_lead_upload", "telecaller_seats", "numbers_pool", "notifications",
];

async function apiGet<T>(path: string): Promise<T> {
  const auth = await getAuthHeaders();
  const res = await fetch(`${API_URL}${path}`, { headers: auth });
  if (!res.ok) throw new Error("Failed to load");
  return res.json();
}

export function CartBuilder({
  mode, existingItems, onSubmitted,
}: {
  mode: "initial" | "addon";
  existingItems: SubscriptionItem[];
  onSubmitted: () => void;
}) {
  const [catalog, setCatalog] = useState<CatalogRow[]>([]);
  const [packages, setPackages] = useState<PackageRow[]>([]);
  const [selected, setSelected] = useState<Record<string, number>>({});
  const [selectedPackage, setSelectedPackage] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiGet<{ catalog: CatalogRow[]; packages: PackageRow[] }>("/api/v1/subscriptions/catalog")
      .then((data) => {
        setCatalog(data.catalog.filter((c) => SELLABLE_KEYS.includes(c.feature_key)));
        setPackages(data.packages);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load catalog"))
      .finally(() => setLoading(false));
  }, []);

  function applyPackage(pkg: PackageRow) {
    setSelectedPackage(pkg.id);
    const next: Record<string, number> = {};
    pkg.feature_keys.forEach((item) => { next[item.feature_key] = item.quantity; });
    setSelected(next);
  }

  function toggleItem(key: string, defaultQty = 1) {
    setSelected((prev) => {
      const next = { ...prev };
      if (next[key]) delete next[key];
      else next[key] = defaultQty;
      return next;
    });
  }

  function setQuantity(key: string, qty: number) {
    setSelected((prev) => ({ ...prev, [key]: Math.max(1, qty) }));
  }

  const existingQtyFor = (key: string) => existingItems.find((i) => i.feature_key === key)?.quantity ?? 0;

  const total = Object.entries(selected).reduce((sum, [key, qty]) => {
    const row = catalog.find((c) => c.feature_key === key);
    if (!row) return sum;
    const unitCost = row.unit_price ?? row.monthly_price;
    return sum + unitCost * qty;
  }, 0);

  async function submit() {
    setSubmitting(true);
    setError(null);
    try {
      const auth = await getAuthHeaders();
      const res = await fetch(`${API_URL}/api/v1/subscriptions/requests`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...auth },
        body: JSON.stringify({
          package_id: selectedPackage,
          items: Object.entries(selected).map(([feature_key, quantity]) => ({ feature_key, quantity })),
        }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || "Failed to submit");
      }
      onSubmitted();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to submit");
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) return <div className="p-8 text-center text-ink-muted">Loading pricing…</div>;

  return (
    <div className="space-y-6">
      {error && <div className="p-3 rounded-xl bg-red-50 text-red-700 text-sm">{error}</div>}

      {packages.length > 0 && (
        <div>
          <h3 className="mb-2 text-sm font-semibold text-ink">Packages</h3>
          <div className="grid gap-3 sm:grid-cols-2">
            {packages.map((pkg) => (
              <button
                key={pkg.id}
                onClick={() => applyPackage(pkg)}
                className={`rounded-xl border p-4 text-left transition ${selectedPackage === pkg.id ? "border-primary bg-primary-light" : "border-border bg-white"}`}
              >
                <p className="font-semibold text-ink">{pkg.name}</p>
                <p className="text-sm text-ink-muted">₹{pkg.monthly_price.toLocaleString("en-IN")}/mo · {pkg.discount_percent}% off</p>
              </button>
            ))}
          </div>
        </div>
      )}

      <div>
        <h3 className="mb-2 text-sm font-semibold text-ink">{mode === "addon" ? "Add more" : "Build your plan"}</h3>
        <div className="space-y-2">
          {catalog.map((item) => {
            const isSelected = item.feature_key in selected;
            const existingQty = existingQtyFor(item.feature_key);
            if (mode === "addon" && existingQty === 0 && !item.usage_metric) return null;
            return (
              <div key={item.feature_key} className="flex items-center justify-between rounded-xl border border-border bg-white p-4">
                <label className="flex items-center gap-3">
                  <input type="checkbox" checked={isSelected} onChange={() => toggleItem(item.feature_key)} />
                  <div>
                    <p className="font-medium text-ink">{item.display_name}</p>
                    <p className="text-xs text-ink-muted">
                      ₹{(item.unit_price ?? item.monthly_price).toLocaleString("en-IN")}
                      {item.unit_price ? " / extra unit" : "/mo"}
                      {existingQty > 0 && ` · currently: ${existingQty}`}
                    </p>
                  </div>
                </label>
                {isSelected && item.unit_price !== null && (
                  <input
                    type="number"
                    min={1}
                    value={selected[item.feature_key]}
                    onChange={(e) => setQuantity(item.feature_key, parseInt(e.target.value) || 1)}
                    className="w-16 rounded-lg border border-border px-2 py-1 text-center text-sm"
                  />
                )}
              </div>
            );
          })}
        </div>
      </div>

      <div className="flex items-center justify-between border-t border-border-subtle pt-4">
        <p className="text-lg font-bold text-ink">Total: ₹{total.toLocaleString("en-IN")}/mo</p>
        <button
          onClick={submit}
          disabled={submitting || Object.keys(selected).length === 0}
          className="btn-primary"
        >
          {submitting ? "Submitting…" : mode === "addon" ? "Request Increase" : "Submit for Approval"}
        </button>
      </div>
    </div>
  );
}
