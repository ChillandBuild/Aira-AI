"use client";

import { ShieldCheck } from "lucide-react";
import { CopyValue, ErrorLine } from "./DevSection";
import { describeError } from "./privateSendClient";

export type PublicKeyState =
  | { phase: "loading" }
  | { phase: "failed"; error: unknown }
  | { phase: "ready"; keys: string[] };

interface PublicKeyPanelProps {
  state: PublicKeyState;
}

/** Shows the key that signs Anril's rule bundles, so a security reviewer can check it. */
export function PublicKeyPanel({ state }: PublicKeyPanelProps) {
  return (
    <div className="space-y-3 rounded-2xl border border-border-subtle bg-white p-4">
      <div className="flex items-center gap-2">
        <ShieldCheck size={14} className="text-primary-600" />
        <p className="font-label text-[10px] font-bold uppercase tracking-wider text-ink-muted">Anril public key</p>
      </div>
      <p className="text-xs">
        Your server uses this to check that the rules it downloads really came from Anril. It is public, so it is safe to share with your
        security team. A rule bundle that doesn&apos;t match it is never used.
      </p>
      {state.phase === "loading" && <div className="h-10 animate-pulse rounded-xl bg-border-subtle" />}
      {state.phase === "failed" && <ErrorLine message={describeError(state.error)} />}
      {state.phase === "ready" &&
        state.keys.map((key, index) => (
          <CopyValue key={key} value={key} label={state.keys.length > 1 ? `Key ${index + 1}` : undefined} />
        ))}
    </div>
  );
}
