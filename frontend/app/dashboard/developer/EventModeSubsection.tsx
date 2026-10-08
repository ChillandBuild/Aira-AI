"use client";

import { useEffect, useState } from "react";
import { CopyButton } from "@/app/dashboard/settings/connect-channels/ui";
import { CodeBox } from "./DevSection";
import { developerApi, type EventsResponse } from "./privateSendClient";

interface EventModeSubsectionProps {
  apiUrl: string;
  sendTemplatePath: string;
  tenantId: string;
}

interface CodeRow {
  key: string;
  label: string;
  custom: boolean;
}

const ERROR_ROWS: { code: string; http: string; text: string }[] = [
  { code: "wrong_mode", http: "400", text: "This account sends by event, and the call carried a template_code. Send an event, or switch to Template ID above." },
  { code: "unknown_event", http: "400", text: "This account has no event with that code. Use one of the codes below." },
  { code: "no_rule", http: "409", text: "No message is set up for this event yet. Add one on the Auto Messages page." },
  { code: "private_send_on", http: "409", text: "This account sends from its own server, so Anril does not send for your app." },
  { code: "template_not_approved", http: "409", text: "The event's template is no longer approved by Meta." },
];

function exampleBody(tenantId: string): string {
  return JSON.stringify(
    { tenant_id: tenantId || "<tenant-id>", phone: "+919876543210", event: "purchased", name: "Priya", extra: { order_id: "INV-1042" }, reference: "order:1042" },
    null,
    2,
  );
}

function successBody(): string {
  return `{"ok": true, "message_id": "wamid.HBg…", "event": "purchased",
 "template": {"code": "123456", "name": "thank_you", "language": "en"}}`;
}

function curlExample(apiUrl: string, path: string, tenantId: string): string {
  const body = JSON.stringify({
    tenant_id: tenantId || "<tenant-id>",
    phone: "+919876543210",
    event: "purchased",
    name: "Priya",
    extra: { order_id: "INV-1042" },
  });
  return `BODY='${body}'
SIG=$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac "$ANRIL_SECRET" | sed 's/^.* //')
curl -X POST "${apiUrl}${path}" \\
  -H "Content-Type: application/json" \\
  -H "X-Anril-Signature: sha256=$SIG" \\
  --data "$BODY"`;
}

function toRows(events: EventsResponse): CodeRow[] {
  return [
    ...events.builtin.map((e) => ({ key: e.key, label: e.label, custom: false })),
    ...events.custom.map((e) => ({ key: e.key, label: e.label, custom: true })),
  ];
}

function EventCodes() {
  const [rows, setRows] = useState<CodeRow[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let live = true;
    developerApi
      .events()
      .then((events) => live && setRows(toRows(events)))
      .catch(() => live && setFailed(true));
    return () => {
      live = false;
    };
  }, []);

  if (failed) return <p className="text-xs text-ink-muted">Couldn&apos;t load your event codes. Reload the page to try again.</p>;
  if (!rows) return <div className="h-24 animate-pulse rounded-2xl bg-border-subtle" aria-busy="true" aria-label="Loading event codes" />;

  return (
    <div className="space-y-2">
      <p className="text-xs font-semibold text-ink">Event codes for this account</p>
      <ul className="m-0 list-none divide-y divide-border-subtle overflow-hidden rounded-2xl border border-border-subtle p-0">
        {rows.map((row) => (
          <li key={row.key} className="flex items-center justify-between gap-3 px-4 py-2.5 text-xs">
            <span className="min-w-0">
              <code className="break-words font-mono font-semibold text-primary">{row.key}</code>
              <span className="ml-2 text-ink-secondary">{row.label}</span>
              {row.custom && (
                <span className="ml-1.5 rounded-full bg-primary-50 px-2 py-0.5 text-[10px] font-semibold text-primary-600">your own</span>
              )}
            </span>
            <CopyButton text={row.key} />
          </li>
        ))}
      </ul>
      <p className="text-[11px] text-ink-muted">Add your own events on the Auto Messages page. An unknown code is rejected, never guessed.</p>
    </div>
  );
}

export function EventModeSubsection({ apiUrl, sendTemplatePath, tenantId }: EventModeSubsectionProps) {
  return (
    <div className="space-y-4">
      <div>
        <h3 className="font-display text-base font-bold text-ink">Send an event</h3>
        <p className="mt-0.5 text-xs">
          Your app says what happened, with an event code like <code className="font-mono">purchased</code>.
          Anril sends the template your team chose for that event on the Auto Messages page, so you can change the message without a deploy.
          Requests are signed as described in &ldquo;How requests are signed&rdquo; above.
        </p>
      </div>

      <CodeBox code={`POST ${apiUrl}${sendTemplatePath}`} />

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="min-w-0 space-y-2">
          <p className="text-xs font-semibold text-ink">Request body</p>
          <CodeBox code={exampleBody(tenantId)} />
        </div>
        <dl className="space-y-2 text-xs">
          {[
            ["tenant_id", "Required. Your Tenant ID from above."],
            ["event", "Required. One of the codes below."],
            ["phone", "Required. +919876543210, 919876543210 or a bare 10-digit Indian mobile all work."],
            ["name", "Optional. The customer's name, for a message that says it."],
            ["extra", "Optional. Your own values, like order_id, for a message that uses them."],
            ["reference", "Optional. Stored with the log only."],
          ].map(([name, text]) => (
            <div key={name} className="grid grid-cols-[72px_1fr] gap-2">
              <dt className="font-mono text-[11px] font-semibold text-primary">{name}</dt>
              <dd>{text}</dd>
            </div>
          ))}
        </dl>
      </div>

      <div className="space-y-2">
        <p className="text-xs font-semibold text-ink">Success — HTTP 200</p>
        <CodeBox code={successBody()} copy={false} />
      </div>

      <div className="space-y-2">
        <p className="text-xs font-semibold text-ink">Errors specific to events</p>
        <ul className="m-0 list-none divide-y divide-border-subtle overflow-hidden rounded-2xl border border-border-subtle p-0">
          {ERROR_ROWS.map((r) => (
            <li key={r.code} className="grid grid-cols-[40px_170px_1fr] gap-2 px-4 py-2.5 text-xs max-sm:grid-cols-[40px_1fr]">
              <span className="font-mono">{r.http}</span>
              <code className="break-words font-mono font-semibold text-primary">{r.code}</code>
              <span className="max-sm:col-span-2">{r.text}</span>
            </li>
          ))}
        </ul>
        <p className="text-[11px] text-ink-muted">The other codes in the Error codes section below apply here too.</p>
      </div>

      <div className="space-y-2">
        <p className="text-xs font-semibold text-ink">Example (curl)</p>
        <CodeBox code={curlExample(apiUrl, sendTemplatePath, tenantId)} />
      </div>

      <EventCodes />
    </div>
  );
}
