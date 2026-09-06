"use client";
import { CheckCircle2, Loader2, ArrowRight, Sparkles } from "lucide-react";
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
    <section className="overflow-hidden rounded-[28px] border border-violet-200/90 bg-white shadow-[0_0_30px_rgba(124,58,237,0.12),0_4px_20px_rgba(0,0,0,0.04)] ring-1 ring-violet-200/50">
      <div className="relative flex flex-col gap-4 border-b border-violet-100 bg-gradient-to-r from-violet-50 via-white to-violet-50/40 px-6 py-6 sm:min-h-[170px] sm:flex-row sm:items-center sm:justify-between sm:px-8 sm:pr-[200px]">
        <div className="relative z-10 max-w-xl">
          <div className="flex items-center gap-2.5 flex-wrap">
            <p className="font-label text-[10px] font-bold uppercase tracking-[0.18em] text-violet-700">Connectivity Hub</p>
            <span className="inline-flex items-center gap-1.5 rounded-full bg-gradient-to-r from-primary via-purple-600 to-indigo-600 px-3 py-1 font-label text-[10px] font-bold tracking-wide text-white shadow-[0_0_16px_rgba(124,58,237,0.55)] ring-1 ring-violet-300/50">
              <Sparkles size={11} className="text-amber-300 animate-pulse" />
              Recommended
            </span>
          </div>
          <h2 className="mt-2 font-display text-2xl font-bold tracking-tight text-ink">WhatsApp, Messenger, Instagram &amp; Ads</h2>
          <p className="mt-2 text-[14px] leading-relaxed text-ink-muted">
            Your central command for all Meta integrations. Manage WhatsApp, Facebook Messenger, linked Instagram, and ad reporting from a single, secure gateway.
          </p>
        </div>
        <div className="pointer-events-none absolute right-4 top-1/2 -translate-y-1/2 hidden sm:block">
          <ZephyrCourier variant="embedded" compact />
        </div>
      </div>

      <div className="grid gap-8 p-6 sm:p-8 lg:grid-cols-12 lg:items-start">
        <div className="lg:col-span-5 flex flex-col justify-between">
          <div>
            <ul className="mb-6 space-y-3.5 font-body text-[14px] sm:text-[15px] text-ink/80">
              {VALUE_PROPS.map(item => (
                <li key={item} className="flex items-center gap-3">
                  <div className="flex shrink-0 items-center justify-center rounded-full bg-primary-light/60 p-1">
                    <CheckCircle2 size={16} className="text-primary" />
                  </div>
                  <span>{item}</span>
                </li>
              ))}
            </ul>
            {error && <p className="mb-4 rounded-xl bg-red-50 px-4 py-3 font-body text-sm text-red-700">{error}</p>}
            <div className="flex flex-wrap items-center gap-2.5">
              <button
                type="button"
                onClick={onConnect}
                disabled={!canManage || isBusy}
                className="inline-flex items-center justify-center gap-2 rounded-xl bg-gradient-to-br from-[#2e1065] to-primary px-4 py-2.5 font-label text-xs sm:text-sm font-bold text-white shadow-[0_4px_14px_rgba(91,33,182,0.3)] transition-all hover:brightness-110 hover:shadow-[0_6px_20px_rgba(91,33,182,0.45)] disabled:cursor-not-allowed disabled:opacity-60"
              >
                {isBusy && activeMode === "standard" && <Loader2 size={14} className="animate-spin" />}
                <span>{isConnected ? "Reconnect Meta Business" : "Connect Meta Business"}</span>
                <ArrowRight size={14} />
              </button>
              <button
                type="button"
                onClick={onConnectCoexistence}
                disabled={!canManage || isBusy}
                className="inline-flex items-center justify-center gap-2 rounded-xl border border-border bg-white px-4 py-2.5 font-label text-xs sm:text-sm font-bold text-ink shadow-xs transition-all hover:bg-surface-subtle hover:border-primary/30 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {isBusy && activeMode === "coexistence" && <Loader2 size={14} className="animate-spin" />}
                <span>WhatsApp Coexistence</span>
                <ArrowRight size={14} className="text-ink-muted" />
              </button>
              {isConnected && (
                <button
                  type="button"
                  onClick={() => onDisconnect("meta")}
                  disabled={!canManage || isBusy}
                  className="inline-flex items-center rounded-xl border border-border px-3.5 py-2.5 font-label text-xs font-bold text-ink-muted transition-colors hover:border-red-200 hover:bg-red-50 hover:text-red-600 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  Disconnect
                </button>
              )}
            </div>
            <p className="mt-3 font-body text-xs text-ink-muted leading-relaxed">
              Already use the WhatsApp Business app? The second option keeps the mobile app connected.
            </p>
          </div>
        </div>

        <div className="lg:col-span-7">
          <div className="mb-3.5 flex items-center justify-between">
            <h3 className="font-label text-xs font-bold uppercase tracking-wider text-ink-muted flex items-center gap-2">
              <span className="inline-block h-2 w-2 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.8)]" />
              Active Channels
            </h3>
            <HealthRefreshButton loading={healthLoading} onClick={onRefreshHealth} />
          </div>
          <div className="flex flex-col gap-2.5">
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
                <div
                  key={channel.id}
                  className="flex items-center justify-between gap-3 rounded-2xl border border-violet-200/90 bg-white p-3.5 shadow-[0_0_15px_rgba(124,58,237,0.18),0_2px_6px_rgba(124,58,237,0.08)] ring-1 ring-violet-400/20 transition-all duration-300 hover:-translate-y-0.5 hover:border-violet-400 hover:shadow-[0_0_24px_rgba(124,58,237,0.35)] hover:ring-violet-400/40"
                >
                  <div className="flex min-w-0 items-center gap-3">
                    <div className={cn("flex h-9 w-9 shrink-0 items-center justify-center rounded-xl", channel.iconBg)}>
                      <channel.icon size={18} className={channel.iconColor} />
                    </div>
                    <div className="min-w-0">
                      <p className="font-display text-sm font-bold text-ink leading-tight">{channel.name}</p>
                      <p className="truncate font-body text-[11px] text-ink-muted mt-0.5">
                        {activity}
                      </p>
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <ChannelStatusBadge configured={configured} hasTokenAlert={Boolean(alert)} isLive={isLive} />
                    {configured && (
                      <div className="flex items-center gap-1">
                        <button
                          type="button"
                          onClick={() => onManageChannel(channel)}
                          className="rounded-lg px-2 py-1 font-label text-[11px] font-bold text-primary transition-colors hover:bg-primary-light/60"
                        >
                          Manage
                        </button>
                        <button
                          type="button"
                          onClick={() => onDisconnect(channel.id)}
                          className="rounded-lg px-1.5 py-1 font-label text-[11px] font-bold text-ink-muted transition-colors hover:bg-red-50 hover:text-red-600"
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
      </div>
    </section>
  );
}
