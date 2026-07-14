"use client";
import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, Gauge, Image as ImageIcon, Languages, Loader2, Mic, RadioTower, Shield, Smartphone, Sparkles, XCircle } from "lucide-react";
import { toast } from "sonner";
import { API_URL, getAuthHeaders } from "@/lib/api";
import { SkeletonCard } from "../components/skeleton";
import { OperatorToggle } from "../../../components/operator-toggle";

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
type VoiceSettingKey = "ai_voice_reply_speaker" | "ai_voice_reply_pace" | "ai_voice_reply_language_mode" | "ai_voice_reply_language_code";
type MediaRecommendationSettingKey = "ai_media_recommendations_enabled" | "ai_media_max_images_per_reply";

type ReplyModelId =
  | "sarvam-30b"
  | "sarvam-105b"
  | "google/gemini-3.1-flash-lite"
  | "google/gemini-3.5-flash"
  | "openai/gpt-5.4-nano-2026-03-17"
  | "openai/gpt-5-nano-2025-08-07"
  | "groq/llama-3.3-70b-versatile";

type AiProviderKey = "sarvam" | "gemini" | "openai" | "groq";

// Each provider is integrated directly (no OpenRouter middleman) and requires its own
// API key configured per client -- there is no platform-wide fallback key for any
// provider, including Sarvam. If a client hasn't had a provider's key set up here, that
// provider's models simply won't work for them.
const AI_PROVIDERS: { key: AiProviderKey; label: string; credKey: string; settingKey: string }[] = [
  { key: "sarvam", label: "Sarvam", credKey: "ai_sarvam", settingKey: "sarvam_api_key" },
  { key: "gemini", label: "Gemini", credKey: "ai_gemini", settingKey: "gemini_api_key" },
  { key: "openai", label: "OpenAI", credKey: "ai_openai", settingKey: "openai_api_key" },
  { key: "groq", label: "Groq", credKey: "ai_groq", settingKey: "groq_api_key" },
];

const REPLY_MODELS: { id: ReplyModelId; label: string; provider: AiProviderKey; costTier: "$" | "$$" | "$$$"; desc: string }[] = [
  { id: "sarvam-30b", label: "Sarvam 30B", provider: "sarvam", costTier: "$", desc: "Default. Best fit for Tamil/Hindi/Hinglish conversations." },
  { id: "sarvam-105b", label: "Sarvam 105B", provider: "sarvam", costTier: "$$", desc: "Sarvam's flagship model. Stronger reasoning, same Indic-language focus as the 30B." },
  { id: "google/gemini-3.1-flash-lite", label: "Gemini 3.1 Flash Lite", provider: "gemini", costTier: "$", desc: "Cheap and fast, good general quality." },
  { id: "google/gemini-3.5-flash", label: "Gemini 3.5 Flash", provider: "gemini", costTier: "$$", desc: "Newer generation, stronger reasoning than Flash Lite." },
  { id: "openai/gpt-5.4-nano-2026-03-17", label: "GPT-5.4 Nano", provider: "openai", costTier: "$", desc: "Cheapest OpenAI tier, fast responses." },
  { id: "openai/gpt-5-nano-2025-08-07", label: "GPT-5 Nano", provider: "openai", costTier: "$", desc: "Previous-generation nano tier." },
  { id: "groq/llama-3.3-70b-versatile", label: "Llama 3.3 70B", provider: "groq", costTier: "$", desc: "Cheapest option overall. Fast, strong in English, weaker on Indic-language nuance." },
];

const RETRIEVAL_MODES: { id: RetrievalMode; label: string; desc: string }[] = [
  { id: "semantic", label: "Smart", desc: "Understands meaning & language (Tamil/English), even when a lead rephrases. Recommended." },
  { id: "keyword", label: "Exact words", desc: "Matches the exact words in your documents. Fastest, no AI cost — weaker on reworded questions." },
  { id: "hybrid", label: "Best of both", desc: "Blends meaning + exact words for the highest accuracy." },
];

const VOICE_LANGUAGES = [
  { value: "auto", label: "Auto detect" },
  { value: "en-IN", label: "English" },
  { value: "hi-IN", label: "Hindi" },
  { value: "ta-IN", label: "Tamil" },
  { value: "te-IN", label: "Telugu" },
  { value: "kn-IN", label: "Kannada" },
  { value: "ml-IN", label: "Malayalam" },
];

