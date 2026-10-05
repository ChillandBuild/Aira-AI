"use client";

import { useState } from "react";
import type { MouseEvent } from "react";

export default function AiraId({ code }: { code?: string }) {
  const [copied, setCopied] = useState(false);
  if (!code) return null;
  const copy = async (e: MouseEvent) => {
    e.stopPropagation();
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard can be blocked (insecure origin, permissions); the code stays selectable.
    }
  };
  return (
    <button
      type="button"
      onClick={copy}
      title="Aira ID — tap to copy"
      className="inline-flex shrink-0 items-center gap-1 rounded-md border border-border bg-surface-subtle px-1.5 py-0.5 font-mono text-[10px] text-ink-muted hover:text-ink"
    >
      <span className="font-body font-semibold uppercase tracking-wider">Aira ID</span>
      <span className="select-all">{copied ? "Copied" : code}</span>
    </button>
  );
}
