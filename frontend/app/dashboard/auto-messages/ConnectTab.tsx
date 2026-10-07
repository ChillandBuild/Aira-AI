"use client";
import { useEffect, useState } from "react";
import { Code2, Globe, Lock, RefreshCw, Send, Webhook } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { CopyButton } from "@/app/dashboard/settings/connect-channels/ui";
import { usePrivateSend } from "./PrivateSend";
import { ghostBtn, inputCls, primaryBtn, reasonText, STATUS_STYLE } from "./shared";

const PY_SNIPPET = `pip install aira-private-send

from aira_private_send import AiraPrivateSend

aira = AiraPrivateSend(license_key="...", meta_token="...",
                       phone_number_id="...", aira_public_key="...")
aira.track("purchased", phone="+91...", name="Ravi")`;

const NODE_SNIPPET = `npm install aira-private-send

import { AiraPrivateSend } from "aira-private-send";

const aira = new AiraPrivateSend({ licenseKey: "...", metaToken: "...",
  phoneNumberId: "...", airaPublicKey: "..." });
await aira.track("purchased", { phone: "+91...", name: "Ravi" });`;

type Links = { ingest_url: string | null; form_script_url: string | null };

function CodeBlock({ code }: { code: string }) {
  return (
    <div className="relative">
      <pre className="overflow-x-auto rounded-xl bg-[#1c1917] p-4 pr-12 font-mono text-[11.5px] leading-relaxed text-[#f5f5f4]">
        {code}
      </pre>
      <div className="absolute right-2 top-2">
        <CopyButton text={code} />
      </div>
    </div>
  );
}

function Card({ icon, title, sub, children }: { icon: React.ReactNode; title: string; sub: string; children: React.ReactNode }) {
  return (
    <section className="space-y-4 rounded-[24px] border border-border-subtle bg-white p-5 sm:p-6">
      <div className="flex items-start gap-3">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">{icon}</span>
        <div>
          <h3 className="font-display text-base font-bold text-ink">{title}</h3>
          <p className="mt-0.5 font-body text-xs text-ink-secondary">{sub}</p>
        </div>
      </div>
      {children}
    </section>
  );
}

function PrivateSendCard({ keyPrefix, replyMode }: { keyPrefix: string | null; replyMode: "client" | "aira" | null }) {
  return (
    <Card
      icon={<Lock size={18} />}
      title="Your server (Private Send)"
      sub="Your own server sends the messages. Anril only receives daily counts — never names or numbers."
    >
      <dl className="space-y-2 font-body text-xs">
        <div className="grid grid-cols-[96px_1fr] gap-2">
          <dt className="font-semibold text-ink">License key</dt>
          <dd className="min-w-0 text-ink-secondary">
            <span className="break-all font-mono text-[11px] font-semibold text-primary">{keyPrefix ? `${keyPrefix}…` : "—"}</span>
            <span className="block text-ink-muted">Ask your Anril contact for the full key.</span>
          </dd>
        </div>
        <div className="grid grid-cols-[96px_1fr] gap-2">
          <dt className="font-semibold text-ink">Replies</dt>
          <dd className="text-ink-secondary">
            {replyMode === "aira"
              ? "Anril AI answers. Replies come to Anril's inbox."
              : "Your system handles replies. Anril never sees them."}
          </dd>
        </div>
      </dl>
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="min-w-0 space-y-2">
          <p className="font-body text-xs font-semibold text-ink">Python</p>
          <CodeBlock code={PY_SNIPPET} />
        </div>
        <div className="min-w-0 space-y-2">
          <p className="font-body text-xs font-semibold text-ink">Node</p>
          <CodeBlock code={NODE_SNIPPET} />
        </div>
      </div>
      <p className="font-body text-[11px] text-ink-muted">Anril only receives daily counts — never names or numbers.</p>
    </Card>
  );
}

