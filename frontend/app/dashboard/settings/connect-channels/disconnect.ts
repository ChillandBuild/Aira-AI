import { API_URL, getAuthHeaders } from "@/lib/api";
import { CHANNELS, META_CHANNEL_IDS } from "./channels";
import type { Setting } from "./channels";

/** Meta Ads and Razorpay are not messaging channels — say what each one actually stops doing. */
const STOPS_VERB: Record<string, string> = {
  meta_ads: "stops importing ad performance data",
  razorpay: "stops accepting in-chat payments",
};

function stopsClause(channelId: string): string {
  const name = CHANNELS.find(c => c.id === channelId)?.name ?? channelId;
  return `${name} ${STOPS_VERB[channelId] ?? "stops receiving and sending messages"}`;
}

export type DisconnectTarget = {
  channel: string;
  label: string;
  stops: string[];
  sharesMetaToken: boolean;
};

/** What the confirm dialog must tell the user before this disconnect runs. */
export function buildDisconnectTarget(channelId: string, settings: Setting[]): DisconnectTarget {
  const isConfigured = (id: string) => {
    const channel = CHANNELS.find(c => c.id === id);
    return Boolean(channel?.fields.every(f => settings.find(s => s.key === f.key)?.is_set));
  };

  if (channelId === "meta") {
    return {
      channel: "meta",
      label: "Meta Business",
      stops: META_CHANNEL_IDS.filter(isConfigured).map(stopsClause),
      sharesMetaToken: false,
    };
  }

  const channel = CHANNELS.find(c => c.id === channelId);
  return {
    channel: channelId,
    label: channel?.name ?? channelId,
    stops: channel ? [stopsClause(channelId)] : [],
    // WhatsApp's token is the one the embedded flow also used for the Page and Instagram.
    sharesMetaToken: channelId === "whatsapp",
  };
}

export async function disconnectChannel(channel: string, releaseAssets: boolean): Promise<void> {
  const auth = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/v1/settings/disconnect`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...auth },
    body: JSON.stringify({ channel, release_assets: releaseAssets }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || "Disconnect failed");
  }
}
