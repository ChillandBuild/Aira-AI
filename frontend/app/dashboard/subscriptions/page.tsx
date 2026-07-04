"use client";
import { useEffect, useState } from "react";
import { API_URL, getAuthHeaders } from "@/lib/api";
import { CartBuilder, SubscriptionItem } from "./CartBuilder";

interface LatestRequest {
  requested_items: unknown[];
  total_amount: number;
  status: string;
  rejection_reason: string | null;
}

interface MeResponse {
  status: "none" | "pending_approval" | "active";
  items: SubscriptionItem[];
  latest_request: LatestRequest | null;
}

export default function SubscriptionsPage() {
  const [me, setMe] = useState<MeResponse | null>(null);
  const [loading, setLoading] = useState(true);

  async function load() {
    const auth = await getAuthHeaders();
    const res = await fetch(`${API_URL}/api/v1/subscriptions/me`, { headers: auth });
    if (res.ok) setMe(await res.json());
    setLoading(false);
  }

  useEffect(() => { load(); }, []);

  if (loading) return <div className="min-h-screen flex items-center justify-center">Loading…</div>;

  const isPending = me?.status === "pending_approval";
  const wasRejected = me?.latest_request?.status === "rejected";

  return (
    <div className="min-h-screen bg-background flex items-start justify-center p-6">
      <div className="w-full max-w-3xl space-y-6">
        <div>
          <h1 className="font-display text-2xl font-bold text-ink">Choose your plan</h1>
          <p className="text-sm text-ink-muted">Pick the features you need — your account unlocks once an admin approves your request.</p>
        </div>

        {wasRejected && me?.latest_request?.rejection_reason && (
          <div className="rounded-xl bg-amber-50 border border-amber-200 p-4 text-sm text-amber-800">
            Your previous request was declined: {me.latest_request.rejection_reason}. Please revise and resubmit below.
          </div>
        )}

        {isPending && !wasRejected ? (
          <div className="rounded-2xl border border-border bg-white p-8 text-center">
            <p className="font-semibold text-ink">Submitted — awaiting admin approval</p>
            <p className="mt-2 text-sm text-ink-muted">We&apos;ll notify you as soon as it&apos;s reviewed.</p>
          </div>
        ) : (
          <CartBuilder mode="initial" existingItems={me?.items ?? []} onSubmitted={load} />
        )}
      </div>
    </div>
  );
}
