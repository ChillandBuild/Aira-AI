"use client";

import { useEffect, useState } from "react";
import { KeyRound } from "lucide-react";
import { ghostBtn, primaryBtn } from "@/app/dashboard/auto-messages/shared";
import { CopyValue, ErrorLine } from "./DevSection";
import { ApiCallError, describeError, developerApi } from "./privateSendClient";

interface KeyPanelProps {
  initialPrefix: string | null;
}

type Busy = "create" | "revoke" | null;

/*
  The full key is shown once, straight after "Create key", and lives only in this
  component's state until the owner presses "I've copied it" (or leaves the page).
  It is never written to storage and never logged.
*/
export function KeyPanel({ initialPrefix }: KeyPanelProps) {
  const [prefix, setPrefix] = useState<string | null>(initialPrefix);
  const [revealed, setRevealed] = useState<string | null>(null);
  const [busy, setBusy] = useState<Busy>(null);
  const [confirmingRevoke, setConfirmingRevoke] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setPrefix(initialPrefix);
  }, [initialPrefix]);

  async function createKey() {
    setBusy("create");
    setError(null);
    try {
      const created = await developerApi.createKey();
      setPrefix(created.key_prefix);
      setRevealed(created.key);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(null);
    }
  }

  async function revokeKey() {
    setBusy("revoke");
    setError(null);
    try {
      await developerApi.revokeKey();
      setPrefix(null);
      setRevealed(null);
      setConfirmingRevoke(false);
    } catch (err) {
      if (err instanceof ApiCallError && err.code === "no_active_key") {
        setPrefix(null);
        setConfirmingRevoke(false);
      }
      setError(describeError(err));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-3 rounded-2xl border border-border-subtle bg-white p-4">
      <div className="flex items-center gap-2">
        <KeyRound size={14} className="text-primary-600" />
        <p className="font-label text-[10px] font-bold uppercase tracking-wider text-ink-muted">Your license key</p>
      </div>

      {revealed && (
        <div className="space-y-2 rounded-xl border border-amber-200 bg-amber-50 p-3">
          <CopyValue value={revealed} />
          <p role="status" className="text-xs font-semibold text-amber-800">
            Copy it now &mdash; you won&apos;t see it again. Put it in your server&apos;s environment, not in your code.
          </p>
          <button type="button" onClick={() => setRevealed(null)} className={ghostBtn}>
            I&apos;ve copied it
          </button>
        </div>
      )}

      {!revealed && prefix && (
        <div className="flex flex-wrap items-center gap-3">
          <span className="break-all rounded-lg bg-surface-subtle px-3 py-2 font-mono text-xs font-semibold text-primary">{prefix}…</span>
          {!confirmingRevoke && (
            <button type="button" onClick={() => setConfirmingRevoke(true)} className={ghostBtn}>
              Revoke key
            </button>
          )}
        </div>
      )}

      {confirmingRevoke && (
        <div className="space-y-2 rounded-xl border border-rose-200 bg-rose-50 p-3">
          <p className="text-xs font-semibold text-rose-700">Revoke? Your server stops sending at once.</p>
          <div className="flex gap-2">
            <button type="button" onClick={revokeKey} disabled={busy === "revoke"} className={primaryBtn}>
              {busy === "revoke" ? "Revoking…" : "Yes, revoke"}
            </button>
            <button type="button" onClick={() => setConfirmingRevoke(false)} disabled={busy === "revoke"} className={ghostBtn}>
              Keep it
            </button>
          </div>
        </div>
      )}

      {!prefix && !revealed && (
        <div className="space-y-2">
          <p className="text-xs">No key yet. Your server needs one to download your rules from Anril.</p>
          <button type="button" onClick={createKey} disabled={busy === "create"} className={primaryBtn}>
            {busy === "create" ? "Creating…" : "Create key"}
          </button>
        </div>
      )}

      <ErrorLine message={error} />
    </div>
  );
}
