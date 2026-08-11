"use client";
import { API_URL } from "@/lib/api";
import { CopyButton } from "./ui";

export default function WebhookConfigGuide({ channelId, tenantId }: { channelId: string; tenantId: string | null }) {
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
    const url = tenantId ? `${API_URL}/webhook/instagram/${tenantId}` : null;
    return (
      <div className="p-5 rounded-2xl bg-surface-subtle border border-border-subtle font-body text-xs text-ink-secondary space-y-2.5">
        <p className="font-semibold text-ink text-sm">Meta Webhook Configuration Guide:</p>
        <p>1. In your Meta Developer App, add the <strong>Instagram Graph API</strong> product.</p>
        <p>2. Set the Webhook Callback URL to:</p>
        <div className="flex items-center gap-2">
          <div className="flex-grow p-3 rounded-xl bg-white border border-border font-mono text-xs select-all break-all text-primary font-medium">
            {url ?? "Retrieving webhook URL…"}
          </div>
          {url && <CopyButton text={url} />}
        </div>
        <p>3. Use the verify token you set in your WhatsApp integration (meta_webhook_verify_token).</p>
        <p>4. Subscribe to <strong>messages</strong> Webhook event fields.</p>
        <p>5. After saving credentials, click <strong>Validate &amp; Activate</strong> to auto-subscribe the webhook.</p>
      </div>
    );
  }

  if (channelId === "facebook") {
    const url = tenantId ? `${API_URL}/webhook/facebook/${tenantId}` : null;
    return (
      <div className="p-5 rounded-2xl bg-surface-subtle border border-border-subtle font-body text-xs text-ink-secondary space-y-2.5">
        <p className="font-semibold text-ink text-sm">Facebook Messenger Webhook Configuration Guide:</p>
        <p>1. In your Meta Developer App, add the <strong>Messenger</strong> product and link your Page.</p>
        <p>2. Set the Webhook Callback URL to:</p>
        <div className="flex items-center gap-2">
          <div className="flex-grow p-3 rounded-xl bg-white border border-border font-mono text-xs select-all break-all text-primary font-medium">
            {url ?? "Retrieving webhook URL…"}
          </div>
          {url && <CopyButton text={url} />}
        </div>
        <p>3. Use the same verify token configured in your WhatsApp integration (meta_webhook_verify_token).</p>
        <p>4. Subscribe to <strong>messages</strong> Webhook event fields under your Page.</p>
        <p>5. After saving credentials, click <strong>Validate &amp; Activate</strong> to auto-subscribe the webhook.</p>
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
