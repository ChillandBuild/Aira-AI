"use client";
import { ZephyrCourier, timeAgo } from "./ui";
import ChannelCard from "./ChannelCard";
import { CHANNELS, resolveConnectionSource } from "./channels";
import type { ChannelConfig, Setting, WebhookHealth } from "./channels";

export default function ManualSection({
  settings,
  webhookHealth,
  healthLoading,
  onRefreshHealth,
  onOpenChannel,
}: {
  settings: Setting[];
  webhookHealth: WebhookHealth | null;
  healthLoading: boolean;
  onRefreshHealth: () => void;
  onOpenChannel: (channel: ChannelConfig) => void;
}) {
  return (
    <section className="overflow-hidden rounded-[28px] border border-violet-200 bg-white shadow-[0_16px_45px_rgba(28,25,23,0.06)]">
      <div className="flex flex-col gap-4 border-b border-violet-100 bg-gradient-to-r from-violet-50 via-white to-[#fbfaf8] px-5 py-5 sm:flex-row sm:items-center sm:justify-between sm:px-7">
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
          <div className="hidden w-[120px] sm:block"><ZephyrCourier variant="manual" compact /></div>
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
              onRefreshHealth={onRefreshHealth}
              onOpen={() => onOpenChannel(channel)}
            />
          );
        })}
      </div>
    </section>
  );
}
