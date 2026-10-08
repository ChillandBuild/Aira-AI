"use client";

import { useEffect, useState } from "react";
import { useAuthRole } from "@/app/dashboard/contexts/AuthRoleContext";
import { focusRing, ghostBtn, primaryBtn } from "@/app/dashboard/auto-messages/shared";
import { ErrorLine } from "./DevSection";
import { describeError, developerApi, type PartnerSendMode } from "./privateSendClient";

/*
  One choice per account: does the app call send-template with a template ID, or with an
  event? Not per call. Admins change it (settings.manage, the same permission as the other
  Developer-page switches); everyone else sees the current choice.
*/

const OPTIONS: { mode: PartnerSendMode; label: string; line: string }[] = [
  { mode: "template", label: "Template ID", line: "Your app names the exact template by its 6-digit Anril ID" },
  { mode: "event", label: "Event", line: "Your app says what happened; the template is chosen on the Auto Messages page" },
];

const optionCls = (selected: boolean) =>
  `rounded-2xl border px-4 py-3 text-left transition-colors disabled:cursor-default ${focusRing} max-sm:min-h-[44px] ${
    selected
      ? "border-primary bg-primary text-white"
      : "border-border bg-white text-ink-secondary hover:border-primary/40 disabled:opacity-60 disabled:hover:border-border"
  }`;

/** The account's saved mode: null while loading, `failed` if it could not be read. */
export function usePartnerSendMode() {
  const [mode, setMode] = useState<PartnerSendMode | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let live = true;
    developerApi
      .partnerSendMode()
      .then((res) => live && setMode(res.mode))
      .catch(() => live && setFailed(true));
    return () => {
      live = false;
    };
  }, []);

  return { mode, failed, setMode };
}

interface SendModePickerProps {
  mode: PartnerSendMode;
  onSaved: (mode: PartnerSendMode) => void;
}

export function SendModePicker({ mode, onSaved }: SendModePickerProps) {
  const { role, permissions } = useAuthRole();
  const canManage = role === "owner" || permissions.includes("settings.manage");
  const [pending, setPending] = useState<PartnerSendMode | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function choose(next: PartnerSendMode) {
    if (next === mode || saving) return;
    setSaved(false);
    setError(null);
    setPending(next);
  }

  async function confirmSwitch() {
    if (!pending) return;
    setSaving(true);
    setError(null);
    try {
      const res = await developerApi.setPartnerSendMode(pending);
      onSaved(res.mode);
      setPending(null);
      setSaved(true);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-3 rounded-2xl border border-border-subtle bg-white p-4">
      <p className="font-label text-[10px] font-bold uppercase tracking-wider text-ink-muted">How your app sends</p>
      <div role="group" aria-label="How your app sends" className="grid gap-2 sm:grid-cols-2">
        {OPTIONS.map((option) => {
          const selected = option.mode === mode;
          return (
            <button
              key={option.mode}
              type="button"
              aria-pressed={selected}
              disabled={!canManage || saving}
              onClick={() => choose(option.mode)}
              className={optionCls(selected)}
            >
              <span className="block font-display text-sm font-bold">{option.label}</span>
              <span className={`mt-0.5 block text-xs ${selected ? "text-white/85" : ""}`}>{option.line}</span>
            </button>
          );
        })}
      </div>
      {!canManage && <p className="text-[11px] text-ink-muted">Only an admin can change this.</p>}

      {pending && (
        <div className="space-y-2 rounded-xl border border-amber-200 bg-amber-50 p-3">
          <p className="text-xs font-semibold text-amber-800">
            Your app&apos;s calls must change at the same time, or they&apos;ll be refused.
          </p>
          <div className="flex gap-2">
            <button type="button" onClick={confirmSwitch} disabled={saving} className={primaryBtn}>
              {saving ? "Switching…" : "Switch"}
            </button>
            <button type="button" onClick={() => setPending(null)} disabled={saving} className={ghostBtn}>
              Cancel
            </button>
          </div>
        </div>
      )}

      <ErrorLine message={error} />
      {saved && (
        <p role="status" className="text-xs font-semibold text-emerald-700">
          Saved
        </p>
      )}
    </div>
  );
}