const VOICE_PACES = [
  { value: "0.85", label: "Slow" },
  { value: "1.0", label: "Normal" },
  { value: "1.2", label: "Fast" },
];

const VOICE_SPEAKERS = [
  { value: "shubh", label: "Shubh" },
  { value: "aditya", label: "Aditya" },
  { value: "ritu", label: "Ritu" },
  { value: "priya", label: "Priya" },
  { value: "neha", label: "Neha" },
  { value: "rahul", label: "Rahul" },
  { value: "pooja", label: "Pooja" },
  { value: "rohan", label: "Rohan" },
  { value: "simran", label: "Simran" },
  { value: "kavya", label: "Kavya" },
  { value: "amit", label: "Amit" },
  { value: "dev", label: "Dev" },
  { value: "ishita", label: "Ishita" },
  { value: "shreya", label: "Shreya" },
  { value: "ratan", label: "Ratan" },
  { value: "varun", label: "Varun" },
  { value: "manan", label: "Manan" },
  { value: "sumit", label: "Sumit" },
  { value: "roopa", label: "Roopa" },
  { value: "kabir", label: "Kabir" },
  { value: "aayan", label: "Aayan" },
  { value: "ashutosh", label: "Ashutosh" },
  { value: "advait", label: "Advait" },
  { value: "anand", label: "Anand" },
  { value: "tanya", label: "Tanya" },
  { value: "tarun", label: "Tarun" },
  { value: "sunny", label: "Sunny" },
  { value: "mani", label: "Mani" },
  { value: "gokul", label: "Gokul" },
  { value: "vijay", label: "Vijay" },
  { value: "shruti", label: "Shruti" },
  { value: "suhani", label: "Suhani" },
  { value: "mohit", label: "Mohit" },
  { value: "kavitha", label: "Kavitha" },
  { value: "rehan", label: "Rehan" },
  { value: "soham", label: "Soham" },
  { value: "rupali", label: "Rupali" },
];

interface ConfigData {
  enabled_features: string[];
  credentials_status: Record<string, "configured" | "incomplete" | "not_configured">;
  settings: {
    ai_auto_reply_enabled: boolean;
    ai_voice_reply_enabled: boolean;
    ai_voice_reply_speaker?: string | null;
    ai_voice_reply_pace?: number | string | null;
    ai_voice_reply_language_mode?: "auto" | "fixed" | string | null;
    ai_voice_reply_language_code?: string | null;
    ai_media_recommendations_enabled?: boolean;
    ai_media_max_images_per_reply?: number | string | null;
    reengagement_enabled: boolean;
    kb_retrieval_mode: RetrievalMode;
    ai_reply_model: ReplyModelId;
  };
  usage_counts?: {
    stt?: number | null;
    tts?: number | null;
    stt_count?: number | null;
    tts_count?: number | null;
    stt_requests?: number | null;
    tts_requests?: number | null;
  };
  stt_usage_count?: number | null;
  tts_usage_count?: number | null;
  usage?: { counters?: { metric: string; used: number }[] } | { metric: string; used: number }[];
  voice_usage?: {
    speech_to_text?: number | null;
    text_to_speech?: number | null;
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
  telegram: "Telegram",
  instagram: "Instagram",
  facebook: "Facebook",
};

// Legacy/superseded credential_status keys, kept in the API response for backward
// compatibility but no longer shown in the generic Credential Status grid -- per-provider
// AI keys now render inside the AI Integrations section instead.
const CRED_KEYS_HANDLED_ELSEWHERE = new Set(["ai", "ai_sarvam", "ai_gemini", "ai_openai", "ai_groq"]);

function usageMetricCount(usage: ConfigData["usage"], metricNames: string[]) {
  const counters = Array.isArray(usage) ? usage : usage?.counters;
  return counters?.find((item) => metricNames.includes(item.metric))?.used;
}

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
  const [voiceReplySaving, setVoiceReplySaving] = useState(false);
  const [voiceSettingSaving, setVoiceSettingSaving] = useState<VoiceSettingKey | null>(null);
  const [mediaRecommendationSaving, setMediaRecommendationSaving] = useState<MediaRecommendationSettingKey | null>(null);
  const [apiKeyDrafts, setApiKeyDrafts] = useState<Record<AiProviderKey, string>>({ sarvam: "", gemini: "", openai: "", groq: "" });
  const [apiKeySaving, setApiKeySaving] = useState<AiProviderKey | null>(null);
  const [replyModelSaving, setReplyModelSaving] = useState<ReplyModelId | null>(null);

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

