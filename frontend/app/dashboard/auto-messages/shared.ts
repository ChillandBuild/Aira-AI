import type { AutoMessageEvent, AutoMessageSend, AutoMessageVarSource } from "@/lib/api";

export const EVENTS: {
  id: AutoMessageEvent;
  label: string;
  when: string;
  nobody: string;
  hint: string;
}[] = [
  {
    id: "interested",
    label: "Interested",
    when: "Someone leaves their number to know more",
    nobody: "People who show interest get nothing from you.",
    hint: "Use a Marketing template: your offer and a link button.",
  },
  {
    id: "signed_up",
    label: "Signed up",
    when: "Someone creates an account or registers",
    nobody: "People who sign up get nothing from you.",
    hint: "A short welcome works best. Utility templates cost less than Marketing.",
  },
  {
    id: "purchased",
    label: "Purchased",
    when: "Someone buys, at your shop counter or online",
    nobody: "Customers who buy get no thank-you.",
    hint: "Use a Utility template (thank-you or receipt). It costs less than Marketing.",
  },
];

export const EVENT_LABEL: Record<AutoMessageEvent, string> = {
  interested: "Interested",
  signed_up: "Signed up",
  purchased: "Purchased",
};

export const VAR_SOURCES: { id: AutoMessageVarSource; label: string }[] = [
  { id: "first_name", label: "Customer's first name" },
  { id: "full_name", label: "Customer's full name" },
  { id: "page_url", label: "Page they came from" },
  { id: "phone", label: "Customer's number" },
  { id: "extra", label: "A field you send (e.g. order_id)" },
  { id: "text", label: "Fixed text" },
];

export const DELAYS: { minutes: number; label: string }[] = [
  { minutes: 0, label: "Instantly" },
  { minutes: 1, label: "After 1 minute" },
  { minutes: 5, label: "After 5 minutes" },
  { minutes: 15, label: "After 15 minutes" },
  { minutes: 30, label: "After 30 minutes" },
  { minutes: 60, label: "After 1 hour" },
  { minutes: 180, label: "After 3 hours" },
  { minutes: 1440, label: "Next day" },
];

export function delayLabel(minutes: number): string {
  const known = DELAYS.find((d) => d.minutes === minutes);
  if (known) return known.label;
  if (minutes < 60) return `After ${minutes} minutes`;
  return `After ${Math.round(minutes / 60)} hours`;
}

export const SOURCE_LABEL: Record<AutoMessageSend["source"], string> = {
  website: "Website form",
  api: "App / API",
  store: "Shop counter",
};

/** Plain-words reason for a send that didn't go out. */
export function reasonText(status: AutoMessageSend["status"], reason: string | null): string | null {
  if (!reason) return null;
  switch (reason) {
    case "no_rule":
      return "No message is set up for this event yet";
    case "duplicate":
      return "Already messaged about this in the last 24 hours";
    case "opted_out":
      return "Customer asked not to be messaged";
    case "template_not_approved":
      return "The template is no longer approved by Meta";
    case "rule_removed_or_off":
      return "The message was turned off before it was due";
    default:
      return status === "failed" ? `WhatsApp refused it: ${reason}` : reason;
  }
}

export const STATUS_STYLE: Record<AutoMessageSend["status"], { label: string; cls: string }> = {
  sent: { label: "Sent", cls: "bg-emerald-50 text-emerald-700 border-emerald-200" },
  queued: { label: "Scheduled", cls: "bg-sky-50 text-sky-700 border-sky-200" },
  sending: { label: "Sending", cls: "bg-sky-50 text-sky-700 border-sky-200" },
  skipped: { label: "Not sent", cls: "bg-amber-50 text-amber-800 border-amber-200" },
  failed: { label: "Failed", cls: "bg-rose-50 text-rose-700 border-rose-200" },
};

export function formatWhen(iso: string): string {
  const d = new Date(iso);
  const sameDay = d.toDateString() === new Date().toDateString();
  const time = d.toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" });
  return sameDay ? time : `${d.toLocaleDateString("en-IN", { day: "numeric", month: "short" })}, ${time}`;
}

/** Splits a template body into text and {{n}} chips for the preview. */
export function splitBody(body: string): ({ text: string } | { variable: number })[] {
  const parts: ({ text: string } | { variable: number })[] = [];
  const re = /\{\{\s*(\d+)\s*\}\}/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(body))) {
    if (m.index > last) parts.push({ text: body.slice(last, m.index) });
    parts.push({ variable: Number(m[1]) });
    last = m.index + m[0].length;
  }
  if (last < body.length) parts.push({ text: body.slice(last) });
  return parts;
}

export const inputCls =
  "w-full rounded-xl border border-border bg-white px-3 py-2 font-body text-sm text-ink placeholder:text-ink-muted focus:border-primary/50 focus:outline-none focus:ring-2 focus:ring-primary/15 disabled:opacity-60";

export const ghostBtn =
  "inline-flex items-center gap-1.5 rounded-lg border border-border bg-white px-3 py-1.5 font-label text-xs font-semibold text-ink-secondary transition-all hover:border-primary/40 hover:text-primary disabled:opacity-40";

export const primaryBtn =
  "inline-flex items-center justify-center gap-1.5 rounded-full bg-primary px-4 py-2 font-label text-xs font-bold text-white shadow-sm transition-all hover:bg-primary/90 disabled:opacity-50";
