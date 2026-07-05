"use client";
import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, Loader2, RadioTower, Shield, Smartphone, Sparkles, XCircle } from "lucide-react";
import { toast } from "sonner";
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

type RetrievalMode = "semantic" | "keyword" | "hybrid";

const RETRIEVAL_MODES: { id: RetrievalMode; label: string; desc: string }[] = [
  { id: "semantic", label: "Smart", desc: "Understands meaning & language (Tamil/English), even when a lead rephrases. Recommended." },
  { id: "keyword", label: "Exact words", desc: "Matches the exact words in your documents. Fastest, no AI cost — weaker on reworded questions." },
  { id: "hybrid", label: "Best of both", desc: "Blends meaning + exact words for the highest accuracy." },
];

interface ConfigData {
  enabled_features: string[];
  credentials_status: Record<string, "configured" | "incomplete" | "not_configured">;
  settings: {
    ai_auto_reply_enabled: boolean;
    reengagement_enabled: boolean;
    kb_retrieval_mode: RetrievalMode;
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
  ai: "Sarvam AI",
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
  const [pendingProvider, setPendingProvider] = useState<"telecmi" | "sim_basic" | null>(null);
  const [retrievalSaving, setRetrievalSaving] = useState<RetrievalMode | null>(null);

  async function updateRetrievalMode(mode: RetrievalMode) {
    if (!config || config.settings.kb_retrieval_mode === mode) return;
    setRetrievalSaving(mode);
    setError(null);
    try {
      await apiFetch<{ status: string }>(
        `/api/v1/operator/clients/${tenantId}/config`,
        {
          method: "PATCH",
          body: JSON.stringify({
            settings: { kb_retrieval_mode: mode }
          })
        }
      );
      setConfig({
        ...config,
        settings: {
          ...config.settings,
          kb_retrieval_mode: mode
        }
      });
      toast.success(`Knowledge search mode set to "${RETRIEVAL_MODES.find(m => m.id === mode)?.label}".`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update knowledge search mode");
      toast.error("Failed to update search mode. Please try again.");
    } finally {
      setRetrievalSaving(null);
    }
  }

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

  const pendingProviderCopy = pendingProvider === "sim_basic"
    ? {
        title: "Switch to SIM Basic?",
        description: "This client will use mobile SIM calling with manual call wrap-up. TeleCMI agent credentials, automatic recordings, and exact provider call duration will no longer drive new calls.",
        confirm: "Switch to SIM Basic",
      }
    : {
        title: "Switch to TeleCMI?",
        description: "This client will use TeleCMI click-to-call. Telecallers need TeleCMI agent ID/password, and recordings/durations come from TeleCMI webhooks.",
        confirm: "Switch to TeleCMI",
      };

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
                onClick={() => {
                  if (provider?.calling_provider !== option.id) setPendingProvider(option.id);
                }}
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

      {pendingProvider && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-card bg-white p-6 shadow-xl">
            <div className="flex items-start gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-warning/10 text-warning">
                <AlertTriangle size={20} />
              </div>
              <div>
                <h3 className="text-lg font-bold text-ink">{pendingProviderCopy.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-ink-secondary">{pendingProviderCopy.description}</p>
              </div>
            </div>
            <div className="mt-6 flex gap-3">
              <button
                type="button"
                onClick={() => setPendingProvider(null)}
                disabled={!!providerSaving}
                className="flex-1 rounded-xl border border-border px-4 py-2.5 text-sm font-medium text-ink-secondary transition-colors hover:bg-surface-mid disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={async () => {
                  const next = pendingProvider;
                  await updateProvider(next);
                  setPendingProvider(null);
                }}
                disabled={!!providerSaving}
                className="flex-1 rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-primary/90 disabled:opacity-50"
              >
                {providerSaving ? <Loader2 size={16} className="mx-auto animate-spin" /> : pendingProviderCopy.confirm}
              </button>
            </div>
          </div>
        </div>
      )}

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

      {/* Knowledge Search Mode */}
      <div>
        <h3 className="text-sm font-semibold text-ink mb-3 flex items-center gap-2">
          <Sparkles size={16} className="text-ink-muted" />
          Knowledge Search Mode
        </h3>
        <div className="grid gap-4 md:grid-cols-3">
          {RETRIEVAL_MODES.map((option) => {
            const selected = config.settings.kb_retrieval_mode === option.id;
            const saving = retrievalSaving === option.id;
            return (
              <button
                key={option.id}
                type="button"
                onClick={() => updateRetrievalMode(option.id)}
                disabled={!!retrievalSaving || selected}
                className={`rounded-card border p-4 text-left shadow-sm transition-all ${
                  selected
                    ? "border-primary bg-primary-light text-ink ring-1 ring-primary/10"
                    : "border-border bg-white hover:border-primary-muted"
                } ${retrievalSaving && !saving ? "opacity-70" : ""} disabled:cursor-default`}
              >
                <div className="flex items-start gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 justify-between">
                      <p className="text-sm font-semibold text-ink">{option.label}</p>
                      {saving && <Loader2 size={14} className="animate-spin text-primary" />}
                      {selected && !saving && (
                        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[10px] font-medium bg-success/10 text-success">
                          Active
                        </span>
                      )}
                    </div>
                    <p className="mt-1 text-xs leading-relaxed text-ink-muted">{option.desc}</p>
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
