"use client";

import { useState } from "react";
import { SwitchPill } from "@/components/ui/controls";
import { ghostBtn, primaryBtn } from "@/app/dashboard/auto-messages/shared";
import { ErrorLine } from "./DevSection";
import { describeError, developerApi, type ReplyMode } from "./privateSendClient";

interface ReplyModePanelProps {
  initialMode: ReplyMode | null;
}

const MODE_COPY: Record<ReplyMode, { now: string; confirm: string }> = {
  aira: {
    now: "Customer replies land in Anril's inbox, where Anril AI and your team can answer them.",
    confirm:
      "Send replies to Anril's inbox? This changes your WhatsApp setup right now: customer replies will go to Anril's inbox, and your own system stops receiving them.",
  },
  client: {
    now: "ALL replies for your whole WhatsApp number go to your own system, not only replies to these messages. Anril's inbox and Anril AI see none of them.",
    confirm:
      "Send ALL replies to your own system? This changes your WhatsApp setup right now: every customer reply on your whole WhatsApp number, not only replies to these messages, stops going to Anril's inbox and goes to your own system instead.",
  },
};

export function ReplyModePanel({ initialMode }: ReplyModePanelProps) {
  const [mode, setMode] = useState<ReplyMode>(initialMode ?? "aira");
  const [pending, setPending] = useState<ReplyMode | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function confirmSwitch() {
    if (!pending) return;
    setSaving(true);
    setError(null);
    try {
      const saved = await developerApi.setReplyMode(pending);
      setMode(saved.reply_mode);
      setPending(null);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-3 rounded-2xl border border-border-subtle bg-white p-4">
      <p className="font-label text-[10px] font-bold uppercase tracking-wider text-ink-muted">Replies</p>
      <div className="flex items-center justify-between gap-4">
        <div>
          <p className="flex flex-wrap items-center gap-2 text-xs font-semibold text-ink">
            Replies come to Anril&apos;s inbox
            <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-bold text-emerald-700">Recommended</span>
          </p>
          <p className="mt-0.5 text-xs">{MODE_COPY[mode].now}</p>
        </div>
        <SwitchPill
          on={mode === "aira"}
          onChange={(next) => setPending(next ? "aira" : "client")}
          disabled={saving || pending !== null}
          loading={saving}
          size="sm"
          aria-label={mode === "aira" ? "Replies come to Anril's inbox, on" : "Replies come to Anril's inbox, off"}
        />
      </div>

      {pending && (
        <div className="space-y-2 rounded-xl border border-amber-200 bg-amber-50 p-3">
          <p className="text-xs font-semibold text-amber-800">{MODE_COPY[pending].confirm}</p>
          <div className="flex gap-2">
            <button type="button" onClick={confirmSwitch} disabled={saving} className={primaryBtn}>
              {saving ? "Switching…" : "Yes, switch"}
            </button>
            <button type="button" onClick={() => setPending(null)} disabled={saving} className={ghostBtn}>
              Cancel
            </button>
          </div>
        </div>
      )}

      <ErrorLine message={error} />
    </div>
  );
}