/** Static look-alike of the website form, so owners see what customers will get. */
function FormPreview() {
  return (
    <div className="grid max-w-[340px] gap-2.5 rounded-xl border border-[#e3e3e3] bg-white p-4 shadow-sm" aria-hidden>
      <p className="text-[15px] font-semibold text-[#1a1a1a]">Get details on WhatsApp</p>
      <div className="rounded-lg border border-[#cfcfcf] px-3 py-2 text-[13px] text-[#9a9a9a]">Your name</div>
      <div className="rounded-lg border border-[#cfcfcf] px-3 py-2 text-[13px] text-[#9a9a9a]">WhatsApp number</div>
      <div className="rounded-lg bg-[#25d366] py-2 text-center text-[13px] font-semibold text-white">Send me details</div>
      <p className="text-[11px] text-[#666]">We&apos;ll send you updates on WhatsApp.</p>
    </div>
  );
}

function TryIt({ ingestUrl }: { ingestUrl: string }) {
  const [phone, setPhone] = useState("");
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState<{ status: keyof typeof STATUS_STYLE; text: string } | null>(null);

  async function run() {
    setSending(true);
    setResult(null);
    try {
      const res = await fetch(ingestUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phone, name: "Test", event: "interested" }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.error || `Rejected (HTTP ${res.status})`);
      const status = body.message_status as keyof typeof STATUS_STYLE;
      const why = reasonText(status, body.reason);
      setResult({
        status,
        text:
          status === "sent"
            ? "Sent. Check WhatsApp on that number."
            : status === "queued"
              ? "Scheduled. It goes out after the wait you set."
              : why ?? "Not sent.",
      });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "The test didn't go through");
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="space-y-3 rounded-2xl border border-primary/15 bg-primary/[0.03] p-4">
      <p className="font-body text-sm font-semibold text-ink">Try it on your own phone</p>
      <div className="grid gap-2 sm:grid-cols-[1fr_auto]">
        <input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="Your WhatsApp number" inputMode="tel" className={inputCls} />
        <button type="button" onClick={run} disabled={sending || phone.replace(/\D/g, "").length < 10} className={primaryBtn}>
          <Send size={13} /> {sending ? "Sending…" : "Send test"}
        </button>
      </div>
      {result && (
        <p className={`rounded-xl border px-3 py-2 font-body text-xs ${STATUS_STYLE[result.status]?.cls ?? ""}`}>{result.text}</p>
      )}
      <p className="font-body text-[11px] text-ink-muted">This adds you as a lead named &ldquo;Test&rdquo;, like a real customer would be.</p>
    </div>
  );
}

