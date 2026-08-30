"use client";
import { API_URL } from "@/lib/api";
import { CopyButton } from "./ui";

// tenantId is still accepted so the caller needn't change, but Instagram and Facebook
// no longer put it in the callback URL: Meta allows one callback URL per app per
// webhook object, so a URL naming one client could only ever serve that client.
export default function WebhookConfigGuide({ channelId }: { channelId: string; tenantId?: string | null }) {
  if (channelId === "whatsapp") {
    const url = `${API_URL}/webhook/whatsapp`;
    return (
      <div className="p-5 rounded-2xl bg-surface-subtle border border-border-subtle font-body text-xs text-ink-secondary space-y-2.5">
        <p className="font-semibold text-ink text-sm">Meta Webhook Configuration Guide:</p>
        <p>1. In your Meta Developer App, go to <strong>WhatsApp → Configuration</strong>.</p>
        <p>2. Set the Callback URL to:</p>
        <div className="flex items-center gap-2">
          <div className="flex-grow p-3 rounded-xl bg-white border border-border font-mono text-xs select-all break-all text-primary font-medium">
            {url}
          </div>
          <CopyButton text={url} />
        </div>
        <p>3. Set the Verify Token to the same value as your <strong>Webhook Verify Token</strong> configured below.</p>
        <p>4. Subscribe to <strong>messages</strong> and <strong>message_status_updates</strong> fields.</p>
        <p>5. After saving credentials, click <strong>Validate &amp; Activate</strong> to verify your token and subscribe the webhook.</p>
      </div>
    );
  }

  if (channelId === "telegram") {
    return (
      <div className="p-5 rounded-2xl bg-surface-subtle border border-border-subtle font-body text-xs text-ink-secondary space-y-2.5">
        <p className="font-semibold text-ink text-sm">Telegram Bot Configuration Guide:</p>
        <p>1. In Telegram, open <strong>@BotFather</strong> and send <strong>/newbot</strong> (or pick an existing bot).</p>
        <p>2. Copy the bot token it gives you — it looks like <span className="font-mono">123456789:AA…</span>.</p>
        <p>3. Paste it below and click <strong>Save Changes</strong>. Saving automatically registers the webhook with Telegram — no callback URL to copy.</p>
        <p>4. Click <strong>Validate &amp; Activate</strong> any time to re-verify the connection and confirm which bot is linked (e.g. after rotating the token).</p>
      </div>
    );
  }

  if (channelId === "instagram") {
    const url = `${API_URL}/webhook/instagram`;
    return (
      <div className="p-5 rounded-2xl bg-surface-subtle border border-border-subtle font-body text-xs text-ink-secondary space-y-2.5">
        <p className="font-semibold text-ink text-sm">Meta Webhook Configuration Guide:</p>
        <p>1. Paste a <strong>Page access token</strong> below, then click <strong>Validate &amp; Activate</strong>. That registers the callback URL and verify token with Meta for you — you should not need to open the Meta console at all.</p>
        <p>2. For reference, or to set it by hand, the Callback URL is:</p>
        <div className="flex items-center gap-2">
          <div className="flex-grow p-3 rounded-xl bg-white border border-border font-mono text-xs select-all break-all text-primary font-medium">
            {url}
          </div>
          <CopyButton text={url} />
        </div>
        <p>3. This one URL serves every client — no client ID in it. Aira works out who a message belongs to from the Instagram account it was sent to.</p>
        <p>4. Verify token: the same <strong>meta_webhook_verify_token</strong> your WhatsApp uses. Subscribe to <strong>messages</strong>.</p>
        <p>5. The token must come from the <strong>same Meta app the backend uses</strong>. A token from a different app is refused, and names the app it belongs to.</p>
      </div>
    );
  }

  if (channelId === "facebook") {
    const url = `${API_URL}/webhook/facebook`;
    return (
      <div className="p-5 rounded-2xl bg-surface-subtle border border-border-subtle font-body text-xs text-ink-secondary space-y-2.5">
        <p className="font-semibold text-ink text-sm">Facebook Messenger Webhook Configuration Guide:</p>
        <p>1. Paste a <strong>Page access token</strong> below, then click <strong>Validate &amp; Activate</strong>. That registers the callback URL and verify token with Meta for you — you should not need to open the Meta console at all.</p>
        <p>2. For reference, or to set it by hand, the Callback URL is:</p>
        <div className="flex items-center gap-2">
          <div className="flex-grow p-3 rounded-xl bg-white border border-border font-mono text-xs select-all break-all text-primary font-medium">
            {url}
          </div>
          <CopyButton text={url} />
        </div>
        <p>3. This one URL serves every client — no client ID in it. Aira works out who a message belongs to from the Page it was sent to.</p>
        <p>4. Verify token: the same <strong>meta_webhook_verify_token</strong> your WhatsApp uses. Subscribe to <strong>messages</strong> under your Page.</p>
        <p>5. The token must come from the <strong>same Meta app the backend uses</strong>. A token from a different app is refused, and names the app it belongs to.</p>
      </div>
    );
  }

  if (channelId === "razorpay") {
    const url = `${API_URL}/api/v1/expert-handoff/razorpay-webhook`;
    return (
      <div className="p-5 rounded-2xl bg-surface-subtle border border-border-subtle font-body text-xs text-ink-secondary space-y-2.5">
        <p className="font-semibold text-ink text-sm">Razorpay Webhook Configuration Guide:</p>
        <p>1. In Razorpay Dashboard, go to <strong>Settings → Webhooks → Add New Webhook</strong>.</p>
        <p>2. Set the Webhook URL to:</p>
        <div className="flex items-center gap-2">
          <div className="flex-grow p-3 rounded-xl bg-white border border-border font-mono text-xs select-all break-all text-primary font-medium">
            {url}
          </div>
          <CopyButton text={url} />
        </div>
        <p>3. Subscribe to the <strong>payment_link.paid</strong> event only.</p>
        <p>4. Set the webhook Secret to the same value you paste into <strong>Webhook Secret</strong> below.</p>
        <p>5. No Activate step here — payments start working as soon as all three fields are saved and a lead pays.</p>
      </div>
    );
  }

  if (channelId === "meta_ads") {
    return (
      <div className="space-y-2.5 rounded-2xl border border-indigo-100 bg-indigo-50/60 p-5 font-body text-xs text-ink-secondary">
        <p className="text-sm font-semibold text-ink">Meta Ads reporting connection</p>
        <p>1. Create or select a Meta System User with access to the required ad account.</p>
        <p>2. Generate a token with <strong>ads_read</strong> and save it with the Ads Account ID.</p>
        <p>3. Click <strong>Validate &amp; Activate</strong> to confirm the account identity.</p>
        <p>4. The performance report imports only ad sets whose destination is exactly <strong>WhatsApp</strong>.</p>
      </div>
    );
  }

  return null;
}
