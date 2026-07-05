"use client";
import { useEffect, useMemo, useState } from "react";
import {
  Check, Sparkles, RadioTower, MessageSquare, Phone, Upload as UploadIcon,
  Users, Layers, Minus, Plus,
} from "lucide-react";
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

const TELECALLING_TYPE_KEYS = ["telecalling_sim", "telecalling_telecmi"];

const ICONS: Record<string, typeof Phone> = {
  inbound_messaging: RadioTower,
  outbound_messaging: MessageSquare,
  telecalling_sim: Phone,
  telecalling_telecmi: Phone,
  bulk_lead_upload: UploadIcon,
  telecaller_seats: Users,
  numbers_pool: Layers,
};

async function apiGet<T>(path: string): Promise<T> {
  const auth = await getAuthHeaders();
  const res = await fetch(`${API_URL}${path}`, { headers: auth });
  if (!res.ok) throw new Error("Failed to load");
  return res.json();
}

/** Mirrors backend `_price_for_item` — flat SKUs (monthly_price > 0) always
 *  cost the full monthly price; quantity-priced SKUs (monthly_price === 0)
 *  bill only units beyond `included_qty`, netting out whatever quantity is
 *  already purchased so a top-up doesn't re-charge an included unit. */
function priceForItem(row: CatalogRow, quantity: number, existingQuantity: number): number {
  if (row.monthly_price > 0) return row.monthly_price;
  if (row.unit_price == null) return 0;
  const included = row.included_qty ?? 0;
  const alreadyBillable = Math.max(0, existingQuantity - included);
  const newBillable = Math.max(0, existingQuantity + quantity - included);
  return row.unit_price * (newBillable - alreadyBillable);
}

function SectionHeading({ children }: { children: React.ReactNode }) {
  return <h3 className="mb-3 text-[13px] font-bold uppercase tracking-wide text-ink-muted">{children}</h3>;
}

function SelectCard({
  selected, onClick, icon: Icon, title, subtitle, disabled,
}: {
  selected: boolean; onClick: () => void; icon: typeof Phone; title: string; subtitle: string; disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`group relative flex w-full items-start gap-3 rounded-2xl border p-4 text-left transition-all ${
        selected
          ? "border-primary bg-primary-light shadow-sm"
          : "border-border bg-white hover:border-primary/40 hover:bg-primary-light/30"
      } ${disabled ? "cursor-not-allowed opacity-50" : ""}`}
    >
      <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ${selected ? "bg-primary text-white" : "bg-surface-mid text-ink-muted"}`}>
        <Icon size={17} />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-ink">{title}</p>
        <p className="mt-0.5 text-xs text-ink-muted">{subtitle}</p>
      </div>
      <div className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border-2 ${selected ? "border-primary bg-primary" : "border-border-subtle"}`}>
        {selected && <Check size={12} className="text-white" strokeWidth={3} />}
      </div>
    </button>
  );
}

