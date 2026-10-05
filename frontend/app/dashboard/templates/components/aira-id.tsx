"use client";

import { useState } from "react";
import type { MouseEvent } from "react";
import { Check, Copy } from "lucide-react";

type AiraIdProps = {
  code?: string;
  /** "sm" = inline badge next to a name; "lg" = stand-alone pill with a copy button. */
  size?: "sm" | "lg";
  /** Extra classes on the outer element. */
  className?: string;
};

async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    // Clipboard API is blocked on plain-http hosts and in some embedded
    // browsers. Fall back to the legacy selection + execCommand path.
    try {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand("copy");
      document.body.removeChild(ta);
      return ok;
    } catch {
      return false;
    }
  }
}

/**
 * The 6-digit "Aira ID" of a template. Admins paste it into the AstroTamil
 * admin panel (WhatsApp Templates), so it has to be readable at a glance and
 * copyable with one click — including on a card whose hover overlay covers
 * everything else.
 */
export default function AiraId({ code, size = "sm", className = "" }: AiraIdProps) {
  const [copied, setCopied] = useState(false);
  if (!code) return null;

  const copy = async (e: MouseEvent) => {
    e.stopPropagation();
    e.preventDefault();
    if (await copyText(code)) {
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    }
  };

  if (size === "lg") {
    return (
      <button
        type="button"
        onClick={copy}
        title="Copy Aira ID — paste it in adminweb → WhatsApp Templates"
        aria-label={`Copy Aira ID ${code}`}
        className={`group/aira inline-flex items-center gap-2.5 rounded-xl border bg-white pl-3 pr-2 py-1.5 shadow-sm transition-colors ${
          copied ? "border-emerald-300 bg-emerald-50" : "border-primary-200 hover:border-primary-400 hover:bg-primary-50"
        } ${className}`}
      >
        <span className="flex flex-col items-start leading-none">
          <span className="font-label text-[9px] font-bold uppercase tracking-[0.14em] text-primary-600">
            Aira ID
          </span>
          <span className="mt-0.5 font-mono text-[17px] font-bold tabular-nums tracking-[0.12em] text-ink select-all">
            {code}
          </span>
        </span>
        <span
          className={`inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-white ${
            copied ? "bg-emerald-500" : "bg-primary-600 group-hover/aira:bg-primary-700"
          }`}
        >
          {copied ? <Check size={14} /> : <Copy size={13} />}
        </span>
        <span className="sr-only" aria-live="polite">{copied ? "Copied" : ""}</span>
      </button>
    );
  }

  return (
    <button
      type="button"
      onClick={copy}
      title="Copy Aira ID — paste it in adminweb → WhatsApp Templates"
      aria-label={`Copy Aira ID ${code}`}
      className={`inline-flex shrink-0 items-center gap-1.5 rounded-md border px-1.5 py-0.5 font-mono text-[11px] font-semibold tabular-nums transition-colors ${
        copied
          ? "border-emerald-300 bg-emerald-50 text-emerald-700"
          : "border-primary-200 bg-primary-50 text-primary-700 hover:border-primary-400"
      } ${className}`}
    >
      <span className="font-label text-[9px] font-bold uppercase tracking-wider">ID</span>
      <span className="select-all">{code}</span>
      {copied ? <Check size={11} /> : <Copy size={11} className="opacity-60" />}
    </button>
  );
}
