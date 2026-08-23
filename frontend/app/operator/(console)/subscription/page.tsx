"use client";
import { useCallback, useEffect, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Package, Plus, Pencil, Trash2, MessageSquare, Zap, Brain, Phone, Cog, Settings2, Save, CheckCircle2 } from "lucide-react";
import { operatorFetch } from "@/lib/operator";
import { cn } from "@/lib/utils";
import { TickMark } from "@/components/ui/controls";

interface CatalogItem {
  feature_key: string;
  display_name: string;
  category: string;
  monthly_price: number;
  unit_price: number | null;
  included_qty: number | null;
  usage_metric: string | null;
  is_metered: boolean;
}

interface PackageItem {
  feature_key: string;
  quantity: number;
}

interface PlanRow {
  id: string;
  name: string;
  monthly_price: number;
  feature_keys: PackageItem[];
  discount_percent: number;
  active: boolean;
  created_at: string;
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

const SELLABLE_KEYS = [
  "inbound_messaging", "outbound_messaging",
  "ai_tier.basic", "ai_tier.standard", "ai_tier.premium",
  "telecalling_sim", "telecalling_telecmi",
  "bulk_lead_upload", "telecaller_seats", "numbers_pool", "notifications",
];

async function loadCatalogAndPackages() {
  const [catalogRes, packagesRes] = await Promise.all([
    operatorFetch<{ data: CatalogItem[] } | CatalogItem[]>("/api/v1/operator/features/catalog"),
    operatorFetch<{ data: PlanRow[] }>("/api/v1/operator/plans"),
  ]);
  const catalog = Array.isArray(catalogRes) ? catalogRes : catalogRes.data ?? [];
  return { catalog, packages: packagesRes.data ?? [] };
}

function itemPrice(item: CatalogItem): number {
  return item.unit_price ?? item.monthly_price;
}

// --- Pricing Catalog tab ---------------------------------------------------

function CatalogRow({ item, onSaved }: { item: CatalogItem; onSaved: () => void }) {
  const [dailyPrice, setDailyPrice] = useState(String(item.monthly_price ? item.monthly_price / 30 : 0));
  const [unitPrice, setUnitPrice] = useState(item.unit_price !== null ? String(item.unit_price) : "");
  const [includedQty, setIncludedQty] = useState(item.included_qty !== null ? String(item.included_qty) : "");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const dirty =
    Math.round((parseFloat(dailyPrice) || 0) * 30 * 100) / 100 !== Number(item.monthly_price) ||
    unitPrice !== (item.unit_price !== null ? String(item.unit_price) : "") ||
    includedQty !== (item.included_qty !== null ? String(item.included_qty) : "");

  async function save() {
    setSaving(true);
    setError(null);
    try {
      await operatorFetch(`/api/v1/operator/catalog/${item.feature_key}`, {
        method: "PATCH",
        body: JSON.stringify({
          monthly_price: Math.round((parseFloat(dailyPrice) || 0) * 30 * 100) / 100,
          unit_price: unitPrice ? parseFloat(unitPrice) : null,
          included_qty: includedQty ? parseInt(includedQty, 10) : null,
        }),
      });
      setSaved(true);
      onSaved();
      setTimeout(() => setSaved(false), 2000);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  }

  const isFlat = item.unit_price === null && item.included_qty === null;

  return (
    <div className="grid grid-cols-[1fr_auto_auto_auto_auto] items-center gap-3 py-2.5 border-b border-border-subtle last:border-0">
      <span className="text-sm text-ink">{item.display_name}</span>
      <input
        type="number" min="0" value={dailyPrice} onChange={e => setDailyPrice(e.target.value)}
        className="w-24 border border-border rounded-lg px-2 py-1 text-sm text-right focus:outline-none focus:ring-2 focus:ring-primary/20"
        placeholder="Daily"
      />
      {!isFlat ? (
        <input
          type="number" min="0" value={unitPrice} onChange={e => setUnitPrice(e.target.value)}
          className="w-24 border border-border rounded-lg px-2 py-1 text-sm text-right focus:outline-none focus:ring-2 focus:ring-primary/20"
          placeholder="Unit"
        />
      ) : (
        <div className="w-24" />
      )}
      {!isFlat ? (
        <input
          type="number" min="0" value={includedQty} onChange={e => setIncludedQty(e.target.value)}
          className="w-24 border border-border rounded-lg px-2 py-1 text-sm text-right focus:outline-none focus:ring-2 focus:ring-primary/20"
          placeholder="Included"
        />
      ) : (
        <div className="w-24" />
      )}
      <button
        onClick={save}
        disabled={saving || !dirty}
        className={cn(
          "flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-semibold transition-all duration-150 hover:scale-[1.02] active:scale-[0.98] shadow-xs",
          saved ? "bg-success/10 text-success" : dirty ? "bg-primary text-white hover:bg-primary-dark hover:shadow-sm" : "bg-surface-mid text-ink-muted cursor-not-allowed"
        )}
      >
        {saved ? <CheckCircle2 size={12} /> : <Save size={12} />}
        {saving ? "Saving…" : saved ? "Saved" : "Save"}
      </button>
      {error && <span className="col-span-5 text-xs text-danger">{error}</span>}
    </div>
  );
}

function PricingCatalogTab({ catalog, onReload }: { catalog: CatalogItem[]; onReload: () => void }) {
  const sellable = catalog.filter(c => SELLABLE_KEYS.includes(c.feature_key));
  const byCategory = sellable.reduce<Record<string, CatalogItem[]>>((acc, c) => {
    if (!acc[c.category]) acc[c.category] = [];
    acc[c.category].push(c);
    return acc;
  }, {});

  return (
    <div className="space-y-6">
      <p className="text-xs text-ink-muted">
        Set the daily price for flat modules; the monthly catalog price is saved as daily x 30. &ldquo;Unit&rdquo; is the price for
        each quantity-based item, such as Telecaller Seats and Numbers Pool.
      </p>
      {Object.entries(byCategory).map(([category, items]) => {
        const Icon = CATEGORY_ICONS[category] || Zap;
        return (
          <div key={category} className="bg-white rounded-card border border-border p-5 shadow-sm">
            <p className="text-xs font-semibold text-ink-muted uppercase tracking-wide flex items-center gap-1.5 mb-3">
              <Icon size={12} /> {CATEGORY_LABELS[category] || category}
            </p>
            <div className="grid grid-cols-[1fr_auto_auto_auto_auto] gap-3 pb-2 text-[11px] font-medium text-ink-muted uppercase tracking-wide">
              <span>Item</span>
              <span className="text-right w-24">Daily</span>
              <span className="text-right w-24">Unit</span>
              <span className="text-right w-24">Included</span>
              <span className="w-20" />
            </div>
            {items.map(item => (
              <CatalogRow key={item.feature_key} item={item} onSaved={onReload} />
            ))}
          </div>
        );
      })}
    </div>
  );
}

// --- Packages tab -----------------------------------------------------------

interface PackageFormState {
  id: string | null;
  name: string;
  discountPercent: string;
  items: Record<string, number>;
}

function emptyPackageForm(): PackageFormState {
  return { id: null, name: "", discountPercent: "0", items: {} };
}

function PackagesTab({ catalog, packages, onReload }: { catalog: CatalogItem[]; packages: PlanRow[]; onReload: () => void }) {
  const [form, setForm] = useState<PackageFormState | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<PlanRow | null>(null);
  const [deleting, setDeleting] = useState(false);

  const sellable = catalog.filter(c => SELLABLE_KEYS.includes(c.feature_key));
  const priceByKey = Object.fromEntries(sellable.map(c => [c.feature_key, itemPrice(c)]));

  function openCreate() {
    setForm(emptyPackageForm());
  }

  function openEdit(pkg: PlanRow) {
    const items: Record<string, number> = {};
    for (const item of pkg.feature_keys) items[item.feature_key] = item.quantity;
    setForm({ id: pkg.id, name: pkg.name, discountPercent: String(pkg.discount_percent), items });
  }

  function toggleItem(key: string) {
    setForm(prev => {
      if (!prev) return prev;
      const next = { ...prev.items };
      if (key in next) delete next[key];
      else next[key] = 1;
      return { ...prev, items: next };
    });
  }

  function setQuantity(key: string, qty: number) {
    setForm(prev => (prev ? { ...prev, items: { ...prev.items, [key]: Math.max(1, qty) } } : prev));
  }

  const discountPercent = form ? parseFloat(form.discountPercent) || 0 : 0;
  const subtotal = form
    ? Object.entries(form.items).reduce((sum, [key, qty]) => sum + (priceByKey[key] ?? 0) * qty, 0)
    : 0;
  const computedPrice = subtotal * (1 - discountPercent / 100);

  async function handleSave() {
    if (!form || !form.name.trim()) return;
    setSaving(true);
    setError(null);
    const payload = {
      name: form.name.trim(),
      discount_percent: discountPercent,
      items: Object.entries(form.items).map(([feature_key, quantity]) => ({ feature_key, quantity })),
    };
    try {
      if (form.id) {
        await operatorFetch(`/api/v1/operator/plans/${form.id}`, { method: "PATCH", body: JSON.stringify(payload) });
      } else {
        await operatorFetch("/api/v1/operator/plans", { method: "POST", body: JSON.stringify(payload) });
      }
      setForm(null);
      onReload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save package");
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
      onReload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete package");
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <p className="text-xs text-ink-muted max-w-lg">
          Packages are optional discounted bundles shown as a one-click shortcut in the client&apos;s cart.
          Prices are always computed from the Pricing Catalog — you only set a discount.
        </p>
        <button
          onClick={openCreate}
          className="flex items-center gap-1 px-3 py-1.5 bg-primary text-white text-xs font-semibold rounded-lg hover:bg-primary-dark hover:scale-[1.02] active:scale-[0.98] transition-all shrink-0 shadow-sm"
        >
          <Plus size={13} /> New Package
        </button>
      </div>

      {error && <div className="p-3 bg-red-50 border border-danger/20 rounded-xl text-sm text-danger">{error}</div>}

      {packages.length === 0 ? (
        <div className="rounded-card border border-dashed border-border p-10 text-center">
          <Package size={28} className="mx-auto text-ink-muted mb-3" />
          <p className="text-sm font-medium text-ink">No packages yet</p>
          <p className="text-xs text-ink-muted mt-1">Clients can still build a cart item-by-item without one.</p>
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {packages.map(pkg => (
            <div key={pkg.id} className="bg-white rounded-card border border-border p-5 shadow-sm">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <h3 className="text-sm font-semibold text-ink">{pkg.name}</h3>
                  <p className="text-lg font-bold text-primary mt-1">
                    ₹{pkg.monthly_price.toLocaleString("en-IN")}
                    <span className="text-xs font-medium text-ink-muted">/mo</span>
                  </p>
                  {pkg.discount_percent > 0 && (
                    <span className="inline-block mt-1 text-[11px] font-medium text-success bg-success/10 rounded-full px-2 py-0.5">
                      {pkg.discount_percent}% off
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-1">
                  <button onClick={() => openEdit(pkg)} className="p-1.5 rounded-lg text-ink-muted hover:bg-surface-mid hover:text-ink transition-colors" title="Edit package">
                    <Pencil size={14} />
                  </button>
                  <button onClick={() => setDeleteTarget(pkg)} className="p-1.5 rounded-lg text-ink-muted hover:bg-red-50 hover:text-danger transition-colors" title="Delete package">
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
              <p className="text-xs text-ink-muted mt-3">{pkg.feature_keys.length} items included</p>
            </div>
          ))}
        </div>
      )}

      {form && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-card shadow-xl w-full max-w-lg max-h-[85vh] overflow-y-auto p-6">
            <h2 className="text-lg font-bold text-ink mb-4">{form.id ? "Edit Package" : "New Package"}</h2>
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-sm font-medium text-ink-secondary block mb-1">Package Name *</label>
                  <input
                    value={form.name}
                    onChange={e => setForm(prev => (prev ? { ...prev, name: e.target.value } : prev))}
                    className="w-full border border-border rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
                    placeholder="Starter Bundle"
                  />
                </div>
                <div>
                  <label className="text-sm font-medium text-ink-secondary block mb-1">Discount (%)</label>
                  <input
                    type="number" min="0" max="100"
                    value={form.discountPercent}
                    onChange={e => setForm(prev => (prev ? { ...prev, discountPercent: e.target.value } : prev))}
                    className="w-full border border-border rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
                  />
                </div>
              </div>

              <div>
                <label className="text-sm font-medium text-ink-secondary block mb-2">Items</label>
                <div className="space-y-2 max-h-56 overflow-y-auto border border-border rounded-xl p-3">
                  {sellable.map(item => {
                    const selected = item.feature_key in form.items;
                    return (
                      <div key={item.feature_key} className="flex items-center justify-between">
                        <button
                          type="button"
                          role="checkbox"
                          aria-checked={selected}
                          onClick={() => toggleItem(item.feature_key)}
                          className="flex items-center gap-2.5 text-left text-sm text-ink-secondary"
                        >
                          <TickMark checked={selected} size="sm" />
                          {item.display_name}
                          <span className="text-xs text-ink-muted">₹{itemPrice(item).toLocaleString("en-IN")}</span>
                        </button>
                        {selected && item.unit_price !== null && (
                          <input
                            type="number" min="1" value={form.items[item.feature_key]}
                            onChange={e => setQuantity(item.feature_key, parseInt(e.target.value, 10) || 1)}
                            className="w-16 border border-border rounded-lg px-2 py-1 text-sm text-center focus:outline-none focus:ring-2 focus:ring-primary/20"
                          />
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>

              <div className="flex items-center justify-between border-t border-border-subtle pt-3">
                <span className="text-sm text-ink-muted">Computed price</span>
                <span className="text-lg font-bold text-ink">₹{computedPrice.toLocaleString("en-IN")}/mo</span>
              </div>
            </div>

            <div className="flex gap-3 pt-6 mt-4 border-t border-border">
              <button
                onClick={() => setForm(null)}
                className="flex-1 px-3 py-2 border border-border text-xs font-semibold text-ink-secondary rounded-lg hover:bg-surface-mid transition-all duration-150"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={saving || !form.name.trim() || Object.keys(form.items).length === 0}
                className="flex-1 px-3 py-2 bg-primary text-white text-xs font-semibold rounded-lg hover:bg-primary-dark hover:scale-[1.02] active:scale-[0.98] transition-all duration-150 disabled:opacity-50 disabled:scale-100 shadow-sm"
              >
                {saving ? "Saving…" : form.id ? "Save Changes" : "Create Package"}
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
              Tenants who started from this package keep their entitlements — it just stops being offered
              as a cart shortcut going forward.
            </p>
            <div className="flex gap-3">
              <button onClick={() => setDeleteTarget(null)} className="flex-1 px-3 py-2 border border-border text-xs font-semibold text-ink-secondary rounded-lg hover:bg-surface-mid transition-all duration-150">
                Cancel
              </button>
              <button onClick={handleDelete} disabled={deleting} className="flex-1 px-3 py-2 bg-danger text-white text-xs font-semibold rounded-lg hover:bg-danger/90 hover:scale-[1.02] active:scale-[0.98] transition-all duration-150 disabled:opacity-50 disabled:scale-100">
                {deleting ? "Deleting…" : "Delete"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// --- Page --------------------------------------------------------------

export default function SubscriptionPage() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const activeTab = searchParams.get("tab") || "catalog";

  const [catalog, setCatalog] = useState<CatalogItem[]>([]);
  const [packages, setPackages] = useState<PlanRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    return loadCatalogAndPackages()
      .then(({ catalog: c, packages: p }) => {
        setCatalog(c);
        setPackages(p);
        setError(null);
      })
      .catch(e => setError(e instanceof Error ? e.message : "Request failed"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="p-7 space-y-6">
      <div>
        <h1 className="font-display text-lg font-bold text-ink">Subscription</h1>
        <p className="text-xs text-ink-muted mt-0.5">Price the catalog clients build their cart from, and author discounted packages.</p>
      </div>

      <div className="flex gap-1 rounded-2xl bg-[#e8e3db]/60 p-1 w-fit">
        <button
          onClick={() => router.push(`${pathname}?tab=catalog`)}
          className={cn(
            "rounded-xl px-4 py-2 text-xs font-bold transition-all",
            activeTab === "catalog" ? "bg-white text-primary shadow-sm" : "text-[#78716c] hover:text-[#292524]"
          )}
        >
          Pricing Catalog
        </button>
        <button
          onClick={() => router.push(`${pathname}?tab=packages`)}
          className={cn(
            "rounded-xl px-4 py-2 text-xs font-bold transition-all",
            activeTab === "packages" ? "bg-white text-primary shadow-sm" : "text-[#78716c] hover:text-[#292524]"
          )}
        >
          Packages
        </button>
      </div>

      {error && <div className="p-3 bg-red-50 border border-danger/20 rounded-xl text-sm text-danger">{error}</div>}

      {loading ? (
        <div className="text-sm text-ink-muted">Loading…</div>
      ) : activeTab === "packages" ? (
        <PackagesTab catalog={catalog} packages={packages} onReload={load} />
      ) : (
        <PricingCatalogTab catalog={catalog} onReload={load} />
      )}
    </div>
  );
}
