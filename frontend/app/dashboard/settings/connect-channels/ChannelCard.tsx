"use client";
import { Settings2, Loader2, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";
import { ChannelStatusBadge, HealthRefreshButton } from "./ui";
import type { ChannelConfig, ConnectionSource } from "./channels";

export default function ChannelCard({
  channel,
  configured,
  isLive,
  hasTokenAlert,
  source,
  metadata,
  healthLoading,
  canManage = true,
  embeddedBusy = false,
  onRefreshHealth,
  onOpen,
  onEmbeddedConnect,
  onDisconnect,
}: {
  channel: ChannelConfig;
  configured: boolean;
  isLive: boolean;
  hasTokenAlert: boolean;
  source: ConnectionSource;
  metadata: string;
  healthLoading: boolean;
  canManage?: boolean;
  embeddedBusy?: boolean;
  onRefreshHealth: () => void;
  onOpen: () => void;
  // Only the Meta-backed channels pass this; Telegram and Razorpay have no
  // Embedded Signup, so their cards keep the manual button alone.
  onEmbeddedConnect?: () => void;
  onDisconnect: () => void;
}) {
  const viaMeta = source === "embedded" && configured;

  return (
    <article
      className={cn(
        "flex min-h-[270px] flex-col justify-between rounded-3xl border bg-white p-5 shadow-sm transition-all duration-300",
        viaMeta
          ? "border-[#ece7fb] bg-[#fdfcff]"
          : "border-[#e8e3db] hover:-translate-y-0.5 hover:border-primary/25 hover:shadow-lg"
      )}
    >
      <div>
        <div className="mb-4 flex items-start justify-between">
          <div className={cn("flex h-12 w-12 items-center justify-center rounded-2xl transition-all duration-300", channel.iconBg)}>
            <channel.icon size={22} className={channel.iconColor} />
          </div>
          {viaMeta ? (
            <span className="inline-flex items-center gap-1 rounded-full bg-[#f4f0ff] px-2.5 py-1 font-label text-[10px] font-bold text-primary">
              Connected via Meta
            </span>
          ) : (
            <ChannelStatusBadge configured={configured} hasTokenAlert={hasTokenAlert} isLive={isLive} />
          )}
        </div>

        <h3 className="mb-1.5 font-display text-base font-bold text-ink">{channel.name}</h3>
        <p className="font-body text-xs leading-relaxed text-ink-muted">{channel.description}</p>
      </div>

      <div className="mt-6 flex w-full items-center justify-between border-t border-border-subtle/50 pt-4 font-body text-[11px] text-ink-muted">
        <span>{configured ? metadata : "Not configured yet"}</span>
      </div>

      <div className="mt-3 flex items-center justify-between gap-2">
        {channel.id === "meta_ads" ? (
          <span className="font-body text-[10px] font-medium text-indigo-600">Click-to-WhatsApp only</span>
        ) : (
          <HealthRefreshButton loading={healthLoading} onClick={onRefreshHealth} />
        )}
        <div className="flex items-center gap-1.5">
          {configured && (
            <button
              type="button"
              onClick={onDisconnect}
              className="rounded-lg px-2 py-1.5 font-label text-[10px] font-bold text-[#a8a29e] transition-colors hover:bg-red-50 hover:text-red-600"
            >
              Disconnect
            </button>
          )}
          {!configured && onEmbeddedConnect && (
            <button
              type="button"
              onClick={onEmbeddedConnect}
              disabled={!canManage || embeddedBusy}
              className="inline-flex items-center gap-1.5 rounded-lg bg-gradient-to-br from-[#2e1065] to-primary px-2.5 py-1.5 font-label text-[10px] font-bold text-white shadow-[0_4px_12px_rgba(91,33,182,0.22)] transition-all hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {embeddedBusy
                ? <><Loader2 size={12} className="animate-spin" /> Opening…</>
                : <><Sparkles size={12} /> Connect via Meta</>}
            </button>
          )}
          <button
            type="button"
            onClick={onOpen}
            className="inline-flex items-center gap-1.5 rounded-lg bg-[#f4f0ff] px-2.5 py-1.5 font-label text-[10px] font-bold text-primary transition-colors hover:bg-[#ede9fe]"
          >
            <Settings2 size={12} /> {viaMeta ? "Override manually" : configured ? "Manage" : "Set up"}
          </button>
        </div>
      </div>
    </article>
  );
}
