"use client";
import { useEffect, useState, useCallback, useMemo } from "react";
import {
  MessageSquare, Send, Eye, EyeOff, Save, AlertCircle, Loader2,
  CheckCircle2, Copy, Check, Zap, XCircle, RefreshCw, X
} from "lucide-react";
import { API_URL, getAuthHeaders } from "@/lib/api";
import { cn } from "@/lib/utils";

// ── Icons for Instagram & Facebook (Baseline SVG) ───────────────────────────
function InstagramIcon({ size = 18, className = "" }: { size?: number | string; className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      <rect width="20" height="20" x="2" y="2" rx="5" ry="5" />
      <path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z" />
      <line x1="17.5" x2="17.51" y1="6.5" y2="6.5" />
    </svg>
  );
}

function FacebookIcon({ size = 18, className = "" }: { size?: number | string; className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      <path d="M18 2h-3a5 5 0 0 0-5 5v3H7v4h3v8h4v-8h3l1-4h-4V7a1 1 0 0 1 1-1h3z" />
    </svg>
  );
}

// ── Types ───────────────────────────────────────────────────────────────────
type Setting = {
  key: string;
  display_value: string;
  is_secret: boolean;
  is_set: boolean;
  updated_at: string;
};

type SettingsMap = Record<string, string>;

type FieldDef = {
  key: string;
  label: string;
  placeholder?: string;
  secret: boolean;
  required?: boolean;
  hint?: string;
};

type ActivateResult = {
  success: boolean;
  message: string;
  detail?: string;
};

type ChannelHealth = {
  last_event: string | null;
};

type TokenAlert = {
  channel: string;
  error: string;
  created_at: string;
};

type WebhookHealth = {
  health: Record<string, ChannelHealth>;
  token_alerts: TokenAlert[];
};

type SaveState = "idle" | "dirty" | "saving" | "saved";

type ChannelConfig = {
  id: string;
  name: string;
  description: string;
  icon: React.ComponentType<{ size?: number | string; className?: string }>;
  iconBg: string;
  iconColor: string;
  themeColor: string;
  fields: FieldDef[];
  hasActivation: boolean;
};

// ── Channel Definitions ──────────────────────────────────────────────────────
const CHANNELS: ChannelConfig[] = [
  {
    id: "whatsapp",
    name: "WhatsApp Cloud API",
    description: "Deploy automated flows, notifications, and outbound campaigns using WhatsApp Business App.",
    icon: MessageSquare,
    iconBg: "bg-emerald-100",
    iconColor: "text-emerald-600",
    themeColor: "emerald",
    fields: [
      { key: "meta_phone_number_id", label: "Phone Number ID", secret: false, required: true },
      { key: "meta_waba_id", label: "WhatsApp Business Account ID (WABA ID)", secret: false, required: true, hint: "Found in Meta Business Manager → WhatsApp Accounts. Required for webhook subscription." },
      { key: "meta_access_token", label: "Permanent Access Token", secret: true, required: true },
      { key: "meta_webhook_verify_token", label: "Webhook Verify Token", secret: true, required: true, hint: "Pick any string. Paste the same value into Meta Developer App → Webhook → Verify Token (shared by WhatsApp, Instagram, Facebook)." },
      { key: "meta_app_secret", label: "Meta App Secret", secret: true, required: true, hint: "Meta Developer App → Settings → Basic → App Secret. Used to verify inbound Facebook + Instagram webhooks." },
    ],
    hasActivation: true,
  },
  {
    id: "telegram",
    name: "Telegram Bot",
    description: "Connect your Telegram bot to handle direct messages, support queries, and group notifications.",
    icon: Send,
    iconBg: "bg-sky-100",
    iconColor: "text-sky-600",
    themeColor: "sky",
    fields: [
      { key: "telegram_bot_token", label: "Telegram Bot Token", secret: true, required: true, hint: "Obtain this token from @BotFather on Telegram" },
    ],
    hasActivation: false,
  },
  {
    id: "instagram",
    name: "Instagram DM",
    description: "Automate responses, track conversations, and manage direct messages from your Instagram business account.",
    icon: InstagramIcon,
    iconBg: "bg-pink-100",
    iconColor: "text-pink-600",
    themeColor: "pink",
    fields: [
      { key: "instagram_page_id", label: "Instagram Page ID / Business Account ID", secret: false, required: true, hint: "Meta Business Manager Page ID or Instagram Business Account ID" },
      { key: "instagram_access_token", label: "Instagram Page Access Token", secret: true, required: true, hint: "Permanent page access token with instagram_manage_messages scope" },
    ],
    hasActivation: true,
  },
  {
    id: "facebook",
    name: "Facebook Messenger",
    description: "Interact with your page visitors, handle support tickets, and route incoming Facebook Messenger chats.",
    icon: FacebookIcon,
    iconBg: "bg-blue-100",
    iconColor: "text-blue-600",
    themeColor: "blue",
    fields: [
      { key: "facebook_page_id", label: "Facebook Page ID", secret: false, required: true, hint: "Your Facebook Page's numeric ID from Page settings" },
      { key: "facebook_access_token", label: "Facebook Page Access Token", secret: true, required: true, hint: "Permanent page access token with pages_messaging scope" },
    ],
    hasActivation: true,
  },
];

