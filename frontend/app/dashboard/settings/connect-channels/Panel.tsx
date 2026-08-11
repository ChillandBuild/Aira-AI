"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertCircle } from "lucide-react";
import { API_URL, getAuthHeaders } from "@/lib/api";
import { fetchSettings, saveSettings } from "./api";
import { CHANNELS, META_CHANNELS, resolveConnectionSource } from "./channels";
import type { ActivateResult, ChannelConfig, SaveState, Setting, SettingsMap, WebhookHealth } from "./channels";
import { useMetaSignup } from "./useMetaSignup";
import EmbeddedSection from "./EmbeddedSection";
import ManualSection from "./ManualSection";
import ChannelConfigModal from "./ChannelConfigModal";
import MetaAssetPickerModal from "./MetaAssetPickerModal";

export default function ConnectChannelsPanel({ canManage = true }: { canManage?: boolean }) {
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

  const meta = useMetaSignup({
    canManage,
    onConnected: async () => { await load(); loadHealth(); },
  });

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
      const draft = drafts[f.key];
      if (draft === undefined) return false;
      if (f.secret) return draft.length > 0;
      const stored = meta?.display_value === "Not set" ? "" : (meta?.display_value ?? "");
      return draft !== stored;
    });
  }, [selectedChannel, drafts, settings]);

  async function handleSave() {
    if (!canManage) return;
    if (!selectedChannel) return;
    setSaveState("saving");
    setError(null);
    const updates: SettingsMap = {};
    selectedChannel.fields.forEach(f => {
      const draft = drafts[f.key];
      if (draft === undefined) return;
      // A never-saved key has no settings row yet; fall back to the field def
      // so first-time saves (e.g. instagram_app_secret) aren't dropped.
      const current = settingFor(f.key);
      if (f.secret) {
        if (draft.length > 0) updates[f.key] = draft;
      } else {
        const stored = current?.display_value === "Not set" ? "" : (current?.display_value ?? "");
        if (draft !== stored) updates[f.key] = draft;
      }
    });

    try {
      if (Object.keys(updates).length > 0) await saveSettings(updates);
      setDrafts(prev => {
        const next = { ...prev };
        if (selectedChannel) {
          selectedChannel.fields.forEach(f => delete next[f.key]);
        }
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
    if (!canManage) return;
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
        } else if (selectedChannel.id === "meta_ads") {
          detail = [
            data.account_name,
            data.account_id,
            data.currency,
            data.account_status === 1 ? "Account active" : `Account status: ${data.account_status ?? "unknown"}`,
          ].filter(Boolean).join(" · ");
        } else {
          detail = [
            data.page_name,
            data.page_id ? `ID: ${data.page_id}` : null,
            data.subscribed ? "Webhook subscribed ✓" : "Webhook subscription failed — check token scopes",
          ].filter(Boolean).join(" · ");
        }
        setActivateResult({ success: true, message: "Validated & connected", detail });
        await load();
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

  const metaConnected = META_CHANNELS.some(c => isChannelConfigured(c));

  return (
    <div className="mx-auto w-full max-w-[1440px] space-y-8">
      {error && (
        <div className="flex items-center gap-2 rounded-2xl border border-red-100 bg-red-50 p-3.5 text-red-700">
          <AlertCircle size={15} />
          <span className="font-body text-sm">{error}</span>
        </div>
      )}

      {loading ? (
        <div className="space-y-6">
          <div className="h-[420px] animate-pulse rounded-[28px] bg-border-subtle" />
          <div className="h-[380px] animate-pulse rounded-[28px] bg-border-subtle" />
        </div>
      ) : (
        <div className="space-y-6">
          <EmbeddedSection
            settings={settings}
            webhookHealth={webhookHealth}
            healthLoading={healthLoading}
            canManage={canManage}
            isBusy={meta.isBusy}
            error={meta.error}
            isConnected={metaConnected}
            onConnect={meta.start}
            onRefreshHealth={loadHealth}
            onManageChannel={openChannelModal}
          />
          <ManualSection
            settings={settings}
            webhookHealth={webhookHealth}
            healthLoading={healthLoading}
            onRefreshHealth={loadHealth}
            onOpenChannel={openChannelModal}
          />
        </div>
      )}

      {meta.assets && (
        <MetaAssetPickerModal
          assets={meta.assets}
          selectedPageId={meta.selectedPageId}
          selectedAdAccountId={meta.selectedAdAccountId}
          onSelectPage={meta.setSelectedPageId}
          onSelectAdAccount={meta.setSelectedAdAccountId}
          onConfirm={meta.complete}
          onDismiss={meta.dismissAssets}
          isBusy={meta.isBusy}
          error={meta.error}
          canManage={canManage}
        />
      )}

      {selectedChannel && (
        <ChannelConfigModal
          channel={selectedChannel}
          settings={settings}
          drafts={drafts}
          tenantId={tenantId}
          canManage={canManage}
          configured={isChannelConfigured(selectedChannel)}
          isDirty={isModalDirty}
          saveState={saveState}
          activating={activating}
          activateResult={activateResult}
          webhookHealth={webhookHealth}
          connectionSource={resolveConnectionSource(selectedChannel.id, settings)}
          onDraftChange={(key, value) => setDrafts(prev => ({ ...prev, [key]: value }))}
          onSave={handleSave}
          onActivate={handleActivate}
          onClose={closeChannelModal}
        />
      )}
    </div>
  );
}
