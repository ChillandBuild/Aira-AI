"use client";
import { useState } from "react";
import { Check, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { ZephyrCourier, timeAgo } from "./ui";
import { META_CHANNELS, EMBEDDED_SIGNUP_TARGETS } from "./channels";
import type { ChannelConfig, EmbeddedSignupTarget, Setting, WebhookHealth } from "./channels";
import type { MetaSignupMode } from "./metaSignupMode";

const VALUE_PROPS: Array<{ title: string; detail: string }> = [
  { title: "Secure one-click connection", detail: "Authorise once in Meta — no tokens to copy or paste" },
  { title: "Official WhatsApp Cloud API", detail: "Templates, broadcasts and delivery reporting" },
  { title: "Number and webhook linked for you", detail: "Aira subscribes your WABA automatically" },
];

/**
 * What a channel is actually doing, replacing the old single `isLive` flag.
 *
 * `isLive` was true when credentials merely existed, so Messenger could show
 * "Live" directly above "No events received yet". These five states never
 * contradict their own subtext, and Meta Ads gets its own word because it is
 * polled on a schedule rather than driven by webhooks.
 */
type ChannelState = "receiving" | "waiting" | "synced" | "attention" | "off";

const STATE_STYLES: Record<ChannelState, string> = {
  receiving: "text-emerald-600",
  waiting: "text-amber-600",
  synced: "text-indigo-600",
  attention: "text-rose-600",
  off: "text-ink-muted",
};

const DOT_STYLES: Record<ChannelState, string> = {
  receiving: "bg-emerald-500",
  waiting: "bg-amber-500",
  synced: "bg-indigo-500",
  attention: "bg-rose-500",
  off: "bg-ink-muted",
};

const RAIL_STYLES: Record<string, string> = {
  whatsapp: "bg-emerald-500",
  instagram: "bg-pink-500",
  facebook: "bg-blue-500",
  meta_ads: "bg-indigo-500",
};

export default function EmbeddedSection({
  settings,
  webhookHealth,
  healthLoading,
  canManage,
  isBusy,
  error,
  isConnected,
  activeMode,
  busyTarget,
  onConnect,
  onConnectCoexistence,
  onEmbeddedConnect,
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
  busyTarget: EmbeddedSignupTarget | null;
  onConnect: () => void;
  onConnectCoexistence: () => void;
  onEmbeddedConnect: (target: EmbeddedSignupTarget) => void;
  onRefreshHealth: () => void;
  onManageChannel: (channel: ChannelConfig) => void;
  onDisconnect: (channelId: string) => void;
}) {
  const [menuOpen, setMenuOpen] = useState(false);

  /** A settings value, or null when the row is missing or never set. */
  function val(key: string): string | null {
    const row = settings.find(s => s.key === key);
    if (!row?.is_set) return null;
    const value = row.display_value;
    return value && value !== "Not set" ? value : null;
  }

  const phoneDisplay = val("meta_phone_display") ?? val("meta_phone_number_id");
  const verifiedName = val("meta_verified_name");
  const wabaId = val("meta_waba_id");
  const pageName = val("facebook_page_name") ?? val("facebook_page_id");
  const igUsername = val("instagram_username");
  const adsName = val("meta_ads_account_name");
  const adsId = val("meta_ads_account_id");
  const connectedAt = val("meta_connected_at");

  function isConfigured(channel: ChannelConfig) {
    return channel.fields.every(f => !f.required || settings.find(s => s.key === f.key)?.is_set);
  }

  /** The Meta asset a channel is bound to — the question the old card never answered. */
  function assetFor(channel: ChannelConfig): { id: string | null; label: string | null } {
    switch (channel.id) {
      case "whatsapp":
        return { id: phoneDisplay, label: verifiedName };
      case "instagram":
        return { id: igUsername ? `@${igUsername}` : val("instagram_page_id"), label: "via linked Page" };
      case "facebook":
        return { id: pageName, label: null };
      case "meta_ads":
        return { id: adsId, label: adsName };
      default:
        return { id: null, label: null };
    }
  }

  function statusFor(channel: ChannelConfig): { state: ChannelState; label: string; detail: string } {
    if (!isConfigured(channel)) return { state: "off", label: "Not connected", detail: "Not connected yet" };

    if (webhookHealth?.token_alerts?.some(a => a.channel === channel.id)) {
      return { state: "attention", label: "Needs attention", detail: "Token rejected by Meta" };
    }

    // Meta Ads is polled on a schedule, so "no events" would read as broken.
    if (channel.id === "meta_ads") {
      const lastSync = val("meta_ads_last_sync_at");
      return lastSync
        ? { state: "synced", label: "Synced", detail: `Click-to-WhatsApp · ${timeAgo(lastSync)}` }
        : { state: "waiting", label: "Awaiting sync", detail: "Connected · first sync pending" };
    }

    const lastEvent = webhookHealth?.health?.[channel.id]?.last_event;
    if (lastEvent) {
      return { state: "receiving", label: "Receiving", detail: `Last message ${timeAgo(lastEvent)}` };
    }
    return { state: "waiting", label: "Awaiting first", detail: "Connected · nothing received yet" };
  }

  const connectedCount = META_CHANNELS.filter(isConfigured).length;

  return (
    <section className="overflow-hidden rounded-[20px] border border-border bg-white shadow-card">
      {/* ── Header ─────────────────────────────────────────────────────── */}
      <div className="grid items-center gap-6 bg-gradient-to-b from-[#fbfaff] to-white px-6 py-6 sm:grid-cols-[1fr_auto] sm:gap-10 sm:px-8">
        <div className="min-w-0">
          <p className="font-label text-[9.5px] font-bold uppercase tracking-[0.17em] text-ink-muted">
            Connectivity Hub
          </p>
          <h2 className="mt-2.5 font-display text-[26px] font-bold leading-[1.15] tracking-tight text-ink">
            {isConnected ? verifiedName ?? "Meta Business" : "Connect Meta Business"}
          </h2>
          <p className="mt-2 max-w-[60ch] font-body text-[13px] leading-relaxed text-ink-secondary">
            {isConnected
              ? "WhatsApp, Messenger, Instagram and Click-to-WhatsApp ad reporting, through one Meta connection."
              : "One secure connection brings WhatsApp, Messenger, Instagram and your Click-to-WhatsApp ad reporting into Aira."}
          </p>

          {error && (
            <p className="mt-4 rounded-xl bg-red-50 px-4 py-3 font-body text-sm text-red-700">{error}</p>
          )}

          <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-3">
            {isConnected ? (
              <>
                <span className="inline-flex items-center gap-2 font-label text-xs font-bold text-emerald-600">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                  Connected{connectedAt ? ` · ${timeAgo(connectedAt)}` : ""}
                </span>
                <button
                  type="button"
                  onClick={() => setMenuOpen(v => !v)}
                  disabled={!canManage}
                  className="inline-flex items-center gap-2 rounded-[10px] border border-border bg-white px-4 py-2 font-label text-xs font-bold text-ink shadow-sm transition-all hover:-translate-y-px hover:border-primary/40 hover:text-primary hover:shadow-[0_4px_12px_-5px_rgba(91,33,182,0.28)] disabled:cursor-not-allowed disabled:opacity-60"
                >
                  Manage connection
                </button>
                <button
                  type="button"
                  onClick={() => onDisconnect("meta")}
                  disabled={!canManage || isBusy}
                  className="font-label text-xs font-bold text-ink-muted underline decoration-transparent underline-offset-4 transition-colors hover:text-danger hover:decoration-current disabled:cursor-not-allowed disabled:opacity-60"
                >
                  Disconnect Meta
                </button>
              </>
            ) : (
              <>
                <button
                  type="button"
                  onClick={onConnect}
                  disabled={!canManage || isBusy}
                  className="inline-flex items-center gap-2 rounded-[10px] bg-gradient-to-br from-[#3b0f79] to-primary px-5 py-2.5 font-label text-[13px] font-bold text-white shadow-[0_1px_2px_rgba(46,16,101,0.24),0_6px_16px_-8px_rgba(91,33,182,0.6)] transition-all hover:-translate-y-px hover:shadow-[0_2px_4px_rgba(46,16,101,0.2),0_12px_24px_-10px_rgba(91,33,182,0.7)] disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {isBusy && activeMode === "standard" && <Loader2 size={14} className="animate-spin" />}
                  Connect Meta Business
                </button>
                <button
                  type="button"
                  onClick={onConnectCoexistence}
                  disabled={!canManage || isBusy}
                  className="inline-flex items-center gap-2 font-label text-[12.5px] font-bold text-primary underline decoration-primary/40 underline-offset-4 transition-colors hover:decoration-primary disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {isBusy && activeMode === "coexistence" && <Loader2 size={14} className="animate-spin" />}
                  Use WhatsApp Coexistence instead
                </button>
              </>
            )}
          </div>
        </div>

        <div className="hidden shrink-0 justify-self-end sm:block">
          <ZephyrCourier variant="embedded" compact />
        </div>
      </div>

      {/* ── Manage menu ────────────────────────────────────────────────── */}
      {isConnected && menuOpen && (
        <div className="grid gap-px border-t border-border-subtle bg-border-subtle sm:grid-cols-2">
          <button
            type="button"
            onClick={() => { setMenuOpen(false); onConnect(); }}
            disabled={!canManage || isBusy}
            className="flex flex-col gap-1 bg-[#fdfcfa] px-6 py-4 text-left transition-colors hover:bg-white disabled:cursor-not-allowed disabled:opacity-60 sm:px-8"
          >
            <span className="font-label text-[12.5px] font-bold text-ink">Reconnect Meta Business</span>
            <span className="font-body text-[11.5px] leading-snug text-ink-secondary">
              Refresh permissions and re-pick assets
            </span>
          </button>
          <button
            type="button"
            onClick={() => { setMenuOpen(false); onConnectCoexistence(); }}
            disabled={!canManage || isBusy}
            className="flex flex-col gap-1 bg-[#fdfcfa] px-6 py-4 text-left transition-colors hover:bg-white disabled:cursor-not-allowed disabled:opacity-60 sm:px-8"
          >
            <span className="font-label text-[12.5px] font-bold text-ink">Switch to Coexistence</span>
            <span className="font-body text-[11.5px] leading-snug text-ink-secondary">
              Keep the WhatsApp mobile app working alongside Aira
            </span>
          </button>
        </div>
      )}

      {/* ── Account strip / value props ────────────────────────────────── */}
      {isConnected ? (
        <dl className="grid border-y border-border-subtle bg-[#fdfcfa] sm:grid-cols-2 lg:grid-cols-4">
          <StripCell label="WhatsApp number" value={phoneDisplay} detail={verifiedName ? `${verifiedName} · verified` : null} />
          <StripCell label="WhatsApp Business account" value={wabaId} detail="Webhook subscribed" mono />
          <StripCell
            label="Facebook Page"
            value={pageName}
            detail={igUsername ? `Messenger + Instagram @${igUsername}` : "Messenger"}
          />
          <StripCell label="Ad account" value={adsName} detail={adsId} detailMono />
        </dl>
      ) : (
        <div className="grid border-y border-border-subtle bg-[#fdfcfa] sm:grid-cols-3">
          {VALUE_PROPS.map((prop, i) => (
            <div
              key={prop.title}
              className={cn(
                "flex items-start gap-3 px-6 py-4 sm:px-8",
                i > 0 && "border-t border-border-subtle sm:border-l sm:border-t-0"
              )}
            >
              <Check size={14} className="mt-0.5 shrink-0 text-primary" strokeWidth={2.6} />
              <div className="min-w-0">
                <p className="font-label text-[13px] font-bold leading-snug text-ink">{prop.title}</p>
                <p className="mt-1 font-body text-[11.5px] leading-snug text-ink-secondary">{prop.detail}</p>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ── Channels ───────────────────────────────────────────────────── */}
      <div className="px-6 pb-2 pt-5 sm:px-8">
        <div className="mb-1 flex items-baseline justify-between gap-3">
          <span className="font-label text-[9.5px] font-bold uppercase tracking-[0.15em] text-ink-muted">
            Channels
          </span>
          <span className="font-label text-[9.5px] font-bold uppercase tracking-[0.15em] text-ink-muted">
            {connectedCount > 0 ? `${connectedCount} connected` : "None connected yet"}
          </span>
        </div>

        <div className="flex flex-col">
          {META_CHANNELS.map(channel => {
            const configured = isConfigured(channel);
            const status = statusFor(channel);
            const asset = assetFor(channel);
            const target = EMBEDDED_SIGNUP_TARGETS[channel.id];

            return (
              <div
                key={channel.id}
                className="group relative -mx-3.5 grid min-h-[64px] grid-cols-[auto_1fr_auto] items-center gap-4 rounded-[10px] border-b border-border-subtle px-3.5 transition-colors last:border-b-0 hover:bg-surface-subtle lg:grid-cols-[auto_260px_minmax(0,1fr)_auto_auto] lg:gap-6"
              >
                {/* rail grows out of the row on hover */}
                <span
                  className={cn(
                    "absolute inset-y-3 left-0.5 w-0.5 origin-center scale-y-0 rounded-full transition-transform duration-300 group-hover:scale-y-100",
                    RAIL_STYLES[channel.id]
                  )}
                />

                <div
                  className={cn(
                    "flex h-9 w-9 items-center justify-center rounded-[10px] transition-transform duration-300 group-hover:scale-105",
                    channel.iconBg,
                    !configured && "opacity-50 grayscale"
                  )}
                >
                  <channel.icon size={17} className={channel.iconColor} />
                </div>

                <div className="min-w-0">
                  <p className="font-display text-[13.5px] font-bold leading-tight tracking-tight text-ink">
                    {channel.name}
                  </p>
                  <p className="mt-0.5 truncate font-body text-[11.5px] text-ink-secondary">{status.detail}</p>
                </div>

                <p className="hidden min-w-0 truncate font-body text-xs text-ink-secondary lg:block">
                  {asset.id ? (
                    <>
                      <span className="font-mono text-[11.5px] font-medium tabular-nums tracking-tight text-ink">
                        {asset.id}
                      </span>
                      {asset.label ? ` · ${asset.label}` : ""}
                    </>
                  ) : (
                    <span className="text-ink-muted">&mdash;</span>
                  )}
                </p>

                <span
                  className={cn(
                    "inline-flex min-w-[120px] items-center gap-2 font-label text-xs font-bold",
                    STATE_STYLES[status.state]
                  )}
                >
                  <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", DOT_STYLES[status.state])} />
                  {status.label}
                </span>

                <div className="flex min-w-[150px] items-center justify-end gap-3.5">
                  {configured ? (
                    <>
                      <button
                        type="button"
                        onClick={() => onManageChannel(channel)}
                        className="font-label text-xs font-bold text-primary underline decoration-transparent underline-offset-4 transition-colors hover:decoration-current"
                      >
                        Manage
                      </button>
                      <button
                        type="button"
                        onClick={() => onDisconnect(channel.id)}
                        disabled={!canManage}
                        className="font-label text-xs font-bold text-ink-muted underline decoration-transparent underline-offset-4 opacity-0 transition-all hover:text-danger hover:decoration-current focus-visible:opacity-100 group-hover:opacity-100 disabled:cursor-not-allowed"
                      >
                        Disconnect
                      </button>
                    </>
                  ) : target ? (
                    <button
                      type="button"
                      onClick={() => onEmbeddedConnect(target)}
                      disabled={!canManage || isBusy || busyTarget === target}
                      className="inline-flex items-center gap-2 rounded-[10px] border border-border bg-white px-4 py-2 font-label text-xs font-bold text-ink shadow-sm transition-all hover:-translate-y-px hover:border-primary/40 hover:text-primary disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {busyTarget === target && <Loader2 size={12} className="animate-spin" />}
                      Connect
                    </button>
                  ) : null}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* ── Footer ─────────────────────────────────────────────────────── */}
      <div className="mt-2 flex flex-wrap items-center justify-between gap-3 border-t border-border-subtle bg-[#fdfcfa] px-6 py-3.5 font-body text-[11.5px] text-ink-secondary sm:px-8">
        <span>
          {isConnected
            ? "Webhook verified · Graph API v21.0"
            : "Nothing to check until a channel is connected"}
        </span>
        {isConnected && (
          <button
            type="button"
            onClick={onRefreshHealth}
            disabled={healthLoading}
            className="inline-flex items-center gap-2 font-label text-xs font-bold text-primary underline decoration-transparent underline-offset-4 transition-colors hover:decoration-current disabled:cursor-wait disabled:opacity-60"
          >
            {healthLoading && <Loader2 size={12} className="animate-spin" />}
            {healthLoading ? "Checking…" : "Refresh health"}
          </button>
        )}
      </div>
    </section>
  );
}

function StripCell({
  label,
  value,
  detail,
  mono = false,
  detailMono = false,
}: {
  label: string;
  value: string | null;
  detail: string | null;
  mono?: boolean;
  detailMono?: boolean;
}) {
  return (
    <div className="min-w-0 border-b border-border-subtle px-6 py-4 transition-colors last:border-b-0 hover:bg-white sm:px-8 sm:[&:nth-child(n+3)]:border-b-0 lg:border-b-0 lg:border-l lg:first:border-l-0">
      <dt className="font-label text-[9.5px] font-bold uppercase tracking-[0.13em] text-ink-muted">{label}</dt>
      <dd
        className={cn(
          "mt-2 truncate font-display text-[14.5px] font-bold leading-tight text-ink",
          mono && "font-mono text-[13.5px] font-medium tabular-nums tracking-tight"
        )}
      >
        {value ?? <span className="font-body text-[13px] font-medium text-ink-muted">Not linked</span>}
      </dd>
      {detail && (
        <p
          className={cn(
            "mt-1 truncate font-body text-[11.5px] text-ink-secondary",
            detailMono && "font-mono tabular-nums tracking-tight"
          )}
        >
          {detail}
        </p>
      )}
    </div>
  );
}