  async function updateReplyModel(model: ReplyModelId) {
    if (!config || config.settings.ai_reply_model === model) return;
    setReplyModelSaving(model);
    setError(null);
    try {
      await apiFetch<{ status: string }>(
        `/api/v1/operator/clients/${tenantId}/config`,
        {
          method: "PATCH",
          body: JSON.stringify({
            settings: { ai_reply_model: model }
          })
        }
      );
      setConfig({
        ...config,
        settings: {
          ...config.settings,
          ai_reply_model: model
        }
      });
      toast.success(`Conversational reply model set to "${REPLY_MODELS.find(m => m.id === model)?.label}".`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update reply model");
      toast.error("Failed to update reply model. Please try again.");
    } finally {
      setReplyModelSaving(null);
    }
  }

  async function updateVoiceReplies(enabled: boolean) {
    if (!config || config.settings.ai_voice_reply_enabled === enabled) return;
    setVoiceReplySaving(true);
    setError(null);
    try {
      await apiFetch<{ status: string }>(
        `/api/v1/operator/clients/${tenantId}/config`,
        {
          method: "PATCH",
          body: JSON.stringify({
            settings: { ai_voice_reply_enabled: enabled }
          })
        }
      );
      setConfig({
        ...config,
        settings: {
          ...config.settings,
          ai_voice_reply_enabled: enabled
        }
      });
      toast.success(enabled ? "AI voice replies enabled for this client." : "AI voice replies disabled for this client.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update AI voice replies");
      toast.error("Failed to update AI voice replies.");
    } finally {
      setVoiceReplySaving(false);
    }
  }

  async function updateVoiceSetting(key: VoiceSettingKey, value: string) {
    if (!config || (config.settings[key] ?? "") === value) return;
    setVoiceSettingSaving(key);
    setError(null);
    try {
      await apiFetch<{ status: string }>(
        `/api/v1/operator/clients/${tenantId}/config`,
        {
          method: "PATCH",
          body: JSON.stringify({
            settings: { [key]: value }
          })
        }
      );
      setConfig({
        ...config,
        settings: {
          ...config.settings,
          [key]: value
        }
      });
      toast.success("AI voice reply setting updated.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update AI voice reply setting");
      toast.error("Failed to update AI voice reply setting.");
    } finally {
      setVoiceSettingSaving(null);
    }
  }

  async function updateVoiceLanguage(value: string) {
    if (!config) return;
    const nextSettings = value === "auto"
      ? { ai_voice_reply_language_mode: "auto" }
      : { ai_voice_reply_language_mode: "fixed", ai_voice_reply_language_code: value };
    setVoiceSettingSaving("ai_voice_reply_language_code");
    setError(null);
    try {
      await apiFetch<{ status: string }>(
        `/api/v1/operator/clients/${tenantId}/config`,
        {
          method: "PATCH",
          body: JSON.stringify({ settings: nextSettings })
        }
      );
      setConfig({
        ...config,
        settings: {
          ...config.settings,
          ...nextSettings,
        }
      });
      toast.success("AI voice reply language updated.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update AI voice reply language");
      toast.error("Failed to update AI voice reply language.");
    } finally {
      setVoiceSettingSaving(null);
    }
  }

  async function updateMediaRecommendationSetting(key: MediaRecommendationSettingKey, value: string | boolean) {
    if (!config || (config.settings[key] ?? "") === value) return;
    setMediaRecommendationSaving(key);
    setError(null);
    try {
      await apiFetch<{ status: string }>(
        `/api/v1/operator/clients/${tenantId}/config`,
        {
          method: "PATCH",
          body: JSON.stringify({
            settings: { [key]: value }
          })
        }
      );
      setConfig({
        ...config,
        settings: {
          ...config.settings,
          [key]: value
        }
      });
      toast.success("AI media recommendation setting updated.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update AI media recommendation setting");
      toast.error("Failed to update AI media recommendation setting.");
    } finally {
      setMediaRecommendationSaving(null);
    }
  }

  async function updateProviderApiKey(provider: AiProviderKey) {
    const meta = AI_PROVIDERS.find((p) => p.key === provider)!;
    const value = apiKeyDrafts[provider].trim();
    if (!config || !value) return;
    setApiKeySaving(provider);
    setError(null);
    try {
      await apiFetch<{ status: string }>(
        `/api/v1/operator/clients/${tenantId}/config`,
        {
          method: "PATCH",
          body: JSON.stringify({ settings: { [meta.settingKey]: value } })
        }
      );
      setApiKeyDrafts((prev) => ({ ...prev, [provider]: "" }));
      setConfig({
        ...config,
        credentials_status: {
          ...config.credentials_status,
          [meta.credKey]: "configured",
        }
      });
      toast.success(`${meta.label} API key saved.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : `Failed to update ${meta.label} API key`);
      toast.error(`Failed to update ${meta.label} API key.`);
    } finally {
      setApiKeySaving(null);
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

  const sttUsageCount = config.voice_usage?.speech_to_text
    ?? config.usage_counts?.stt
    ?? config.usage_counts?.stt_count
    ?? config.usage_counts?.stt_requests
    ?? config.stt_usage_count
    ?? usageMetricCount(config.usage, ["ai_speech_to_text", "stt", "speech_to_text", "ai_voice_stt"]);
  const ttsUsageCount = config.voice_usage?.text_to_speech
    ?? config.usage_counts?.tts
    ?? config.usage_counts?.tts_count
    ?? config.usage_counts?.tts_requests
    ?? config.tts_usage_count
    ?? usageMetricCount(config.usage, ["ai_text_to_speech", "tts", "text_to_speech", "ai_voice_tts"]);
  const hasVoiceUsage = typeof sttUsageCount === "number" || typeof ttsUsageCount === "number";
  const voiceSettings = {
    speaker: config.settings.ai_voice_reply_speaker ?? "shubh",
    pace: String(config.settings.ai_voice_reply_pace ?? "1.0"),
    language: config.settings.ai_voice_reply_language_mode === "fixed"
      ? (config.settings.ai_voice_reply_language_code ?? "en-IN")
      : "auto",
  };
  const mediaRecommendationsEnabled = config.settings.ai_media_recommendations_enabled ?? false;
  const mediaMaxImages = Number(config.settings.ai_media_max_images_per_reply ?? 3);
  const mediaUsageCount = usageMetricCount(config.usage, ["ai_media_recommendation", "ai_media_recommendations", "catalog_image_sent"]) ?? 0;

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
          {Object.entries(config.credentials_status)
            .filter(([provider]) => !CRED_KEYS_HANDLED_ELSEWHERE.has(provider))
            .map(([provider, status]) => (
              <div key={provider} className="bg-white rounded-card border border-border p-4 shadow-sm">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-medium text-ink">{CRED_LABELS[provider] || provider}</p>
                  {statusBadge(status)}
                </div>
              </div>
          ))}
        </div>
      </div>

      {/* AI Voice Replies */}
      <div>
        <h3 className="text-sm font-semibold text-ink mb-3 flex items-center gap-2">
          <Mic size={16} className="text-ink-muted" />
          AI Voice Replies
        </h3>
        <div className="rounded-card border border-border bg-white p-4 shadow-sm">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <p className="text-sm font-semibold text-ink">Reply with WhatsApp audio</p>
              <p className="mt-1 text-xs leading-relaxed text-ink-muted">
                When a customer sends a WhatsApp voice note, Aira transcribes it and replies back as a Bulbul voice note for this client.
              </p>
            </div>
            <OperatorToggle
              checked={config.settings.ai_voice_reply_enabled}
              onChange={updateVoiceReplies}
              loading={voiceReplySaving}
              disabled={!config.settings.ai_auto_reply_enabled}
              aria-label="Toggle AI voice replies"
            />
          </div>
          {!config.settings.ai_auto_reply_enabled && (
            <p className="mt-3 text-xs text-warning">Enable AI Auto-Reply before turning on voice replies.</p>
          )}
          <div className="mt-4 grid gap-3 border-t border-border-subtle pt-4 md:grid-cols-3">
            <label className="block">
              <span className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-ink-muted">
                <Mic size={13} /> Speaker
              </span>
              <select
                value={voiceSettings.speaker}
                onChange={(e) => updateVoiceSetting("ai_voice_reply_speaker", e.target.value)}
                disabled={voiceSettingSaving === "ai_voice_reply_speaker"}
                className="w-full rounded-xl border border-border bg-white px-3 py-2 text-sm text-ink outline-none transition-colors focus:border-primary disabled:opacity-60"
              >
                {VOICE_SPEAKERS.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-ink-muted">
                <Gauge size={13} /> Pace
              </span>
              <select
                value={voiceSettings.pace}
                onChange={(e) => updateVoiceSetting("ai_voice_reply_pace", e.target.value)}
                disabled={voiceSettingSaving === "ai_voice_reply_pace"}
                className="w-full rounded-xl border border-border bg-white px-3 py-2 text-sm text-ink outline-none transition-colors focus:border-primary disabled:opacity-60"
              >
                {VOICE_PACES.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-ink-muted">
                <Languages size={13} /> Language
              </span>
              <select
                value={voiceSettings.language}
                onChange={(e) => updateVoiceLanguage(e.target.value)}
                disabled={voiceSettingSaving === "ai_voice_reply_language_code"}
                className="w-full rounded-xl border border-border bg-white px-3 py-2 text-sm text-ink outline-none transition-colors focus:border-primary disabled:opacity-60"
              >
                {VOICE_LANGUAGES.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>
          </div>
          {hasVoiceUsage && (
            <div className="mt-4 grid gap-3 md:grid-cols-2">
              <div className="rounded-xl bg-surface-mid px-3 py-2">
                <p className="text-[10px] font-semibold uppercase tracking-wider text-ink-muted">STT usage</p>
                <p className="mt-1 font-mono text-sm font-semibold text-ink">
                  {(sttUsageCount ?? 0).toLocaleString("en-IN")}
                </p>
              </div>
              <div className="rounded-xl bg-surface-mid px-3 py-2">
                <p className="text-[10px] font-semibold uppercase tracking-wider text-ink-muted">TTS usage</p>
                <p className="mt-1 font-mono text-sm font-semibold text-ink">
                  {(ttsUsageCount ?? 0).toLocaleString("en-IN")}
                </p>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* AI Media Recommendations */}
      <div>
        <h3 className="text-sm font-semibold text-ink mb-3 flex items-center gap-2">
          <ImageIcon size={16} className="text-ink-muted" />
          AI Media Recommendations
        </h3>
        <div className="rounded-card border border-border bg-white p-4 shadow-sm">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <p className="text-sm font-semibold text-ink">Recommend catalog images</p>
              <p className="mt-1 text-xs leading-relaxed text-ink-muted">
                Controls whether this client&apos;s AI can recommend catalog items and send item images inside WhatsApp replies.
              </p>
            </div>
            <OperatorToggle
              checked={mediaRecommendationsEnabled}
              onChange={(checked) => updateMediaRecommendationSetting("ai_media_recommendations_enabled", checked)}
              loading={mediaRecommendationSaving === "ai_media_recommendations_enabled"}
              aria-label="Toggle AI media recommendations"
            />
          </div>
          <div className="mt-4 grid gap-3 border-t border-border-subtle pt-4 md:grid-cols-2">
            <label className="block">
              <span className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-ink-muted">
                <ImageIcon size={13} /> Max images per reply
              </span>
              <select
                value={Number.isFinite(mediaMaxImages) ? String(mediaMaxImages) : "3"}
                onChange={(e) => updateMediaRecommendationSetting("ai_media_max_images_per_reply", e.target.value)}
                disabled={mediaRecommendationSaving === "ai_media_max_images_per_reply"}
                className="w-full rounded-xl border border-border bg-white px-3 py-2 text-sm text-ink outline-none transition-colors focus:border-primary disabled:opacity-60"
              >
                {[1, 2, 3, 4, 5].map((count) => (
                  <option key={count} value={count}>{count}</option>
                ))}
              </select>
            </label>
            <div className="rounded-xl bg-surface-mid px-3 py-2">
              <p className="text-[10px] font-semibold uppercase tracking-wider text-ink-muted">Usage count</p>
              <p className="mt-1 font-mono text-sm font-semibold text-ink">
                {mediaUsageCount.toLocaleString("en-IN")}
              </p>
            </div>
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

      {/* AI Integrations */}
      <div>
        <h3 className="text-sm font-semibold text-ink mb-3 flex items-center gap-2">
          <Sparkles size={16} className="text-ink-muted" />
          AI Integrations
        </h3>
        <p className="mb-4 text-xs leading-relaxed text-ink-muted">
          Each provider is integrated directly and needs its own API key for this client — there is no shared platform key. A provider's models won't work for this client until its key is added below. The highlighted model is what currently generates auto-replies, reengagement messages, and product-recommendation replies.
        </p>
        <div className="flex flex-col gap-5">
          {AI_PROVIDERS.map((providerMeta) => {
            const status = config.credentials_status[providerMeta.credKey] || "not_configured";
            const draft = apiKeyDrafts[providerMeta.key];
            const savingKey = apiKeySaving === providerMeta.key;
            const models = REPLY_MODELS.filter((m) => m.provider === providerMeta.key);
            return (
              <div key={providerMeta.key} className="rounded-card border border-border bg-white p-4 shadow-sm">
                <div className="flex items-center justify-between mb-3">
                  <p className="text-sm font-semibold text-ink">{providerMeta.label}</p>
                  {statusBadge(status)}
                </div>
                <div className="flex flex-col gap-3 md:flex-row md:items-end mb-4">
                  <label className="block min-w-0 flex-1">
                    <span className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-ink-muted">
                      <Sparkles size={13} /> {providerMeta.label} API Key
                    </span>
                    <input
                      type="password"
                      value={draft}
                      onChange={(e) => setApiKeyDrafts((prev) => ({ ...prev, [providerMeta.key]: e.target.value }))}
                      placeholder={status === "configured" ? "Configured — enter a new key to replace" : `Paste this client's ${providerMeta.label} API key`}
                      disabled={savingKey}
                      className="w-full rounded-xl border border-border bg-white px-3 py-2 text-sm text-ink outline-none transition-colors placeholder:text-ink-muted focus:border-primary disabled:opacity-60"
                    />
                  </label>
                  <button
                    type="button"
                    onClick={() => updateProviderApiKey(providerMeta.key)}
                    disabled={savingKey || !draft.trim()}
                    className="inline-flex h-10 items-center justify-center rounded-xl bg-primary px-4 text-sm font-semibold text-white transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:bg-surface-mid disabled:text-ink-muted"
                  >
                    {savingKey ? <Loader2 size={16} className="animate-spin" /> : "Save Key"}
                  </button>
                </div>
                <div className="grid gap-3 md:grid-cols-2">
                  {models.map((option) => {
                    const selected = config.settings.ai_reply_model === option.id;
                    const saving = replyModelSaving === option.id;
                    return (
                      <button
                        key={option.id}
                        type="button"
                        onClick={() => updateReplyModel(option.id)}
                        disabled={!!replyModelSaving || selected}
                        className={`rounded-card border p-3 text-left shadow-sm transition-all ${
                          selected
                            ? "border-primary bg-primary-light text-ink ring-1 ring-primary/10"
                            : "border-border bg-white hover:border-primary-muted"
                        } ${replyModelSaving && !saving ? "opacity-70" : ""} disabled:cursor-default`}
                      >
                        <div className="flex items-center gap-2 justify-between">
                          <p className="text-sm font-semibold text-ink">{option.label}</p>
                          {saving && <Loader2 size={14} className="animate-spin text-primary" />}
                          {selected && !saving && (
                            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[10px] font-medium bg-success/10 text-success">
                              Active
                            </span>
                          )}
                        </div>
                        <p className="mt-0.5 text-[11px] font-medium text-ink-muted">{option.costTier}</p>
                        <p className="mt-1 text-xs leading-relaxed text-ink-muted">{option.desc}</p>
                      </button>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