async function fetchSettings(): Promise<Setting[]> {
  const auth = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/v1/settings`, { headers: auth });
  if (!res.ok) throw new Error("Failed to load settings");
  return (await res.json()).settings;
}

async function saveSettings(updates: SettingsMap): Promise<void> {
  const auth = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/v1/settings`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...auth },
    body: JSON.stringify({ updates }),
  });
  if (!res.ok) throw new Error("Failed to save settings");
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 2000);
        } catch {}
      }}
      title="Copy to clipboard"
      className="flex-shrink-0 inline-flex items-center gap-1 px-2 py-1 rounded-lg text-[11px] font-label font-semibold transition-all border border-border bg-white text-ink-muted hover:text-primary hover:border-primary/40"
    >
      {copied ? <><Check size={11} className="text-emerald-600" />Copied</> : <><Copy size={11} />Copy</>}
    </button>
  );
}

function OutlinedField({
  label, value, onChange, placeholder, type = "text", rightSlot, hint,
}: {
  label: string; value: string; onChange: (v: string) => void;
  placeholder?: string; type?: "text" | "password"; rightSlot?: React.ReactNode; hint?: string;
}) {
  return (
    <div className="space-y-1">
      <div className="relative">
        <input
          type={type}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder ?? " "}
          className="peer w-full px-4 pt-5 pb-2 pr-10 rounded-xl bg-white border border-border text-sm font-body text-ink placeholder:text-ink-muted/40 focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/15 transition"
        />
        <label className="pointer-events-none absolute left-3 -top-2 px-1.5 text-[11px] font-label font-medium text-ink-muted bg-white tracking-wide">
          {label}
        </label>
        {rightSlot && (
          <div className="absolute right-2.5 top-1/2 -translate-y-1/2 flex items-center">
            {rightSlot}
          </div>
        )}
      </div>
      {hint && <p className="text-[11px] text-ink-muted font-body pl-1">{hint}</p>}
    </div>
  );
}

