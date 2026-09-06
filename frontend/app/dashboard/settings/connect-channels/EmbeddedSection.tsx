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
      <div className="flex flex-col gap-5 border-b border-border bg-gradient-to-b from-primary-light/30 to-white px-6 py-6 sm:flex-row sm:items-start sm:justify-between sm:px-8">
        <div className="max-w-xl">
          <p className="font-label text-[11px] font-extrabold uppercase tracking-[0.2em] text-primary">Connectivity Hub</p>
          <h2 className="mt-2 font-display text-2xl font-bold tracking-tight text-ink">WhatsApp, Messenger, Instagram &amp; Ads</h2>
          <p className="mt-2 text-[14px] leading-relaxed text-ink-muted">
            Your central command for all Meta integrations. Manage WhatsApp, Facebook Messenger, linked Instagram, and ad reporting from a single, secure gateway.
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2 self-start">
          <HealthRefreshButton loading={healthLoading} onClick={onRefreshHealth} />
        </div>
      </div>

      <div className="grid gap-8 p-6 sm:p-8 lg:grid-cols-[1fr_280px] lg:items-center">
        <div>
          <ul className="mb-6 space-y-3.5 font-body text-[15px] text-ink/80">
            {VALUE_PROPS.map(item => (
              <li key={item} className="flex items-center gap-3">
                <div className="flex shrink-0 items-center justify-center rounded-full bg-primary-light/50 p-1">
                  <CheckCircle2 size={16} className="text-primary" />
                </div>
                {item}
              </li>
            ))}
          </ul>
          {error && <p className="mt-4 rounded-xl bg-red-50 px-4 py-3 font-body text-sm text-red-700">{error}</p>}
          <div className="flex flex-col gap-3 sm:max-w-md">
            <button
              type="button"
              onClick={onConnect}
              disabled={!canManage || isBusy}
              className="flex w-full items-center justify-between rounded-xl bg-gradient-to-br from-[#2e1065] to-primary px-6 py-3.5 font-label text-sm font-bold text-white shadow-[0_8px_20px_rgba(91,33,182,0.28)] transition-all hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-60"
            >
              <span className="flex items-center gap-2">{isBusy && activeMode === "standard" && <Loader2 size={16} className="animate-spin" />}{isConnected ? "Reconnect Meta Business" : "Connect Meta Business"}</span>
              <ArrowRight size={16} />
            </button>
            <button
              type="button"
              onClick={onConnectCoexistence}
              disabled={!canManage || isBusy}
              className="flex w-full items-center justify-between rounded-xl border border-border bg-white px-6 py-3.5 font-label text-sm font-bold text-ink transition-all hover:bg-surface-subtle disabled:cursor-not-allowed disabled:opacity-60"
            >
              <span className="flex items-center gap-2">{isBusy && activeMode === "coexistence" && <Loader2 size={16} className="animate-spin" />}WhatsApp Coexistence</span>
              <ArrowRight size={16} className="text-ink-muted" />
            </button>
          </div>
          <p className="mt-3 font-body text-[13px] leading-relaxed text-ink-muted/90">
            Already use the WhatsApp Business app? The second option keeps the mobile app connected.
          </p>
          {isConnected && (
            <button
              type="button"
              onClick={() => onDisconnect("meta")}
              disabled={!canManage || isBusy}
              className="mt-6 rounded-xl border border-border px-5 py-2.5 font-label text-xs font-bold text-ink-muted transition-colors hover:border-red-200 hover:bg-red-50 hover:text-red-600 disabled:cursor-not-allowed disabled:opacity-60"
            >
              Disconnect
            </button>
          )}
        </div>
        <div className="hidden lg:flex lg:items-center lg:justify-end"><ZephyrCourier variant="embedded" /></div>
      </div>

      <div className="bg-surface-subtle/30 border-t border-border p-6 sm:p-8">
        <h3 className="mb-5 font-label text-xs font-bold uppercase tracking-wider text-ink-muted">Active Channels</h3>
        <div className="grid gap-4 sm:grid-cols-2">
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
            <div key={channel.id} className="group flex flex-col justify-between rounded-2xl border border-border bg-white p-5 shadow-sm transition-all hover:border-primary/40 hover:shadow-md">
              <div className="flex items-start justify-between gap-3">
                <div className="flex min-w-0 items-center gap-3">
                  <div className={cn("flex h-11 w-11 shrink-0 items-center justify-center rounded-xl", channel.iconBg)}>
                    <channel.icon size={20} className={channel.iconColor} />
                  </div>
                  <div className="min-w-0">
                    <p className="truncate font-display text-[15px] font-bold text-ink">{channel.name}</p>
                    <p className="mt-0.5 truncate font-body text-xs text-ink-muted">
                      {activity}
                    </p>
                  </div>
                </div>
              </div>
              <div className="mt-5 flex items-center justify-between border-t border-border/50 pt-4">
                <ChannelStatusBadge configured={configured} hasTokenAlert={Boolean(alert)} isLive={isLive} />
                {configured && (
                  <div className="flex items-center gap-1.5 opacity-0 transition-opacity group-hover:opacity-100">
                    <button
                      type="button"
                      onClick={() => onManageChannel(channel)}
                      className="rounded-lg bg-primary-light/50 px-3 py-1.5 font-label text-[11px] font-bold text-primary transition-colors hover:bg-primary-light"
                    >
                      Manage
                    </button>
                    <button
                      type="button"
                      onClick={() => onDisconnect(channel.id)}
                      className="rounded-lg bg-red-50 px-3 py-1.5 font-label text-[11px] font-bold text-red-600 transition-colors hover:bg-red-100"
                    >
                      Disconnect
                    </button>
                  </div>
                )}
              </div>
            </div>
          );
        })}
        </div>
      </div>
    </section>
  );
}