function Stepper({ value, onChange, min = 1 }: { value: number; onChange: (v: number) => void; min?: number }) {
  return (
    <div className="flex items-center gap-1 rounded-xl border border-border bg-surface-mid/60 p-1">
      <button
        type="button"
        onClick={() => onChange(Math.max(min, value - 1))}
        className="flex h-7 w-7 items-center justify-center rounded-lg bg-white text-ink shadow-sm transition hover:bg-primary-light disabled:opacity-40"
        disabled={value <= min}
      >
        <Minus size={13} />
      </button>
      <span className="w-8 text-center text-sm font-bold text-ink">{value}</span>
      <button
        type="button"
        onClick={() => onChange(value + 1)}
        className="flex h-7 w-7 items-center justify-center rounded-lg bg-white text-ink shadow-sm transition hover:bg-primary-light"
      >
        <Plus size={13} />
      </button>
    </div>
  );
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
        setCatalog(data.catalog);
        setPackages(data.packages);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load catalog"))
      .finally(() => setLoading(false));
  }, []);

  const byKey = useMemo(() => new Map(catalog.map((c) => [c.feature_key, c])), [catalog]);
  const existingQtyFor = (key: string) => existingItems.find((i) => i.feature_key === key)?.quantity ?? 0;

  function applyPackage(pkg: PackageRow) {
    setSelectedPackage((prev) => (prev === pkg.id ? null : pkg.id));
    if (selectedPackage === pkg.id) { setSelected({}); return; }
    const next: Record<string, number> = {};
    pkg.feature_keys.forEach((item) => { next[item.feature_key] = item.quantity; });
    setSelected(next);
  }

  function toggleItem(key: string, defaultQty = 1) {
    setSelectedPackage(null);
    setSelected((prev) => {
      const next = { ...prev };
      if (next[key]) delete next[key];
      else next[key] = defaultQty;
      return next;
    });
  }

  function selectTelecallingType(key: string) {
    setSelectedPackage(null);
    setSelected((prev) => {
      const next = { ...prev };
      const otherKey = TELECALLING_TYPE_KEYS.find((k) => k !== key)!;
      delete next[otherKey];
      if (next[key]) delete next[key];
      else next[key] = 1;
      return next;
    });
  }

  const total = Object.entries(selected).reduce((sum, [key, qty]) => {
    const row = byKey.get(key);
    if (!row) return sum;
    return sum + priceForItem(row, qty, existingQtyFor(key));
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

  if (loading) {
    return (
      <div className="flex items-center justify-center gap-2 p-12 text-ink-muted">
        <div className="h-4 w-4 animate-spin rounded-full border-2 border-primary border-t-transparent" />
        Loading pricing…
      </div>
    );
  }

  const inbound = byKey.get("inbound_messaging");
  const outbound = byKey.get("outbound_messaging");
  const sim = byKey.get("telecalling_sim");
  const telecmi = byKey.get("telecalling_telecmi");
  const upload = byKey.get("bulk_lead_upload");
  const seats = byKey.get("telecaller_seats");
  const numbers = byKey.get("numbers_pool");


  const telecallingTypeSelected = TELECALLING_TYPE_KEYS.some((k) => k in selected);
  const hasTelecallingCoverage = telecallingTypeSelected || TELECALLING_TYPE_KEYS.some((k) => existingQtyFor(k) > 0);

  function fmt(n: number) {
    return `₹${n.toLocaleString("en-IN")}`;
  }

  function itemInAddonMode(row?: CatalogRow) {
    if (!row) return false;
    if (mode !== "addon") return true;
    return existingQtyFor(row.feature_key) > 0 || !!row.usage_metric;
  }

  return (
    <div className="space-y-8">
      {error && <div className="rounded-xl bg-red-50 p-3 text-sm text-red-700">{error}</div>}

      {packages.length > 0 && mode === "initial" && (
        <div>
          <SectionHeading>Quick-start packages</SectionHeading>
          <div className="grid gap-3 sm:grid-cols-2">
            {packages.map((pkg) => (
              <button
                key={pkg.id}
                type="button"
                onClick={() => applyPackage(pkg)}
                className={`relative rounded-2xl border p-4 text-left transition-all ${
                  selectedPackage === pkg.id
                    ? "border-primary bg-gradient-to-br from-primary-light to-white shadow-sm"
                    : "border-border bg-white hover:border-primary/40"
                }`}
              >
                {pkg.discount_percent > 0 && (
                  <span className="absolute -top-2 right-3 rounded-full bg-primary px-2 py-0.5 text-[10px] font-bold text-white">
                    {pkg.discount_percent}% off
                  </span>
                )}
                <div className="mb-1 flex items-center gap-1.5 text-primary">
                  <Sparkles size={14} />
                  <p className="font-semibold text-ink">{pkg.name}</p>
                </div>
                <p className="text-lg font-bold text-ink">{fmt(pkg.monthly_price)}<span className="text-xs font-medium text-ink-muted">/mo</span></p>

                <div className="mt-3.5 space-y-1.5 border-t border-border/40 pt-2.5">
                  {pkg.feature_keys.map((item) => {
                    const row = byKey.get(item.feature_key);
                    if (!row) return null;
                    return (
                      <div key={item.feature_key} className="flex items-center justify-between text-xs text-ink-muted">
                        <span>{row.display_name}</span>
                        {item.quantity > 1 && (
                          <span className="font-semibold font-mono text-[10px] bg-surface-mid px-1 rounded-xs">
                            ×{item.quantity}
                          </span>
                        )}
                      </div>
                    );
                  })}
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {(inbound || outbound) && (itemInAddonMode(inbound) || itemInAddonMode(outbound)) && (
        <div>
          <SectionHeading>Messaging</SectionHeading>
          <p className="mb-3 -mt-2 text-xs text-ink-muted">
            Conversations, Segments, Numbers Pool, Knowledge Base &amp; Analytics come free with either channel below.
          </p>
          <div className="grid gap-3 sm:grid-cols-2">
            {inbound && itemInAddonMode(inbound) && (
              <SelectCard
                selected={inbound.feature_key in selected}
                onClick={() => toggleItem(inbound.feature_key)}
                icon={ICONS.inbound_messaging}
                title="Inbound Messaging"
                subtitle={`${fmt(inbound.monthly_price)}/mo · Instagram, Facebook & Telegram included`}
              />
            )}
            {outbound && itemInAddonMode(outbound) && (
              <SelectCard
                selected={outbound.feature_key in selected}
                onClick={() => toggleItem(outbound.feature_key)}
                icon={ICONS.outbound_messaging}
                title="Outbound Messaging"
                subtitle={`${fmt(outbound.monthly_price)}/mo · WhatsApp · Templates included · ${outbound.included_qty ?? 1000} msgs/mo`}
              />
            )}
          </div>
        </div>
      )}

      {(sim || telecmi || upload || seats) && (itemInAddonMode(sim) || itemInAddonMode(telecmi) || itemInAddonMode(upload) || itemInAddonMode(seats)) && (
        <div>
          <SectionHeading>Telecalling</SectionHeading>
          <div className="space-y-3">
            {(sim && itemInAddonMode(sim)) || (telecmi && itemInAddonMode(telecmi)) ? (
              <div className="grid gap-3 sm:grid-cols-2">
                {sim && itemInAddonMode(sim) && (
                  <SelectCard
                    selected={sim.feature_key in selected}
                    onClick={() => selectTelecallingType(sim.feature_key)}
                    icon={ICONS.telecalling_sim}
                    title="SIM-based"
                    subtitle={`${fmt(sim.monthly_price)}/mo · Dialer, Scheduled Calls & Notes included`}
                  />
                )}
                {telecmi && itemInAddonMode(telecmi) && (
                  <SelectCard
                    selected={telecmi.feature_key in selected}
                    onClick={() => selectTelecallingType(telecmi.feature_key)}
                    icon={ICONS.telecalling_telecmi}
                    title="Tele-CMI"
                    subtitle={`${fmt(telecmi.monthly_price)}/mo · ${telecmi.included_qty ?? 500} call minutes/mo included`}
                  />
                )}
              </div>
            ) : null}

            {seats && itemInAddonMode(seats) && (
              <div className="flex items-center justify-between rounded-2xl border border-border bg-white p-4">
                <div className="flex items-center gap-3">
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-surface-mid text-ink-muted">
                    <ICONS.telecaller_seats size={17} />
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-ink">Telecaller Seats</p>
                    <p className="text-xs text-ink-muted">
                      1 seat included · +{fmt(seats.unit_price ?? 0)} per extra seat
                      {existingQtyFor(seats.feature_key) > 0 && ` · currently ${existingQtyFor(seats.feature_key)}`}
                    </p>
                  </div>
                </div>
                <Stepper
                  value={selected[seats.feature_key] ?? 1}
                  onChange={(v) => setSelected((prev) => ({ ...prev, [seats.feature_key]: v }))}
                />
              </div>
            )}

            {upload && itemInAddonMode(upload) && (
              <SelectCard
                selected={upload.feature_key in selected}
                onClick={() => toggleItem(upload.feature_key)}
                icon={ICONS.bulk_lead_upload}
                title="Bulk Lead Upload"
                subtitle={`${fmt(upload.monthly_price)}/mo · CSV upload for telecalling campaigns · optional add-on`}
                disabled={!hasTelecallingCoverage}
              />
            )}
          </div>
        </div>
      )}

      {numbers && itemInAddonMode(numbers) && (
        <div>
          <SectionHeading>Numbers Pool</SectionHeading>
          <div className="flex items-center justify-between rounded-2xl border border-border bg-white p-4">
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-surface-mid text-ink-muted">
                <ICONS.numbers_pool size={17} />
              </div>
              <div>
                <p className="text-sm font-semibold text-ink">Phone Numbers</p>
                <p className="text-xs text-ink-muted">
                  1 number included with messaging/telecalling · +{fmt(numbers.unit_price ?? 0)} per extra number
                  {existingQtyFor(numbers.feature_key) > 0 && ` · currently ${existingQtyFor(numbers.feature_key)}`}
                </p>
              </div>
            </div>
            <Stepper
              value={selected[numbers.feature_key] ?? 1}
              onChange={(v) => setSelected((prev) => ({ ...prev, [numbers.feature_key]: v }))}
            />
          </div>
        </div>
      )}



      <div className="sticky bottom-0 flex items-center justify-between rounded-2xl border border-border bg-white/95 p-4 shadow-lg backdrop-blur">
        <div>
          <p className="text-xs font-medium text-ink-muted">{mode === "addon" ? "Additional monthly cost" : "Total"}</p>
          <p className="text-2xl font-bold text-ink">{fmt(total)}<span className="text-sm font-medium text-ink-muted">/mo</span></p>
        </div>
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