function SecretField({
  label, storedMask, isSet, newValue, onChange, hint,
}: {
  label: string; storedMask: string; isSet: boolean;
  newValue: string; onChange: (v: string) => void; hint?: string;
}) {
  const [show, setShow] = useState(false);
  const [editing, setEditing] = useState(false);
  const showInput = editing || newValue.length > 0 || !isSet;

  return (
    <div className="space-y-1">
      {!showInput ? (
        <button type="button" onClick={() => setEditing(true)} className="relative w-full text-left group">
          <div className="w-full px-4 pt-5 pb-2 rounded-xl bg-white border border-border font-mono text-sm text-ink-secondary cursor-text group-hover:border-primary/40 transition">
            {storedMask}
          </div>
          <span className="pointer-events-none absolute left-3 -top-2 px-1.5 text-[11px] font-label font-medium text-ink-muted bg-white tracking-wide">
            {label}
          </span>
          <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[11px] font-label font-semibold text-primary opacity-0 group-hover:opacity-100 transition">
            Edit
          </span>
        </button>
      ) : (
        <OutlinedField
          label={label}
          value={newValue}
          onChange={onChange}
          type={show ? "text" : "password"}
          placeholder={isSet ? "Enter new value to replace existing" : "Paste your value here"}
          rightSlot={
            <button type="button" onClick={() => setShow(s => !s)} className="p-1 text-ink-muted hover:text-ink-secondary" tabIndex={-1}>
              {show ? <EyeOff size={14} /> : <Eye size={14} />}
            </button>
          }
        />
      )}
      {hint && <p className="text-[11px] text-ink-muted font-body pl-1">{hint}</p>}
    </div>
  );
}

