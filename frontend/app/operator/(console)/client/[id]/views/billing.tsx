"use client";
import { useEffect, useState } from "react";
import { CreditCard, AlertTriangle, IndianRupee, Activity } from "lucide-react";
import { API_URL, getAuthHeaders } from "@/lib/api";
import { SkeletonCard } from "../components/skeleton";

async function apiFetch<T>(path: string): Promise<T> {
  const auth = await getAuthHeaders();
  const res = await fetch(`${API_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...auth },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail || "Request failed");
  }
  const json = await res.json();
  return ((json as { data?: T }).data ?? json) as T;
}

interface PlanSummary {
  id: string;
  name: string;
  monthly_price: number;
}

interface Subscription {
  plan_id: string | null;
  mrr: number;
  plan: PlanSummary | null;
}

interface UsageMetric {
  metric: string;
  used: number;
  included: number;
  hard_cap: number | null;
}

const METRIC_LABELS: Record<string, string> = {
  message_sent: "Messages",
  ai_reply: "AI Replies",
  call_minute: "Call Minutes",
  team_seat_active: "Team Seats",
  storage_gb: "Storage (GB)",
  ai_call_summary: "AI Call Summaries",
  ai_call_scoring: "AI Call Scoring",
};

function meterColor(pct: number): { bar: string; text: string } {
  if (pct >= 100) return { bar: "bg-danger", text: "text-danger" };
  if (pct >= 80) return { bar: "bg-warning", text: "text-warning" };
  return { bar: "bg-success", text: "text-success" };
}

function UsageMeterRow({ item }: { item: UsageMetric }) {
  const label = METRIC_LABELS[item.metric] || item.metric;
  const unlimited = item.included <= 0;
  const pct = unlimited ? 0 : (item.used / item.included) * 100;
  const clampedPct = Math.min(100, Math.max(0, pct));
  const nearCap = !unlimited && item.used >= item.included * 0.8;
  const { bar, text } = meterColor(pct);

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
          <span className="text-ink-muted">
            / {unlimited ? "Unlimited" : item.included.toLocaleString("en-IN")}
          </span>
          {!unlimited && (
            <span className={`font-semibold ${text}`}>{Math.round(pct)}%</span>
          )}
        </div>
      </div>
      {unlimited ? (
        <div className="flex h-2 items-center">
          <span className="text-xs text-ink-muted">—</span>
        </div>
      ) : (
        <div className="h-2 w-full overflow-hidden rounded-full bg-surface-mid">
          <div
            className={`h-full rounded-full transition-all duration-500 ${bar}`}
            style={{ width: `${clampedPct}%` }}
          />
        </div>
      )}
    </div>
  );
}

export function BillingView({ tenantId }: { tenantId: string }) {
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [usage, setUsage] = useState<UsageMetric[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      apiFetch<Subscription>(`/api/v1/operator/clients/${tenantId}/subscription`),
      apiFetch<UsageMetric[]>(`/api/v1/operator/clients/${tenantId}/usage`),
    ])
      .then(([sub, use]) => {
        setSubscription(sub);
        setUsage(Array.isArray(use) ? use : []);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load billing"))
      .finally(() => setLoading(false));
  }, [tenantId]);

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => <SkeletonCard key={i} />)}
        </div>
        <SkeletonCard />
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-xl border border-danger/20 bg-red-50 p-4 text-sm text-danger">
        {error}
      </div>
    );
  }

  if (!subscription) return null;

  return (
    <div className="space-y-6">
      {/* Billing summary */}
      <div>
        <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-ink">
          <CreditCard size={16} className="text-ink-muted" />
          Subscription
        </h3>
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {/* MRR — prominent */}
          <div className="rounded-card border border-border bg-gradient-to-br from-primary-light to-white p-5 shadow-sm">
            <div className="mb-2 flex items-center gap-2 text-primary">
              <IndianRupee size={16} />
              <span className="font-label text-xs font-medium uppercase tracking-wider">Monthly Recurring</span>
            </div>
            <p className="text-3xl font-bold text-ink">
              ₹{(subscription.mrr || 0).toLocaleString("en-IN")}
              <span className="ml-1 text-sm font-medium text-ink-muted">/mo</span>
            </p>
          </div>

          {/* Plan */}
          <div className="rounded-card border border-border bg-white p-5 shadow-sm">
            <div className="mb-3 flex items-center gap-2 text-ink-muted">
              <CreditCard size={16} />
              <span className="font-label text-xs font-medium uppercase tracking-wider">Plan</span>
            </div>
            {subscription.plan ? (
              <p className="text-sm font-semibold text-ink">{subscription.plan.name}</p>
            ) : (
              <p className="text-sm text-ink-muted">No plan assigned.</p>
            )}
          </div>
        </div>
      </div>

      {/* Usage meters */}
      <div>
        <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-ink">
          <Activity size={16} className="text-ink-muted" />
          Usage This Cycle
        </h3>
        <div className="rounded-card border border-border bg-white px-5 py-4 shadow-sm">
          {usage.length > 0 ? (
            <div className="divide-y divide-border-subtle">
              {usage.map((item) => (
                <UsageMeterRow key={item.metric} item={item} />
              ))}
            </div>
          ) : (
            <p className="py-4 text-center text-sm text-ink-muted">No usage recorded this cycle.</p>
          )}
        </div>
      </div>
    </div>
  );
}
