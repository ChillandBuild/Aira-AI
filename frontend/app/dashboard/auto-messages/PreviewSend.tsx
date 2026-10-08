"use client";
import { useState } from "react";
import { Send } from "lucide-react";
import { api } from "@/lib/api";
import { ghostBtn, inputCls } from "./shared";

type Result = { kind: "ok" | "fail"; text: string } | null;

function prettyPhone(raw: string): string {
  const digits = raw.replace(/\D/g, "");
  return digits.length === 10 ? `${digits.slice(0, 5)} ${digits.slice(5)}` : raw.trim();
}

/** "Send me a preview": sends the saved message to the owner's own number. Makes no lead and no log row. */
export function PreviewSend({ ruleId, isDirty }: { ruleId: string | null; isDirty: boolean }) {
  const [open, setOpen] = useState(false);
  const [phone, setPhone] = useState("");
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState<Result>(null);

  async function send() {
    if (!ruleId) return;
    setSending(true);
    setResult(null);
    try {
      const res = await api.autoMessages.previewRule(ruleId, phone.trim());
      setResult(
        res.status === "sent"
          ? { kind: "ok", text: `Sent to ${prettyPhone(phone)}. Check your phone.` }
          : { kind: "fail", text: res.reason ?? "The preview didn't go out. Try again." }
      );
    } catch (err) {
      setResult({ kind: "fail", text: err instanceof Error ? err.message : "The preview didn't go out. Try again." });
    } finally {
      setSending(false);
    }
  }

  if (!open) {
    return (
      <div className="flex flex-col gap-1">
        <button type="button" onClick={() => setOpen(true)} disabled={!ruleId} className={ghostBtn}>
          <Send size={12} /> Send me a preview
        </button>
        {!ruleId && <p className="font-body text-[11px] text-ink-muted">Save the message first, then you can preview it.</p>}
      </div>
    );
  }

  return (
    <div className="w-full space-y-2 rounded-xl border border-border-subtle p-3 sm:max-w-md">
      <label htmlFor="preview-phone" className="font-label text-xs font-bold text-ink">
        Your WhatsApp number
      </label>
      <div className="grid gap-2 sm:grid-cols-[1fr_auto]">
        <input
          id="preview-phone"
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
          placeholder="98765 43210"
          inputMode="tel"
          autoComplete="tel"
          className={inputCls}
        />
        <button type="button" onClick={send} disabled={sending || phone.replace(/\D/g, "").length < 10} className={ghostBtn}>
          {sending ? "Sending…" : "Send"}
        </button>
      </div>
      {isDirty && (
        <p className="font-body text-[11px] text-ink-muted">The preview uses the saved message. Save first to see your changes.</p>
      )}
      {result?.kind === "ok" && (
        <p role="status" className="font-body text-xs font-semibold text-emerald-700">
          {result.text}
        </p>
      )}
      {result?.kind === "fail" && (
        <p role="alert" className="font-body text-xs text-danger">
          {result.text}
        </p>
      )}
    </div>
  );
}
