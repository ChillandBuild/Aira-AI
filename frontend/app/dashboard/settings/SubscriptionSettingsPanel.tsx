"use client";
import { useEffect, useState } from "react";
import { API_URL, getAuthHeaders } from "@/lib/api";
import { CartBuilder, SubscriptionItem } from "../subscriptions/CartBuilder";

interface UsageMetric { metric: string; used: number; included: number; hard_cap: number | null }
interface MeResponse {
  status: string; mrr: number; items: (SubscriptionItem & { unit_price_snapshot: number })[];
  usage: UsageMetric[];
  latest_request: { status: string; total_amount: number; submitted_at: string } | null;
}

const METRIC_LABELS: Record<string, string> = {
  message_sent: "Outbound Messages", ai_reply: "AI Replies", call_minute: "Call Minutes",
  team_seat_active: "Telecaller Seats", phone_number: "Phone Numbers",
  storage_gb: "Storage (GB)", ai_call_summary: "AI Call Summaries", ai_call_scoring: "AI Call Scoring",
};

export function SubscriptionSettingsPanel() {
  const [me, setMe] = useState<MeResponse | null>(null);
  const [showAddon, setShowAddon] = useState(false);
  const [loading, setLoading] = useState(true);

  async function load() {
    const auth = await getAuthHeaders();
    const res = await fetch(`${API_URL}/api/v1/subscriptions/me`, { headers: auth });
    if (res.ok) setMe(await res.json());
    setLoading(false);
  }

  useEffect(() => { load(); }, []);

  if (loading || !me) return <div className="text-sm text-ink-muted">Loading…</div>;

  return (
    <div className="space-y-6">
      <div className="card rounded-3xl p-6">
        <p className="text-sm text-ink-muted">Monthly total</p>
        <p className="text-3xl font-bold text-ink">₹{me.mrr.toLocaleString("en-IN")}<span className="text-sm font-medium text-ink-muted">/mo</span></p>
        <div className="mt-4 divide-y divide-border-subtle">
          {me.items.map((item) => (
            <div key={item.feature_key} className="flex justify-between py-2 text-sm">
              <span className="text-ink">{item.feature_key}</span>
              <span className="text-ink-muted">×{item.quantity} · ₹{item.unit_price_snapshot.toLocaleString("en-IN")}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="card rounded-3xl p-6">
        <p className="mb-3 text-sm font-semibold text-ink">Usage this cycle</p>
        <div className="divide-y divide-border-subtle">
          {me.usage.map((u) => {
            const pct = u.included > 0 ? Math.min(100, (u.used / u.included) * 100) : 0;
            return (
              <div key={u.metric} className="py-3">
                <div className="mb-1 flex justify-between text-sm">
                  <span className="text-ink">{METRIC_LABELS[u.metric] ?? u.metric}</span>
                  <span className="text-ink-muted">{u.used} / {u.included || "0"}</span>
                </div>
                <div className="h-2 rounded-full bg-surface-mid">
                  <div className={`h-full rounded-full ${pct >= 100 ? "bg-danger" : pct >= 80 ? "bg-warning" : "bg-success"}`} style={{ width: `${pct}%` }} />
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {me.latest_request?.status === "submitted" ? (
        <div className="rounded-xl bg-amber-50 border border-amber-200 p-4 text-sm text-amber-800">
          A request for ₹{me.latest_request.total_amount.toLocaleString("en-IN")}/mo is awaiting admin approval.
        </div>
      ) : showAddon ? (
        <div className="card rounded-3xl p-6">
          <CartBuilder mode="addon" existingItems={me.items} onSubmitted={() => { setShowAddon(false); load(); }} />
        </div>
      ) : (
        <button onClick={() => setShowAddon(true)} className="btn-primary">Request more</button>
      )}
    </div>
  );
}
