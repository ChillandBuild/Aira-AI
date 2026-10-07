"use client";
import { useState } from "react";
import { KeyRound, Loader2, Plus } from "lucide-react";
import { toast } from "sonner";
import { CopyButton } from "@/app/dashboard/settings/connect-channels/ui";
import { createPrivateSendKey, relTime, revokePrivateSendKey } from "@/lib/operator";
import type { PrivateSendKey, PrivateSendNewKey } from "../types";

function NewKeyDialog({ created, onClose }: { created: PrivateSendNewKey; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-sm">
      <div role="dialog" aria-modal="true" aria-label="New license key" className="w-full max-w-md rounded-card bg-white p-6 shadow-xl">
        <h3 className="text-lg font-bold text-ink">License key created</h3>
        <p className="mt-2 text-sm leading-relaxed text-warning">Copy it now — Anril can&apos;t show it again.</p>
        <div className="mt-4 flex items-start gap-2">
          <div className="min-w-0 flex-1 select-all break-all rounded-xl border border-border bg-surface-subtle p-3 font-mono text-[11px] font-medium text-primary">
            {created.key}
          </div>
          <CopyButton text={created.key} />
        </div>
        <button
          type="button"
          onClick={onClose}
          className="mt-6 w-full rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-primary/90"
        >
          I&apos;ve copied it
        </button>
      </div>
    </div>
  );
}

function KeyRow({
  k, confirming, revoking, onAskRevoke, onCancel, onRevoke,
}: {
  k: PrivateSendKey; confirming: boolean; revoking: boolean;
  onAskRevoke: () => void; onCancel: () => void; onRevoke: () => void;
}) {
  const active = k.status === "active";
  return (
    <li className="space-y-2 px-4 py-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <span className="truncate font-mono text-xs font-semibold text-ink">{k.key_prefix}…</span>
          <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${active ? "bg-green-50 text-success" : "bg-surface-mid text-ink-muted"}`}>
            {active ? "active" : "revoked"}
          </span>
        </div>
        {active && !confirming && (
          <button type="button" onClick={onAskRevoke} className="text-xs font-semibold text-danger hover:underline">Revoke</button>
        )}
      </div>
      <p className="text-xs text-ink-muted">
        Created {relTime(k.created_at)} · Last seen {k.last_seen_at ? relTime(k.last_seen_at) : "never"}
        {k.plugin_version ? ` · ${k.plugin_version}` : ""}
      </p>
      {confirming && (
        <div className="flex flex-wrap items-center gap-2 rounded-xl border border-danger/20 bg-red-50 p-3">
          <p className="min-w-0 flex-1 text-xs text-danger">Revoke this key? The client&apos;s plug-in stops sending at once.</p>
          <button type="button" onClick={onCancel} disabled={revoking} className="rounded-lg border border-border bg-white px-3 py-1.5 text-xs font-medium text-ink-secondary disabled:opacity-50">
            Cancel
          </button>
          <button type="button" onClick={onRevoke} disabled={revoking} className="rounded-lg bg-danger px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50">
            {revoking ? <Loader2 size={12} className="animate-spin" /> : "Yes, revoke"}
          </button>
        </div>
      )}
    </li>
  );
}

export function PrivateSendKeys({
  tenantId, keys, onChanged,
}: { tenantId: string; keys: PrivateSendKey[]; onChanged: () => Promise<void> }) {
  const [creating, setCreating] = useState(false);
  const [created, setCreated] = useState<PrivateSendNewKey | null>(null);
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [revokingId, setRevokingId] = useState<string | null>(null);

  async function create() {
    setCreating(true);
    try {
      setCreated(await createPrivateSendKey(tenantId));
      await onChanged();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to create key");
    } finally {
      setCreating(false);
    }
  }

  async function revoke(id: string) {
    setRevokingId(id);
    try {
      await revokePrivateSendKey(tenantId, id);
      setConfirmId(null);
      await onChanged();
      toast.success("Key revoked.");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to revoke key");
    } finally {
      setRevokingId(null);
    }
  }

  return (
    <div>
      <div className="mb-3 flex items-center justify-between gap-3">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-ink">
          <KeyRound size={16} className="text-ink-muted" />
          License keys
        </h3>
        <button
          type="button"
          onClick={create}
          disabled={creating}
          className="inline-flex items-center gap-1.5 rounded-full bg-primary px-4 py-2 font-label text-xs font-bold text-white shadow-sm transition-all hover:bg-primary/90 disabled:opacity-50"
        >
          {creating ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />} Create key
        </button>
      </div>
      <div className="overflow-hidden rounded-card border border-border bg-white shadow-sm">
        {keys.length === 0 ? (
          <p className="px-4 py-8 text-center text-sm text-ink-muted">No keys yet. Create one and give it to the client.</p>
        ) : (
          <ul className="divide-y divide-border-subtle">
            {keys.map((k) => (
              <KeyRow
                key={k.id}
                k={k}
                confirming={confirmId === k.id}
                revoking={revokingId === k.id}
                onAskRevoke={() => setConfirmId(k.id)}
                onCancel={() => setConfirmId(null)}
                onRevoke={() => revoke(k.id)}
              />
            ))}
          </ul>
        )}
      </div>
      {created && <NewKeyDialog created={created} onClose={() => setCreated(null)} />}
    </div>
  );
}
