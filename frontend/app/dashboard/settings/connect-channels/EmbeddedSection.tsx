"use client";
import { CheckCircle2, Loader2, ArrowRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { ChannelStatusBadge, HealthRefreshButton, ZephyrCourier, timeAgo } from "./ui";
import { META_CHANNELS } from "./channels";
import type { ChannelConfig, Setting, WebhookHealth } from "./channels";
import type { MetaSignupMode } from "./metaSignupMode";

const VALUE_PROPS = [
  "Secure one-click connection",
  "Official WhatsApp Cloud API",
  "Business number and webhook linked automatically",
];

export default function EmbeddedSection({
  settings,
  webhookHealth,
  healthLoading,
  canManage,
  isBusy,
  error,
  isConnected,
  activeMode,
  onConnect,
  onConnectCoexistence,
  onRefreshHealth,
  onManageChannel,
  onDisconnect,
}: {
  settings: Setting[];
  webhookHealth: WebhookHealth | null;
  healthLoading: boolean;
  canManage: boolean;
  isBusy: boolean;
  error: string | null;
  isConnected: boolean;
  activeMode: MetaSignupMode | null;
  onConnect: () => void;
  onConnectCoexistence: () => void;
  onRefreshHealth: () => void;
  onManageChannel: (channel: ChannelConfig) => void;
  onDisconnect: (channelId: string) => void;
}) {
  return (
    <section className="overflow-hidden rounded-[28px] border border-primary-muted bg-white shadow-[0_16px_45px_rgba(28,25,23,0.06)]">
      <div className="flex flex-col gap-4 border-b border-primary-muted bg-gradient-to-r from-primary-light via-white to-primary-light/40 px-5 py-5 sm:flex-row sm:items-start sm:justify-between sm:px-7">
        <div>
          <p className="font-label text-[10px] font-bold uppercase tracking-[0.18em] text-primary">Embedded onboarding</p>
          <h2 className="mt-1 font-display text-xl font-bold text-ink">WhatsApp, Messenger, Instagram &amp; Ads</h2>
          <p className="mt-1 max-w-2xl font-body text-xs text-ink-muted">
            One secure Meta window connects WhatsApp, your Facebook Page and Messenger, linked
            Instagram, and optional read-only ad reporting.
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2 self-start">
          <span className="rounded-lg bg-gradient-to-br from-[#2e1065] to-primary px-2.5 py-1 font-label text-[10px] font-bold text-white shadow-sm">Recommended</span>
          <HealthRefreshButton loading={healthLoading} onClick={onRefreshHealth} />
        </div>
      </div>

      <div className="grid gap-5 p-5 sm:p-7 lg:grid-cols-[minmax(0,1fr)_220px] lg:items-center">
        <div>
          <ul className="space-y-3 font-body text-sm text-[#57534e]">
            {VALUE_PROPS.map(item => (
              <li key={item} className="flex items-center gap-2"><CheckCircle2 size={16} className="shrink-0 text-primary" />{item}</li>
            ))}
          </ul>
          {error && <p className="mt-4 rounded-xl bg-red-50 px-3 py-2 font-body text-xs text-red-700">{error}</p>}
          <div className="mt-5 flex flex-col gap-2 sm:flex-row sm:items-stretch">
            <button
              type="button"
              onClick={onConnect}
              disabled={!canManage || isBusy}
              className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-br from-[#2e1065] to-primary px-4 py-3 font-label text-sm font-bold text-white shadow-[0_8px_20px_rgba(91,33,182,0.28)] transition-all hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto sm:px-8"
            >
              {isBusy && activeMode === "standard" ? <><Loader2 size={16} className="animate-spin" />Connecting…</> : <>{isConnected ? "Reconnect Meta Business" : "Connect Meta Business"} <ArrowRight size={16} /></>}
            </button>
            <button
              type="button"
              onClick={onConnectCoexistence}
              disabled={!canManage || isBusy}
              className="inline-flex w-full items-center justify-center gap-2 rounded-xl border border-primary-muted bg-white px-4 py-3 font-label text-sm font-bold text-primary transition-all hover:border-primary/40 hover:bg-primary-light disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto sm:px-6"
            >
              {isBusy && activeMode === "coexistence" ? <><Loader2 size={16} className="animate-spin" />Opening coexistence…</> : <>Connect WhatsApp Business App <ArrowRight size={16} /></>}
            </button>
          </div>
          <p className="mt-2 font-body text-xs text-ink-muted">
            Already use the WhatsApp Business app? The second option keeps the mobile app connected.
          </p>
          {isConnected && (
            <button
              type="button"
              onClick={() => onDisconnect("meta")}
              disabled={!canManage || isBusy}
              className="mt-2 rounded-xl border border-[#e8e3db] px-4 py-3 font-label text-sm font-bold text-[#78716c] transition-colors hover:border-red-200 hover:bg-red-50 hover:text-red-600 disabled:cursor-not-allowed disabled:opacity-60"
            >
              Disconnect
            </button>
          )}
        </div>
        <div className="hidden lg:block"><ZephyrCourier variant="embedded" /></div>
      </div>

      <div className="divide-y divide-[#f0ece4] border-t border-[#f0ece4]">
        {META_CHANNELS.map(channel => {
          const configured = channel.fields.every(f => settings.find(s => s.key === f.key)?.is_set);
          const health = webhookHealth?.health?.[channel.id];
          const alert = webhookHealth?.token_alerts?.find(a => a.channel === channel.id);
          const statusSetting = settings.find(s => s.key === `${channel.id}_status`);
          const isLive = !channel.hasActivation || statusSetting?.display_value === "live" || Boolean(health?.last_event);

          // Meta Ads is polled, not webhook-driven — "no events" would read as broken.
          const adsLastSync = settings.find(s => s.key === "meta_ads_last_sync_at")?.display_value;
          const activity = channel.id === "meta_ads"
            ? (configured
                ? (adsLastSync && adsLastSync !== "Not set" ? `Synced ${timeAgo(adsLastSync)}` : "Awaiting first sync")
                : "Not connected")
            : health?.last_event
              ? `Active ${timeAgo(health.last_event)}`
              : configured ? "No events received yet" : "Not connected";

          return (
            <div key={channel.id} className="flex items-center justify-between gap-3 px-5 py-3.5 sm:px-7">
              <div className="flex min-w-0 items-center gap-3">
                <div className={cn("flex h-9 w-9 shrink-0 items-center justify-center rounded-xl", channel.iconBg)}>
                  <channel.icon size={17} className={channel.iconColor} />
                </div>
                <div className="min-w-0">
                  <p className="truncate font-display text-sm font-bold text-ink">{channel.name}</p>
                  <p className="truncate font-body text-[11px] text-ink-muted">
                    {activity}
                  </p>
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <ChannelStatusBadge configured={configured} hasTokenAlert={Boolean(alert)} isLive={isLive} />
                {configured && (
                  <>
                    <button
                      type="button"
                      onClick={() => onManageChannel(channel)}
                      className="rounded-lg px-2.5 py-1.5 font-label text-[10px] font-bold text-primary transition-colors hover:bg-[#f4f0ff]"
                    >
                      Manage
                    </button>
                    <button
                      type="button"
                      onClick={() => onDisconnect(channel.id)}
                      className="rounded-lg px-2 py-1.5 font-label text-[10px] font-bold text-[#a8a29e] transition-colors hover:bg-red-50 hover:text-red-600"
                    >
                      Disconnect
                    </button>
                  </>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
