"use client";
import { useState } from "react";
import { AlertTriangle, Loader2, X } from "lucide-react";
import { Portal } from "./ui";
import type { DisconnectTarget } from "./disconnect";
import { TickMark } from "@/components/ui/controls";

export default function DisconnectDialog({
  target, busy, error, onConfirm, onCancel,
}: {
  target: DisconnectTarget;
  busy: boolean;
  error: string | null;
  onConfirm: (releaseAssets: boolean) => void;
  onCancel: () => void;
}) {
  const [releaseAssets, setReleaseAssets] = useState(false);

  return (
    <Portal>
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-4 backdrop-blur-[3px]">
        <div className="w-full max-w-lg overflow-hidden rounded-card bg-surface shadow-card ring-1 ring-[#c4c7c7]/20">
          <div className="flex items-start justify-between border-b border-border-subtle p-6">
            <div className="flex items-start gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-red-100 text-red-600">
                <AlertTriangle size={19} />
              </div>
              <div>
                <h2 className="font-display text-lg font-bold text-ink">Disconnect {target.label}?</h2>
                <p className="mt-1 font-body text-xs text-ink-muted">This stops message delivery immediately.</p>
              </div>
            </div>
            <button type="button" onClick={onCancel} aria-label="Cancel disconnect" className="rounded-lg p-1.5 text-on-surface-muted transition-colors hover:bg-surface-low hover:text-on-surface">
              <X size={18} />
            </button>
          </div>

          <div className="space-y-4 p-6">
            {error && <p className="rounded-xl bg-red-50 px-3 py-2 font-body text-xs text-red-700">{error}</p>}
            <ul className="space-y-1.5 font-body text-sm text-[#57534e]">
              {target.stops.map(clause => <li key={clause}>· {clause}</li>)}
              <li>· Aira&apos;s webhooks are unsubscribed at the provider</li>
              <li>· Stored tokens are deleted from Aira</li>
            </ul>

            {target.sharesMetaToken && (
              <p className="rounded-xl bg-amber-50 px-3 py-2.5 font-body text-xs text-amber-800">
                Instagram and Messenger share this Meta token. If they were connected through
                Embedded Onboarding, reconnect them afterwards.
              </p>
            )}

            <button
              type="button"
              role="checkbox"
              aria-checked={releaseAssets}
              onClick={() => setReleaseAssets(!releaseAssets)}
              className="flex w-full items-start gap-2.5 rounded-xl border border-border-subtle p-3 text-left transition-colors hover:border-border"
            >
              <TickMark checked={releaseAssets} size="sm" className="mt-0.5" />
              <span className="font-body text-xs text-ink-secondary">
                Also release these assets so they can be connected to a different Aira workspace.
                <span className="mt-0.5 block text-ink-muted">Leave this off to keep them reserved for you.</span>
              </span>
            </button>
          </div>

          <div className="flex items-center justify-end gap-2 border-t border-border-subtle bg-surface-low p-5">
            <button type="button" onClick={onCancel} autoFocus className="rounded-xl px-3 py-2 font-label text-sm font-semibold text-ink-muted hover:bg-white">Cancel</button>
            <button type="button" onClick={() => onConfirm(releaseAssets)} disabled={busy} className="inline-flex items-center gap-2 rounded-xl bg-red-600 px-4 py-2.5 font-label text-sm font-bold text-white transition-colors hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-60">
              {busy ? <><Loader2 size={16} className="animate-spin" />Disconnecting…</> : "Disconnect"}
            </button>
          </div>
        </div>
      </div>
    </Portal>
  );
}
