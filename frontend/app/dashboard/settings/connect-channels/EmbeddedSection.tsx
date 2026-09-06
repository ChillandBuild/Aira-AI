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
      <div className="flex flex-col gap-5 border-b border-primary-muted/50 bg-gradient-to-br from-primary-light/80 via-white to-primary-light/30 px-6 py-7 sm:flex-row sm:items-start sm:justify-between sm:px-8">
        <div className="max-w-xl">
          <p className="font-label text-[11px] font-extrabold uppercase tracking-[0.2em] text-primary">Embedded onboarding</p>
          <h2 className="mt-2.5 font-display text-2xl font-bold tracking-tight text-ink">WhatsApp, Messenger, Instagram &amp; Ads</h2>
          <p className="mt-2 text-sm leading-relaxed text-ink-muted">
            One secure Meta window connects WhatsApp, your Facebook Page and Messenger, linked
            Instagram, and optional read-only ad reporting.
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-3 self-start">
          <span className="flex items-center gap-1.5 rounded-full bg-gradient-to-r from-[#2e1065] to-primary px-3.5 py-1.5 font-label text-xs font-bold tracking-wide text-white shadow-lg shadow-primary/20 ring-1 ring-primary/10">
            <CheckCircle2 size={14} className="text-white/90" />
            Recommended
          </span>
          <HealthRefreshButton loading={healthLoading} onClick={onRefreshHealth} />
        </div>
      </div>

      <div className="grid gap-8 p-6 sm:p-8 lg:grid-cols-[minmax(0,1fr)_280px] lg:items-center">
        <div>
          <ul className="space-y-3.5 font-body text-[15px] text-ink/80">
            {VALUE_PROPS.map(item => (
              <li key={item} className="flex items-center gap-3">
                <div className="flex shrink-0 items-center justify-center rounded-full bg-primary-light/50 p-1">
                  <CheckCircle2 size={16} className="text-primary" />
                </div>
                {item}
              </li>
            ))}
          </ul>
          {error && <p className="mt-5 rounded-xl bg-red-50 px-4 py-3 font-body text-sm text-red-700">{error}</p>}
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
          <p className="mt-3.5 font-body text-[13px] leading-relaxed text-ink-muted/90">
            Already use the WhatsApp Business app? The second option keeps the mobile app connected.
          </p>
          {isConnected && (
            <button
              type="button"
              onClick={() => onDisconnect("meta")}
              disabled={!canManage || isBusy}
              className="mt-4 rounded-xl border border-border px-5 py-3 font-label text-sm font-bold text-ink-muted transition-colors hover:border-red-200 hover:bg-red-50 hover:text-red-600 disabled:cursor-not-allowed disabled:opacity-60"
            >
              Disconnect
            </button>
          )}
        </div>
        <div className="hidden lg:flex lg:justify-end lg:items-center"><ZephyrCourier variant="embedded" /></div>
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
