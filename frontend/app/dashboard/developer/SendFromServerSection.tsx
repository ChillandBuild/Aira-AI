"use client";

import { useEffect, useState } from "react";
import { Lock } from "lucide-react";
import type { PrivateSendStatus } from "@/lib/api";
import { CodeBox, DevSection } from "./DevSection";
import { KeyPanel } from "./KeyPanel";
import { PublicKeyPanel, type PublicKeyState } from "./PublicKeyPanel";
import { ReplyModePanel } from "./ReplyModePanel";
import { developerApi } from "./privateSendClient";
import { snippetsFor, type Language } from "./sendFromServerSnippets";

interface SendFromServerSectionProps {
  /** From usePrivateSend(): null while loading or when the account doesn't have the feature. */
  status: PrivateSendStatus | null;
}

const LANGUAGES: { id: Language; label: string }[] = [
  { id: "python", label: "Python" },
  { id: "node", label: "Node.js" },
];

function usePublicKeys(enabled: boolean): PublicKeyState {
  const [state, setState] = useState<PublicKeyState>({ phase: "loading" });
  useEffect(() => {
    if (!enabled) return;
    let live = true;
    developerApi
      .publicKeys()
      .then((res) => live && setState({ phase: "ready", keys: res.public_keys }))
      .catch((error: unknown) => live && setState({ phase: "failed", error }));
    return () => {
      live = false;
    };
  }, [enabled]);
  return state;
}

export function SendFromServerSection({ status }: SendFromServerSectionProps) {
  const [language, setLanguage] = useState<Language>("python");
  const publicKeys = usePublicKeys(status !== null);

  if (!status) return null;

  const firstKey = publicKeys.phase === "ready" ? (publicKeys.keys[0] ?? null) : null;
  const snippets = snippetsFor(language, firstKey);

  return (
    <DevSection
      id="send-from-server"
      icon={Lock}
      title="Send from your server"
      intro="Your own server sends the messages, using your own WhatsApp token. Anril supplies the rules and templates. Customer numbers never leave your systems. Anril only receives daily counts."
    >
      <div className="grid gap-4 lg:grid-cols-2">
        <KeyPanel initialPrefix={status.key_prefix} />
        <ReplyModePanel initialMode={status.reply_mode} />
      </div>

      <PublicKeyPanel state={publicKeys} />

      <div className="space-y-3">
        <div className="flex gap-1 rounded-xl bg-surface-subtle p-1 text-xs font-semibold">
          {LANGUAGES.map((l) => (
            <button
              key={l.id}
              type="button"
              onClick={() => setLanguage(l.id)}
              aria-pressed={language === l.id}
              className={`rounded-lg px-3 py-1.5 transition-colors ${
                language === l.id ? "bg-white text-primary shadow-sm" : "text-ink-muted hover:text-ink"
              }`}
            >
              {l.label}
            </button>
          ))}
        </div>
        {snippets.map((s) => (
          <div key={`${language}-${s.title}`} className="space-y-1.5">
            <p className="text-xs font-semibold text-ink">{s.title}</p>
            <CodeBox code={s.code} />
          </div>
        ))}
        <p className="text-xs">
          You also need your own WhatsApp access token and phone number id. Anril never sees them. Your team picks the
          template for each event on the Auto Messages page, and the plug-in picks up changes within 5 minutes.
        </p>
      </div>

      <p className="text-xs font-semibold text-ink">
        Customer numbers never leave your systems. Anril only receives daily counts.
      </p>
    </DevSection>
  );
}
