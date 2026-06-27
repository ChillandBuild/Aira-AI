"use client";
import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, Loader2, RadioTower, Shield, Smartphone, XCircle } from "lucide-react";
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
  };
}

interface CallingProviderData {
  tenant_id: string;
  calling_provider: "telecmi" | "sim_basic";
  telecalling_enabled: boolean;
}

const CRED_LABELS: Record<string, string> = {
  whatsapp: "WhatsApp (Meta)",
  telecalling: "TeleCMI",
  ai: "Groq AI",
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
  const [provider, setProvider] = useState<CallingProviderData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [providerSaving, setProviderSaving] = useState<"telecmi" | "sim_basic" | null>(null);

  useEffect(() => {
    Promise.all([
      apiFetch<ConfigData>(`/api/v1/operator/clients/${tenantId}/config`),
      apiFetch<CallingProviderData>(`/api/v1/operator/clients/${tenantId}/calling-provider`),
    ])
      .then(([configData, providerData]) => {
        setConfig(configData);
        setProvider(providerData);
      })
      .catch(e => setError(e instanceof Error ? e.message : "Failed to load config"))
      .finally(() => setLoading(false));
  }, [tenantId]);

  async function updateProvider(callingProvider: "telecmi" | "sim_basic") {
    if (!provider || provider.calling_provider === callingProvider) return;
    setProviderSaving(callingProvider);
    setError(null);
    try {
      const saved = await apiFetch<{ tenant_id: string; calling_provider: "telecmi" | "sim_basic" }>(
        `/api/v1/operator/clients/${tenantId}/calling-provider`,
        { method: "PATCH", body: JSON.stringify({ calling_provider: callingProvider }) },
      );
      setProvider({ ...provider, calling_provider: saved.calling_provider });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update calling provider");
    } finally {
      setProviderSaving(null);
    }
  }

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
      {/* Calling Provider */}
      <div>
        <h3 className="text-sm font-semibold text-ink mb-3 flex items-center gap-2">
          <RadioTower size={16} className="text-ink-muted" />
          Calling Provider
        </h3>
        <div className="grid gap-4 md:grid-cols-2">
          {[
            {
              id: "telecmi" as const,
              title: "TeleCMI",
              desc: "API calling with automatic call logs, duration, recordings, and webhooks.",
              icon: RadioTower,
            },
            {
              id: "sim_basic" as const,
              title: "SIM Basic",
              desc: "Mobile SIM calling with manual wrap-up, duration, and notes.",
              icon: Smartphone,
            },
          ].map((option) => {
            const Icon = option.icon;
            const selected = provider?.calling_provider === option.id;
            const saving = providerSaving === option.id;
            return (
              <button
                key={option.id}
                type="button"
                onClick={() => updateProvider(option.id)}
                disabled={!!providerSaving}
                className={`rounded-card border p-4 text-left shadow-sm transition-all ${
                  selected
                    ? "border-primary bg-primary-light text-ink ring-1 ring-primary/10"
                    : "border-border bg-white hover:border-primary-muted"
                } ${providerSaving ? "opacity-70" : ""}`}
              >
                <div className="flex items-start gap-3">
                  <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${selected ? "bg-white text-primary" : "bg-surface-mid text-ink-muted"}`}>
                    {saving ? <Loader2 size={18} className="animate-spin" /> : <Icon size={18} />}
                  </div>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-semibold text-ink">{option.title}</p>
                      {selected && statusBadge("configured")}
                    </div>
                    <p className="mt-1 text-xs leading-relaxed text-ink-muted">{option.desc}</p>
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      </div>

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
        </div>
      </div>
    </div>
  );
}