export function ConnectTab({ canManage }: { canManage: boolean }) {
  const [links, setLinks] = useState<Links | null>(null);
  const [forbidden, setForbidden] = useState(false);
  const [rotating, setRotating] = useState(false);
  const privateSend = usePrivateSend();

  useEffect(() => {
    api.autoMessages
      .setup()
      .then(setLinks)
      .catch((err: Error & { status?: number }) => {
        if (err.status === 403) setForbidden(true);
        setLinks({ ingest_url: null, form_script_url: null });
      });
  }, []);

  async function rotate() {
    if (links?.ingest_url && !window.confirm("Make a new link? The old one stops working at once, so you'll need to update your website and apps.")) return;
    setRotating(true);
    try {
      setLinks(await api.autoMessages.rotateToken());
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Couldn't create the link");
    } finally {
      setRotating(false);
    }
  }

  if (links === null) return <div className="h-64 animate-pulse rounded-[24px] bg-border-subtle" />;
  if (forbidden || !canManage) {
    return (
      <div className="rounded-[24px] border border-border-subtle bg-white p-8 text-center font-body text-sm text-ink-muted">
        Only admins can see the website form and connection link.
      </div>
    );
  }

  if (!links.ingest_url || !links.form_script_url) {
    return (
      <div className="space-y-5">
      {privateSend && <PrivateSendCard keyPrefix={privateSend.key_prefix} replyMode={privateSend.reply_mode} />}
      <div className="rounded-[24px] border border-border-subtle bg-white p-8 text-center sm:p-12">
        <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-primary/10 text-primary">
          <Globe size={22} />
        </span>
        <h3 className="mt-4 font-display text-lg font-bold text-ink">Connect your website and apps</h3>
        <p className="mx-auto mt-1 max-w-md font-body text-sm text-ink-secondary">
          Create your link to get a ready-made form for your website, and a web address your app, billing software or
          Zapier can send customers to.
        </p>
        <button type="button" onClick={rotate} disabled={rotating} className={`${primaryBtn} mt-5`}>
          {rotating ? "Creating…" : "Create my link"}
        </button>
      </div>
      </div>
    );
  }

  const snippet = `<div data-aira-form></div>\n<script src="${links.form_script_url}" async></script>`;
  const sample = JSON.stringify(
    { phone: "9876543210", name: "Priya", event: "purchased", order_id: "INV-1042" },
    null,
    2
  );

  return (
    <div className="space-y-5">
      {privateSend && <PrivateSendCard keyPrefix={privateSend.key_prefix} replyMode={privateSend.reply_mode} />}
      <Card icon={<Globe size={18} />} title="Website form" sub="No developer needed. Paste this where you want the form to appear.">
        <div className="grid gap-5 lg:grid-cols-[1fr_auto]">
          <div className="min-w-0 space-y-3">
            <CodeBlock code={snippet} />
            <div className="space-y-1.5 font-body text-xs text-ink-secondary">
              <p className="text-ink-muted">
                Works on WordPress, Wix, Shopify and plain HTML. In WordPress, use a &ldquo;Custom HTML&rdquo; block.
              </p>
            </div>
          </div>
          <div className="hidden lg:block">
            <p className="mb-2 font-label text-[10px] font-bold uppercase tracking-wide text-ink-muted">Customers see</p>
            <FormPreview />
          </div>
        </div>
      </Card>

      <Card
        icon={<Webhook size={18} />}
        title="Apps, billing software, Zapier & Pabbly"
        sub="Send a customer to this address whenever something happens. JSON or form fields both work."
      >
        <div className="flex items-center gap-2">
          <div className="min-w-0 flex-1 select-all break-all rounded-xl border border-border bg-surface-subtle p-3 font-mono text-[11px] font-medium text-primary">
            {links.ingest_url}
          </div>
          <CopyButton text={links.ingest_url} />
        </div>
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="space-y-2">
            <p className="flex items-center gap-1.5 font-body text-xs font-semibold text-ink">
              <Code2 size={13} /> Example (POST)
            </p>
            <CodeBlock code={sample} />
          </div>
          <dl className="space-y-2 font-body text-xs">
            {[
              ["phone", "Required. Any format: 98765 43210, +91…, 919876…"],
              ["name", "Optional. Customer's name."],
              ["event", "interested (default), signed_up or purchased."],
              ["anything else", "Kept with the customer and usable in the message, like order_id."],
            ].map(([k, v]) => (
              <div key={k} className="grid grid-cols-[96px_1fr] gap-2">
                <dt className="font-mono text-[11px] font-semibold text-primary">{k}</dt>
                <dd className="text-ink-secondary">{v}</dd>
              </div>
            ))}
          </dl>
        </div>
        <TryIt ingestUrl={links.ingest_url} />
      </Card>

      <div className="flex flex-wrap items-center justify-between gap-3 px-1">
        <p className="font-body text-[11px] text-ink-muted">
          This link only adds customers and sends your own messages. It can&apos;t read anything.
        </p>
        <button type="button" onClick={rotate} disabled={rotating} className={ghostBtn}>
          <RefreshCw size={12} className={rotating ? "animate-spin" : ""} /> New link
        </button>
      </div>
    </div>
  );
}
