"use client";
import { useEffect, useState } from "react";
import { AlertTriangle, CreditCard, Activity, ArrowRight } from "lucide-react";
import { API_URL, getAuthHeaders } from "@/lib/api";
import { CartBuilder, SubscriptionItem } from "../subscriptions/CartBuilder";

interface CatalogRow { feature_key: string; display_name: string }
interface UsageMetric { metric: string; used: number; included: number; hard_cap: number | null }
interface MeResponse {
  status: string;
  mrr: number;
  items: (SubscriptionItem & { unit_price_snapshot: number })[];
  usage: UsageMetric[];
  latest_request: { status: string; total_amount: number; submitted_at: string; rejection_reason: string | null } | null;
}

const METRIC_LABELS: Record<string, string> = {
  message_sent: "Outbound Messages", ai_reply: "AI Replies", call_minute: "Call Minutes",
  team_seat_active: "Telecaller Seats", phone_number: "Phone Numbers",
  storage_gb: "Storage (GB)", ai_call_summary: "AI Call Summaries", ai_call_scoring: "AI Call Scoring",
};

function UsageMeterRow({ item }: { item: UsageMetric }) {
  const label = METRIC_LABELS[item.metric] ?? item.metric;
  const unlimited = item.included <= 0;
  const pct = unlimited ? 0 : (item.used / item.included) * 100;
  const clamped = Math.min(100, Math.max(0, pct));
  const nearCap = !unlimited && item.used >= item.included * 0.8;
  const bar = pct >= 100 ? "bg-danger" : pct >= 80 ? "bg-warning" : "bg-success";
  const text = pct >= 100 ? "text-danger" : pct >= 80 ? "text-warning" : "text-success";

  return (
    <div className="py-3.5 first:pt-0 last:pb-0">
      <div className="mb-2 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-sm font-medium text-ink truncate">{label}</span>
          {nearCap && (
            <span className="inline-flex items-center gap-1 rounded-full bg-warning/10 px-2 py-0.5 text-[11px] font-medium text-warning">
              <AlertTriangle size={11} /> Near cap
            </span>
          )}
        </div>
        <div className="flex items-baseline gap-2 shrink-0 font-mono text-xs">
          <span className="font-semibold text-ink">{item.used.toLocaleString("en-IN")}</span>
          <span className="text-ink-muted">/ {unlimited ? "Unlimited" : item.included.toLocaleString("en-IN")}</span>
          {!unlimited && <span className={`font-semibold ${text}`}>{Math.round(pct)}%</span>}
        </div>
      </div>
      {!unlimited && (
        <div className="h-2 w-full overflow-hidden rounded-full bg-surface-mid">
          <div className={`h-full rounded-full transition-all duration-500 ${bar}`} style={{ width: `${clamped}%` }} />
        </div>
      )}
    </div>
  );
}

export default function SubscriptionPage() {
  const [me, setMe] = useState<MeResponse | null>(null);
  const [catalog, setCatalog] = useState<CatalogRow[]>([]);
  const [showAddon, setShowAddon] = useState(false);
  const [loading, setLoading] = useState(true);

  async function load() {
    const auth = await getAuthHeaders();
    const [meRes, catalogRes] = await Promise.all([
      fetch(`${API_URL}/api/v1/subscriptions/me`, { headers: auth }),
      fetch(`${API_URL}/api/v1/subscriptions/catalog`, { headers: auth }),
    ]);
    if (meRes.ok) setMe(await meRes.json());
    if (catalogRes.ok) setCatalog((await catalogRes.json()).catalog ?? []);
    setLoading(false);
  }

  useEffect(() => { load(); }, []);

  if (loading || !me) {
    return (
      <div className="flex items-center justify-center gap-2 p-16 text-ink-muted">
        <div className="h-4 w-4 animate-spin rounded-full border-2 border-primary border-t-transparent" />
        Loading subscription…
      </div>
    );
  }

  const catalogByKey = new Map(catalog.map((c) => [c.feature_key, c]));
  const isPending = me.latest_request?.status === "submitted";

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="font-display text-2xl font-bold text-ink">Subscription</h1>
        <p className="text-sm text-ink-muted">Your plan, usage, and add-ons.</p>
      </div>

      <div className="rounded-3xl border border-border bg-gradient-to-br from-primary-light to-white p-6 shadow-sm">
        <div className="mb-4 flex items-center justify-between">
          <div className="flex items-center gap-2 text-primary">
            <CreditCard size={16} />
            <span className="font-label text-xs font-medium uppercase tracking-wider">Monthly total</span>
          </div>
          <span className="rounded-full bg-white px-2.5 py-1 text-xs font-semibold capitalize text-ink-secondary shadow-sm">
            {me.status.replace("_", " ")}
          </span>
        </div>
        <p className="mb-4 text-4xl font-bold text-ink">
          ₹{me.mrr.toLocaleString("en-IN")}<span className="text-sm font-medium text-ink-muted">/mo</span>
        </p>
        <div className="divide-y divide-border-subtle rounded-2xl bg-white/70 px-4">
          {me.items.length > 0 ? me.items.map((item) => (
            <div key={item.feature_key} className="flex justify-between py-2.5 text-sm">
              <span className="text-ink">{catalogByKey.get(item.feature_key)?.display_name ?? item.feature_key}</span>
              <span className="text-ink-muted">
                {item.quantity > 1 && `×${item.quantity} · `}₹{item.unit_price_snapshot.toLocaleString("en-IN")}
              </span>
            </div>
          )) : (
            <p className="py-3 text-sm text-ink-muted">No items yet.</p>
          )}
        </div>
      </div>

      <div className="rounded-3xl border border-border bg-white p-6 shadow-sm">
        <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-ink">
          <Activity size={16} className="text-ink-muted" /> Usage this cycle
        </h3>
        {me.usage.length > 0 ? (
          <div className="divide-y divide-border-subtle">
            {me.usage.map((u) => <UsageMeterRow key={u.metric} item={u} />)}
          </div>
        ) : (
          <p className="text-sm text-ink-muted">No usage recorded this cycle.</p>
        )}
      </div>

      {isPending ? (
        <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
          A request for ₹{me.latest_request!.total_amount.toLocaleString("en-IN")}/mo is awaiting admin approval.
        </div>
      ) : showAddon ? (
        <div className="rounded-3xl border border-border bg-white p-6 shadow-sm">
          <h3 className="mb-4 text-sm font-semibold text-ink">Add to your plan</h3>
          <CartBuilder mode="addon" existingItems={me.items} onSubmitted={() => { setShowAddon(false); load(); }} />
        </div>
      ) : (
        <button onClick={() => setShowAddon(true)} className="btn-primary flex items-center gap-1.5">
          Request more <ArrowRight size={14} />
        </button>
      )}
    </div>
  );
}