function timeAgo(iso: string | null): string {
  if (!iso) return "never";
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function WebhookConfigGuide({ channelId, tenantId }: { channelId: string; tenantId: string | null }) {
  if (channelId === "whatsapp") {
    const url = `${API_URL}/webhook/whatsapp`;
    return (
      <div className="p-5 rounded-2xl bg-surface-subtle border border-border-subtle font-body text-xs text-ink-secondary space-y-2.5">
        <p className="font-semibold text-ink text-sm">Meta Webhook Configuration Guide:</p>
        <p>1. In your Meta Developer App, go to <strong>WhatsApp → Configuration</strong>.</p>
        <p>2. Set the Callback URL to:</p>
        <div className="flex items-center gap-2">
          <div className="flex-grow p-3 rounded-xl bg-white border border-border font-mono text-xs select-all break-all text-primary font-medium">
            {url}
          </div>
          <CopyButton text={url} />
        </div>
        <p>3. Set the Verify Token to the same value as your <strong>Webhook Verify Token</strong> configured below.</p>
        <p>4. Subscribe to <strong>messages</strong> and <strong>message_status_updates</strong> fields.</p>
        <p>5. After saving credentials, click <strong>Validate &amp; Activate</strong> to verify your token and subscribe the webhook.</p>
      </div>
    );
  }

  if (channelId === "instagram") {
    const url = tenantId ? `${API_URL}/webhook/instagram/${tenantId}` : null;
    return (
      <div className="p-5 rounded-2xl bg-surface-subtle border border-border-subtle font-body text-xs text-ink-secondary space-y-2.5">
        <p className="font-semibold text-ink text-sm">Meta Webhook Configuration Guide:</p>
        <p>1. In your Meta Developer App, add the <strong>Instagram Graph API</strong> product.</p>
        <p>2. Set the Webhook Callback URL to:</p>
        <div className="flex items-center gap-2">
          <div className="flex-grow p-3 rounded-xl bg-white border border-border font-mono text-xs select-all break-all text-primary font-medium">
            {url ?? "Retrieving webhook URL…"}
          </div>
          {url && <CopyButton text={url} />}
        </div>
        <p>3. Use the verify token you set in your WhatsApp integration (meta_webhook_verify_token).</p>
        <p>4. Subscribe to <strong>messages</strong> Webhook event fields.</p>
        <p>5. After saving credentials, click <strong>Validate &amp; Activate</strong> to auto-subscribe the webhook.</p>
      </div>
    );
  }

  if (channelId === "facebook") {
    const url = tenantId ? `${API_URL}/webhook/facebook/${tenantId}` : null;
    return (
      <div className="p-5 rounded-2xl bg-surface-subtle border border-border-subtle font-body text-xs text-ink-secondary space-y-2.5">
        <p className="font-semibold text-ink text-sm">Facebook Messenger Webhook Configuration Guide:</p>
        <p>1. In your Meta Developer App, add the <strong>Messenger</strong> product and link your Page.</p>
        <p>2. Set the Webhook Callback URL to:</p>
        <div className="flex items-center gap-2">
          <div className="flex-grow p-3 rounded-xl bg-white border border-border font-mono text-xs select-all break-all text-primary font-medium">
            {url ?? "Retrieving webhook URL…"}
          </div>
          {url && <CopyButton text={url} />}
        </div>
        <p>3. Use the same verify token configured in your WhatsApp integration (meta_webhook_verify_token).</p>
        <p>4. Subscribe to <strong>messages</strong> Webhook event fields under your Page.</p>
        <p>5. After saving credentials, click <strong>Validate &amp; Activate</strong> to auto-subscribe the webhook.</p>
      </div>
    );
  }

  return null;
}

export default function ChannelsHubPage() {
  const [settings, setSettings] = useState<Setting[]>([]);
  const [drafts, setDrafts] = useState<SettingsMap>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [webhookHealth, setWebhookHealth] = useState<WebhookHealth | null>(null);
  const [healthLoading, setHealthLoading] = useState(false);
  const [tenantId, setTenantId] = useState<string | null>(null);

  // Modal control
  const [selectedChannel, setSelectedChannel] = useState<ChannelConfig | null>(null);
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [activating, setActivating] = useState(false);
  const [activateResult, setActivateResult] = useState<ActivateResult | null>(null);

  const load = useCallback(async () => {
    try {
      const s = await fetchSettings();
      setSettings(s);
      setDrafts((prev) => {
        const next: SettingsMap = { ...prev };
        s.forEach((row) => {
          // Flatten all channel fields drafts
          const isKnownField = CHANNELS.some(c => c.fields.some(f => f.key === row.key));
          if (isKnownField) {
            if (!row.is_secret) {
              const value = row.display_value === "Not set" ? "" : row.display_value;
              if (!(row.key in next) || next[row.key] === "") next[row.key] = value;
            } else {
              if (!(row.key in next)) next[row.key] = "";
            }
          }
        });
        return next;
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load settings");
    } finally {
      setLoading(false);
    }
  }, []);

  const loadHealth = useCallback(async () => {
    setHealthLoading(true);
    try {
      const auth = await getAuthHeaders();
      const res = await fetch(`${API_URL}/api/v1/settings/webhook-health`, { headers: auth });
      if (res.ok) setWebhookHealth(await res.json());
    } catch {} finally {
      setHealthLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    loadHealth();
    async function fetchTenantStatus() {
      try {
        const auth = await getAuthHeaders();
        const res = await fetch(`${API_URL}/api/v1/onboarding/status`, { headers: auth });
        if (res.ok) {
          const data = await res.json();
          if (data.tenant_id) setTenantId(data.tenant_id);
        }
      } catch {}
    }
    fetchTenantStatus();
  }, [load, loadHealth]);

  function settingFor(key: string) {
    return settings.find(s => s.key === key);
  }

  // Check if a channel's fields are completely set in DB
  const isChannelConfigured = useCallback((channel: ChannelConfig) => {
    return channel.fields.every(f => settings.find(s => s.key === f.key)?.is_set);
  }, [settings]);

  // Check if modal channel has drafts changes
  const isModalDirty = useMemo(() => {
    if (!selectedChannel) return false;
    return selectedChannel.fields.some(f => {
      const meta = settings.find(s => s.key === f.key);
      const draft = drafts[f.key] ?? "";
      if (f.secret) return draft.length > 0;
      const stored = meta?.display_value === "Not set" ? "" : (meta?.display_value ?? "");
      return draft !== stored;
    });
  }, [selectedChannel, drafts, settings]);

  async function handleSave() {
    if (!selectedChannel) return;
    setSaveState("saving");
    setError(null);
    const updates: SettingsMap = {};
    selectedChannel.fields.forEach(f => {
      const draft = drafts[f.key];
      const current = settingFor(f.key);
      if (!current) return;
      if (current.is_secret) {
        if (draft && draft.length > 0) updates[f.key] = draft;
      } else {
        const stored = current.display_value === "Not set" ? "" : current.display_value;
        if (draft !== undefined && draft !== stored) updates[f.key] = draft;
      }
    });

    try {
      if (Object.keys(updates).length > 0) await saveSettings(updates);
      setDrafts(prev => {
        const next = { ...prev };
        Object.keys(updates).forEach(k => {
          if (settingFor(k)?.is_secret) next[k] = "";
        });
        return next;
      });
      await load();
      setSaveState("saved");
      setTimeout(() => setSaveState("idle"), 2500);
      loadHealth();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
      setSaveState("idle");
    }
  }

  async function handleActivate() {
    if (!selectedChannel) return;
    setActivating(true);
    setActivateResult(null);
    try {
      const auth = await getAuthHeaders();
      const res = await fetch(`${API_URL}/api/v1/settings/activate`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...auth },
        body: JSON.stringify({ channel: selectedChannel.id }),
      });
      const data = await res.json();
      if (!res.ok) {
        setActivateResult({ success: false, message: data.detail ?? "Activation failed" });
      } else {
        let detail = "";
        if (selectedChannel.id === "whatsapp") {
          detail = [
            data.business_name,
            data.phone_number,
            data.subscribed ? "Webhook subscribed ✓" : "Add WABA ID to enable webhook subscription",
          ].filter(Boolean).join(" · ");
        } else {
          detail = [
            data.page_name,
            data.page_id ? `ID: ${data.page_id}` : null,
            data.subscribed ? "Webhook subscribed ✓" : "Webhook subscription failed — check token scopes",
          ].filter(Boolean).join(" · ");
        }
        setActivateResult({ success: true, message: "Validated & connected", detail });
        loadHealth();
      }
    } catch {
      setActivateResult({ success: false, message: "Network error — please try again" });
    } finally {
      setActivating(false);
    }
  }

  const openChannelModal = (channel: ChannelConfig) => {
    setSelectedChannel(channel);
    setSaveState("idle");
    setActivateResult(null);
  };

  const closeChannelModal = () => {
    setSelectedChannel(null);
  };

  return (
    <div className="max-w-6xl mx-auto space-y-8">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="page-title">Connect Channels</h1>
          <p className="page-subtitle">Configure credentials and view synchronization health across your messaging channels.</p>
        </div>
        <button
          onClick={loadHealth}
          disabled={healthLoading}
          title="Refresh health status"
          className="inline-flex items-center gap-2 px-4 py-2 rounded-xl font-label text-sm font-semibold border border-border text-ink-muted hover:text-ink-secondary transition-all bg-white"
        >
          <RefreshCw size={14} className={healthLoading ? "animate-spin" : ""} />
          <span>Refresh Health</span>
        </button>
      </div>

      {error && (
        <div className="flex items-center gap-2 p-3.5 rounded-2xl bg-red-50 text-red-700 border border-red-100">
          <AlertCircle size={15} />
          <span className="font-body text-sm">{error}</span>
        </div>
      )}

      {/* Channels Grid */}
      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="card rounded-3xl h-56 animate-pulse bg-border-subtle" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {CHANNELS.map((channel) => {
            const configured = isChannelConfigured(channel);
            const health = webhookHealth?.health?.[channel.id];
            const alert = webhookHealth?.token_alerts?.find(a => a.channel === channel.id);

            return (
              <button
                key={channel.id}
                onClick={() => openChannelModal(channel)}
                className="card rounded-3xl p-6 text-left flex flex-col justify-between hover:shadow-lg hover:border-primary/25 hover:ring-2 hover:ring-primary/5 transition-all duration-300 group cursor-pointer relative"
              >
                <div>
                  {/* Top Bar: Icon + Configuration Status */}
                  <div className="flex items-start justify-between mb-4">
                    <div className={cn("w-12 h-12 rounded-2xl flex items-center justify-center transition-all duration-300 group-hover:scale-105", channel.iconBg)}>
                      <channel.icon size={22} className={channel.iconColor} />
                    </div>

                    <div className="flex items-center gap-2">
                      {/* Health Status badge */}
                      {configured && (
                        <>
                          {alert ? (
                            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-label font-bold bg-red-100 text-red-700">
                              Token Invalid
                            </span>
                          ) : health?.last_event ? (
                            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-label font-bold bg-emerald-50 text-emerald-700">
                              Live
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-label font-bold bg-amber-50 text-amber-700">
                              Configured
                            </span>
                          )}
                        </>
                      )}
                      {!configured && (
                        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-label font-bold bg-[#f0ece4] text-[#78716c]">
                          Not Configured
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Title & Description */}
                  <h3 className="font-display font-bold text-ink text-base mb-1.5 group-hover:text-primary transition-colors">
                    {channel.name}
                  </h3>
                  <p className="font-body text-xs text-ink-muted leading-relaxed">
                    {channel.description}
                  </p>
                </div>

                {/* Bottom health metadata */}
                {configured && (
                  <div className="mt-6 pt-4 border-t border-border-subtle/50 flex items-center justify-between text-[11px] text-ink-muted font-body">
                    <span>
                      {health?.last_event ? (
                        <>Active event: <strong className="text-emerald-600">{timeAgo(health.last_event)}</strong></>
                      ) : (
                        "No events received yet"
                      )}
                    </span>
                    <span className="text-primary font-semibold opacity-0 group-hover:opacity-100 transition-opacity">
                      Configure Settings →
                    </span>
                  </div>
                )}
                {!configured && (
                  <div className="mt-6 pt-4 border-t border-border-subtle/50 flex justify-end text-[11px] font-body text-primary font-semibold">
                    Set up integration →
                  </div>
                )}
              </button>
            );
          })}
        </div>
      )}

      {/* Integration Configuration Modal */}
      {selectedChannel && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/45 backdrop-blur-[3px] animate-fade-in">
          <div className="bg-surface rounded-card shadow-card w-full max-w-2xl max-h-[85vh] overflow-y-auto ring-1 ring-[#c4c7c7]/20 flex flex-col">
            
            {/* Modal Header */}
            <div className="flex items-center justify-between p-6 border-b border-border-subtle">
              <div className="flex items-center gap-3">
                <div className={cn("w-10 h-10 rounded-2xl flex items-center justify-center", selectedChannel.iconBg)}>
                  <selectedChannel.icon size={20} className={selectedChannel.iconColor} />
                </div>
                <div>
                  <h2 className="font-display text-lg font-bold text-ink">{selectedChannel.name} Settings</h2>
                  <p className="font-body text-xs text-ink-muted">Set up credentials and subscription webhooks.</p>
                </div>
              </div>
              <button
                onClick={closeChannelModal}
                className="p-1.5 rounded-lg hover:bg-surface-low transition-colors text-on-surface-muted hover:text-on-surface"
              >
                <X size={18} />
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-6 space-y-6 overflow-y-auto flex-1">
              {/* Dynamic Webhook Guide */}
              <WebhookConfigGuide channelId={selectedChannel.id} tenantId={tenantId} />

              {/* Form Fields */}
              <div className="space-y-4">
                <div className="flex items-center gap-2 mb-2">
                  <h4 className="font-label font-bold text-ink text-xs uppercase tracking-wider">Credentials</h4>
                  <div className="h-px flex-1 bg-border-subtle" />
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {selectedChannel.fields.map((field) => {
                    const meta = settingFor(field.key);
                    const draft = drafts[field.key] ?? "";
                    if (field.secret) {
                      return (
                        <SecretField
                          key={field.key}
                          label={field.label}
                          storedMask={meta?.display_value ?? "Not set"}
                          isSet={!!meta?.is_set}
                          newValue={draft}
                          onChange={v => setDrafts(d => ({ ...d, [field.key]: v }))}
                          hint={field.hint}
                        />
                      );
                    }
                    return (
                      <OutlinedField
                        key={field.key}
                        label={field.label}
                        value={draft}
                        onChange={v => setDrafts(d => ({ ...d, [field.key]: v }))}
                        placeholder={field.placeholder}
                        hint={field.hint}
                      />
                    );
                  })}
                </div>
              </div>

              {/* Token Alerts */}
              {(() => {
                const tokenAlert = webhookHealth?.token_alerts?.find(a => a.channel === selectedChannel.id);
                if (!tokenAlert) return null;
                return (
                  <div className="flex items-start gap-2.5 p-3.5 rounded-2xl border bg-red-50 border-red-200 text-red-800 text-xs font-body">
                    <XCircle size={14} className="flex-shrink-0 mt-0.5 text-red-500" />
                    <div>
                      <p className="font-semibold">Token invalid — connection broken</p>
                      <p className="mt-0.5 opacity-80">{tokenAlert.error} · Detected {timeAgo(tokenAlert.created_at)}</p>
                      <p className="mt-1 opacity-70">Update your access token above, click Save Changes, then click Validate &amp; Activate.</p>
                    </div>
                  </div>
                );
              })()}

              {/* Activation Result */}
              {activateResult && (
                <div className={cn("flex items-start gap-2.5 p-3.5 rounded-2xl border text-xs font-body",
                  activateResult.success
                    ? "bg-emerald-50 border-emerald-200 text-emerald-800"
                    : "bg-red-50 border-red-200 text-red-700"
                )}>
                  {activateResult.success
                    ? <CheckCircle2 size={14} className="flex-shrink-0 mt-0.5 text-emerald-600" />
                    : <XCircle size={14} className="flex-shrink-0 mt-0.5 text-red-500" />
                  }
                  <div>
                    <p className="font-semibold">{activateResult.message}</p>
                    {activateResult.detail && <p className="mt-0.5 opacity-80">{activateResult.detail}</p>}
                  </div>
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div className="p-6 border-t border-border-subtle bg-surface-low flex items-center justify-between gap-3 flex-wrap">
              <div>
                {saveState === "saved" && (
                  <span className="inline-flex items-center gap-1.5 text-emerald-600 font-body text-sm font-medium animate-fade-in">
                    <CheckCircle2 size={14} /> Saved successfully
                  </span>
                )}
                {!isModalDirty && saveState === "idle" && isChannelConfigured(selectedChannel) && (
                  <span className="text-[11px] text-ink-muted font-body">No unsaved changes</span>
                )}
                {isModalDirty && (
                  <span className="text-[11px] text-amber-600 font-body font-medium animate-fade-in">Unsaved changes</span>
                )}
              </div>

              <div className="flex items-center gap-2">
                {selectedChannel.hasActivation && (
                  <button
                    type="button"
                    onClick={handleActivate}
                    disabled={activating || !isChannelConfigured(selectedChannel)}
                    title={!isChannelConfigured(selectedChannel) ? "Save required fields first" : "Validate token and register webhook"}
                    className={cn("inline-flex items-center gap-2 px-4 py-2 rounded-xl font-label text-sm font-semibold transition-all border",
                      isChannelConfigured(selectedChannel)
                        ? "border-violet-300 text-violet-700 bg-violet-50 hover:bg-violet-100"
                        : "border-border text-ink-muted bg-surface-subtle cursor-not-allowed opacity-50"
                    )}
                  >
                    {activating ? (
                      <><Loader2 size={14} className="animate-spin" />Validating…</>
                    ) : (
                      <><Zap size={14} />Validate &amp; Activate</>
                    )}
                  </button>
                )}

                <button
                  onClick={handleSave}
                  disabled={saveState === "saving" || saveState === "saved" || !isModalDirty}
                  className={cn("inline-flex items-center gap-2 px-4 py-2 rounded-xl font-label text-sm font-semibold transition-all",
                    saveState === "saved"
                      ? "bg-emerald-100 text-emerald-700 cursor-default"
                      : isModalDirty
                      ? "bg-primary text-white hover:bg-primary/90"
                      : "bg-surface-subtle text-ink-muted cursor-default"
                  )}
                >
                  {saveState === "saving" ? (
                    <><Loader2 size={14} className="animate-spin" />Saving…</>
                  ) : saveState === "saved" ? (
                    <><CheckCircle2 size={14} />Saved</>
                  ) : (
                    <><Save size={14} />Save Changes</>
                  )}
                </button>
              </div>
            </div>

          </div>
        </div>
      )}
    </div>
  );
}
