"use client";
import { useEffect, useState } from "react";
import { CheckCircle2, AlertTriangle, XCircle, Shield } from "lucide-react";
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
  return res.json() as Promise<T>;
}

interface ConfigData {
  enabled_features: string[];
  credentials_status: Record<string, "configured" | "incomplete" | "not_configured">;
  settings: {
    ai_auto_reply_enabled: boolean;
    reengagement_enabled: boolean;
    booking_event_name: string | null;
    booking_ref_prefix: string | null;
    booking_amount_paise: string | null;
  };
}

const CRED_LABELS: Record<string, string> = {
  whatsapp: "WhatsApp (Meta)",
  telecalling: "TeleCMI",
  ai: "Groq AI",
  payments: "Razorpay",
};

function statusBadge(status: string) {
  switch (status) {
    case "configured":
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-success/10 text-success">
          <CheckCircle2 size={12} /> Configured
        </span>
      );
    case "incomplete":
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-warning/10 text-warning">
          <AlertTriangle size={12} /> Incomplete
        </span>
      );
    default:
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-surface-mid text-ink-muted">
          <XCircle size={12} /> Not Configured
        </span>
      );
  }
}

export function ConfigView({ tenantId }: { tenantId: string }) {
  const [config, setConfig] = useState<ConfigData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<ConfigData>(`/api/v1/operator/clients/${tenantId}/config`)
      .then(setConfig)
      .catch(e => setError(e instanceof Error ? e.message : "Failed to load config"))
      .finally(() => setLoading(false));
  }, [tenantId]);

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-2 gap-4">
          {Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} />)}
        </div>
        <div className="grid grid-cols-3 gap-4">
          {Array.from({ length: 3 }).map((_, i) => <SkeletonCard key={i} />)}
        </div>
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

  if (!config) return null;

  return (
    <div className="space-y-6">
      {/* Credential Status */}
      <div>
        <h3 className="text-sm font-semibold text-ink mb-3 flex items-center gap-2">
          <Shield size={16} className="text-ink-muted" />
          Credential Status
        </h3>
        <div className="grid grid-cols-2 gap-4">
          {Object.entries(config.credentials_status).map(([provider, status]) => (
            <div key={provider} className="bg-white rounded-card border border-border p-4 shadow-sm">
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium text-ink">{CRED_LABELS[provider] || provider}</p>
                {statusBadge(status)}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Key Settings */}
      <div>
        <h3 className="text-sm font-semibold text-ink mb-3">Key Settings</h3>
        <div className="grid grid-cols-3 gap-4">
          <div className="bg-white rounded-card border border-border p-4 shadow-sm">
            <p className="text-xs text-ink-muted uppercase tracking-wider mb-1">AI Auto-Reply</p>
            <p className={`text-sm font-medium ${config.settings.ai_auto_reply_enabled ? "text-success" : "text-ink-muted"}`}>
              {config.settings.ai_auto_reply_enabled ? "Enabled" : "Disabled"}
            </p>
          </div>
          <div className="bg-white rounded-card border border-border p-4 shadow-sm">
            <p className="text-xs text-ink-muted uppercase tracking-wider mb-1">Re-engagement</p>
            <p className={`text-sm font-medium ${config.settings.reengagement_enabled ? "text-success" : "text-ink-muted"}`}>
              {config.settings.reengagement_enabled ? "Enabled" : "Disabled"}
            </p>
          </div>
          <div className="bg-white rounded-card border border-border p-4 shadow-sm">
            <p className="text-xs text-ink-muted uppercase tracking-wider mb-1">Booking</p>
            <p className={`text-sm font-medium ${config.settings.booking_event_name ? "text-success" : "text-ink-muted"}`}>
              {config.settings.booking_event_name ? "Enabled" : "Disabled"}
            </p>
            {config.settings.booking_event_name && (
              <p className="text-xs text-ink-muted mt-1">Event: {config.settings.booking_event_name}</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
