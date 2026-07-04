"use client";
import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ClipboardList, Check, X } from "lucide-react";
import { operatorFetch } from "@/lib/operator";

interface RequestedItem {
  feature_key: string;
  quantity: number;
  line_total: number;
}

interface SubscriptionRequest {
  id: string;
  tenant_id: string;
  tenant_name: string;
  status: "submitted" | "approved" | "rejected";
  requested_items: RequestedItem[];
  package_id: string | null;
  total_amount: number;
  is_initial: boolean;
  payment_confirmed: boolean;
  submitted_at: string;
}

function RequestCard({ request, onReviewed }: { request: SubscriptionRequest; onReviewed: () => void }) {
  const [paymentConfirmed, setPaymentConfirmed] = useState(false);
  const [showReject, setShowReject] = useState(false);
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function approve() {
    setSubmitting(true);
    setError(null);
    try {
      await operatorFetch(`/api/v1/operator/subscription-requests/${request.id}`, {
        method: "PATCH",
        body: JSON.stringify({ action: "approve", payment_confirmed: true }),
      });
      onReviewed();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to approve");
    } finally {
      setSubmitting(false);
    }
  }

  async function reject() {
    if (!reason.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      await operatorFetch(`/api/v1/operator/subscription-requests/${request.id}`, {
        method: "PATCH",
        body: JSON.stringify({ action: "reject", rejection_reason: reason.trim() }),
      });
      onReviewed();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to reject");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="bg-white rounded-card border border-border p-5 shadow-sm space-y-4">
      <div className="flex items-start justify-between">
        <div>
          <h3 className="text-sm font-semibold text-ink">{request.tenant_name}</h3>
          <p className="text-xs text-ink-muted mt-0.5">
            {request.is_initial ? "Initial subscription" : "Top-up request"} · {new Date(request.submitted_at).toLocaleString("en-IN")}
          </p>
        </div>
        <span className="text-lg font-bold text-primary">₹{request.total_amount.toLocaleString("en-IN")}<span className="text-xs font-medium text-ink-muted">/mo</span></span>
      </div>

      <div className="divide-y divide-border-subtle border border-border-subtle rounded-xl px-3">
        {request.requested_items.map(item => (
          <div key={item.feature_key} className="flex items-center justify-between py-2 text-sm">
            <span className="text-ink">{item.feature_key} {item.quantity > 1 && <span className="text-ink-muted">×{item.quantity}</span>}</span>
            <span className="text-ink-muted">₹{item.line_total.toLocaleString("en-IN")}</span>
          </div>
        ))}
      </div>

      {error && <div className="p-2.5 bg-red-50 border border-danger/20 rounded-lg text-xs text-danger">{error}</div>}

      {request.status === "submitted" && (
        <div className="space-y-3">
          <label className="flex items-center gap-2 text-sm text-ink-secondary cursor-pointer">
            <input type="checkbox" checked={paymentConfirmed} onChange={e => setPaymentConfirmed(e.target.checked)} className="rounded border-border" />
            Payment confirmed received
          </label>

          {showReject ? (
            <div className="space-y-2">
              <input
                value={reason}
                onChange={e => setReason(e.target.value)}
                placeholder="Reason for rejection"
                className="w-full border border-border rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20"
              />
              <div className="flex gap-2">
                <button onClick={() => setShowReject(false)} className="flex-1 px-3 py-2 border border-border text-sm text-ink-secondary rounded-xl hover:bg-surface-mid">
                  Cancel
                </button>
                <button
                  onClick={reject}
                  disabled={submitting || !reason.trim()}
                  className="flex-1 px-3 py-2 bg-danger text-white text-sm font-medium rounded-xl hover:bg-danger/90 disabled:opacity-50"
                >
                  {submitting ? "Rejecting…" : "Confirm Reject"}
                </button>
              </div>
            </div>
          ) : (
            <div className="flex gap-2">
              <button
                onClick={() => setShowReject(true)}
                disabled={submitting}
                className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 border border-border text-sm text-ink-secondary rounded-xl hover:bg-surface-mid"
              >
                <X size={14} /> Reject
              </button>
              <button
                onClick={approve}
                disabled={submitting || !paymentConfirmed}
                className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 bg-primary text-white text-sm font-medium rounded-xl hover:bg-primary-dark disabled:opacity-50"
              >
                <Check size={14} /> {submitting ? "Approving…" : "Approve"}
              </button>
            </div>
          )}
        </div>
      )}

      {request.status !== "submitted" && (
        <span className={`inline-block text-xs font-medium px-2 py-0.5 rounded-full ${request.status === "approved" ? "bg-success/10 text-success" : "bg-danger/10 text-danger"}`}>
          {request.status === "approved" ? "Approved" : "Rejected"}
        </span>
      )}
    </div>
  );
}

export default function SubscriptionRequestsPage() {
  const searchParams = useSearchParams();
  const tenantFilter = searchParams.get("tenant_id");

  const [requests, setRequests] = useState<SubscriptionRequest[]>([]);
  const [statusFilter, setStatusFilter] = useState<string>("submitted");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    const query = statusFilter ? `?status=${statusFilter}` : "";
    return operatorFetch<{ data: SubscriptionRequest[] }>(`/api/v1/operator/subscription-requests${query}`)
      .then(res => {
        const data = tenantFilter ? (res.data ?? []).filter(r => r.tenant_id === tenantFilter) : res.data ?? [];
        setRequests(data);
        setError(null);
      })
      .catch(e => setError(e instanceof Error ? e.message : "Request failed"))
      .finally(() => setLoading(false));
  }, [statusFilter, tenantFilter]);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="p-7 space-y-6">
      <div>
        <h1 className="font-display text-lg font-bold text-ink">Subscription Requests</h1>
        <p className="text-xs text-ink-muted mt-0.5">
          {tenantFilter ? "Filtered to one tenant." : "Cart submissions and top-up asks awaiting review."}
        </p>
      </div>

      <div className="flex gap-2">
        {(["submitted", "approved", "rejected"] as const).map(s => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            className={`px-3 py-1.5 rounded-xl text-xs font-medium capitalize transition-colors ${
              statusFilter === s ? "bg-primary text-white" : "bg-surface-mid text-ink-secondary hover:text-ink"
            }`}
          >
            {s}
          </button>
        ))}
      </div>

      {error && <div className="p-3 bg-red-50 border border-danger/20 rounded-xl text-sm text-danger">{error}</div>}

      {loading ? (
        <div className="text-sm text-ink-muted">Loading…</div>
      ) : requests.length === 0 ? (
        <div className="rounded-card border border-dashed border-border p-10 text-center">
          <ClipboardList size={28} className="mx-auto text-ink-muted mb-3" />
          <p className="text-sm font-medium text-ink">No {statusFilter} requests</p>
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {requests.map(r => (
            <RequestCard key={r.id} request={r} onReviewed={load} />
          ))}
        </div>
      )}
    </div>
  );
}
