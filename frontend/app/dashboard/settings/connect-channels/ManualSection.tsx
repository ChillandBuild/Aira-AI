"use client";
import { ZephyrCourier, timeAgo } from "./ui";
import ChannelCard from "./ChannelCard";
import { CHANNELS, EMBEDDED_SIGNUP_TARGETS, resolveConnectionSource } from "./channels";
import type { ChannelConfig, EmbeddedSignupTarget, Setting, WebhookHealth } from "./channels";

export default function ManualSection({
  settings,
  webhookHealth,
  healthLoading,
  canManage,
  busyTarget,
  onRefreshHealth,
  onOpenChannel,
  onEmbeddedConnect,
  onDisconnectChannel,
}: {
  settings: Setting[];
  webhookHealth: WebhookHealth | null;
  healthLoading: boolean;
  canManage: boolean;
  busyTarget: EmbeddedSignupTarget | null;
  onRefreshHealth: () => void;
  onOpenChannel: (channel: ChannelConfig) => void;
  onEmbeddedConnect: (target: EmbeddedSignupTarget) => void;
  onDisconnectChannel: (channelId: string) => void;
}) {
  return (
    <section className="overflow-hidden rounded-[28px] border border-violet-200 bg-white shadow-[0_16px_45px_rgba(28,25,23,0.06)]">
      <div className="relative flex flex-col gap-4 border-b border-violet-100 bg-gradient-to-r from-violet-50 via-white to-violet-50/40 px-5 py-5 sm:min-h-[200px] sm:flex-row sm:items-center sm:justify-between sm:px-7 sm:pr-[250px]">
        <div>
          <p className="font-label text-[10px] font-bold uppercase tracking-[0.18em] text-violet-700">Manual API connection</p>
          <h2 className="mt-1 font-display text-xl font-bold text-ink">Bring your own tokens</h2>
          <p className="mt-1 max-w-2xl font-body text-xs text-ink-muted">
            Use your own Business Account ID, permanent access tokens and webhook controls.
            Telegram and Razorpay are configured here only.
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-3 self-start sm:self-auto">
          <span className="rounded-lg bg-violet-600 px-2.5 py-1 font-label text-[10px] font-bold text-white shadow-sm">Advanced</span>
        </div>
        {/* Absolute so full-size art never stretches the band into an empty strip. */}
        <div className="pointer-events-none absolute bottom-1 right-6 hidden w-[200px] sm:block">
          <ZephyrCourier variant="manual" />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-5 p-5 sm:p-7 md:grid-cols-2 lg:grid-cols-3">
        {CHANNELS.map(channel => {
          const configured = channel.fields.every(f => settings.find(s => s.key === f.key)?.is_set);
          const health = webhookHealth?.health?.[channel.id];
          const alert = webhookHealth?.token_alerts?.find(a => a.channel === channel.id);
          const source = resolveConnectionSource(channel.id, settings);
          const statusSetting = settings.find(s => s.key === `${channel.id}_status`);
          const isLive = !channel.hasActivation || statusSetting?.display_value === "live" || Boolean(health?.last_event);
          const adsAccountName = settings.find(s => s.key === "meta_ads_account_name")?.display_value;
          const adsLastSync = settings.find(s => s.key === "meta_ads_last_sync_at")?.display_value;

          const metadata =
            channel.id === "meta_ads"
              ? [
                  adsAccountName && adsAccountName !== "Not set" ? adsAccountName : "Ads account connected",
                  adsLastSync && adsLastSync !== "Not set" ? `Synced ${timeAgo(adsLastSync)}` : null,
                ].filter(Boolean).join(" · ")
              : health?.last_event
                ? `Active event: ${timeAgo(health.last_event)}`
                : "No events received yet";

          const embeddedTarget = EMBEDDED_SIGNUP_TARGETS[channel.id];

          return (
            <ChannelCard
              key={channel.id}
              channel={channel}
              configured={configured}
              isLive={isLive}
              hasTokenAlert={Boolean(alert)}
              source={source}
              metadata={metadata}
              healthLoading={healthLoading}
              canManage={canManage}
              embeddedBusy={Boolean(embeddedTarget) && busyTarget === embeddedTarget}
              onRefreshHealth={onRefreshHealth}
              onOpen={() => onOpenChannel(channel)}
              onEmbeddedConnect={embeddedTarget ? () => onEmbeddedConnect(embeddedTarget) : undefined}
              onDisconnect={() => onDisconnectChannel(channel.id)}
            />
          );
        })}
      </div>
    </section>
  );
}
