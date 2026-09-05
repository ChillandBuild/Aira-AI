"use client";
import { useCallback, useRef, useState } from "react";
import { API_URL, getAuthHeaders } from "@/lib/api";
import { buildMetaLoginOptions } from "./metaSignupMode";
import { loadFacebookSdk } from "./useMetaSignup";

/**
 * Per-channel Embedded Signup for everything that is not WhatsApp.
 *
 * Meta makes every asset listed in a Login configuration mandatory, so one big
 * configuration blocks any customer who lacks one of its assets. These targets each
 * point at a narrow configuration instead: "page" asks only for a Page and its
 * linked Instagram account, "ads" asks only for an ad account.
 *
 * Deliberately separate from `useMetaSignup`. That hook waits for Meta's
 * WA_EMBEDDED_SIGNUP browser message before it can finish; a General login variation
 * never sends one, so reusing it would leave the spinner running forever.
 */
export type MetaChannelTarget = "page" | "ads";

export type MetaChannelPage = {
  id: string;
  name: string;
  instagram_business_account?: { id: string; username?: string } | null;
};

export type MetaChannelAdAccount = {
  id: string;
  name: string;
  account_id?: string;
  currency?: string;
};

export type MetaChannelAssets = {
  session_id: string;
  pages?: MetaChannelPage[];
  ad_accounts?: MetaChannelAdAccount[];
};

type TargetSpec = {
  configId: string;
  startPath: string;
  completePath: string;
  completeKey: "page_id" | "ad_account_id";
  emptyError: string;
};

// Not secrets — safe to expose client-side. Env vars let prod/staging override.
const TARGETS: Record<MetaChannelTarget, TargetSpec> = {
  page: {
    configId: process.env.NEXT_PUBLIC_META_PAGE_CONFIG_ID || "2226622718102220",
    startPath: "/api/v1/settings/facebook/business-login/start",
    completePath: "/api/v1/settings/facebook/business-login/complete",
    completeKey: "page_id",
    emptyError: "No Facebook Page was shared. Start again and select a Page in the Meta window.",
  },
  ads: {
    configId: process.env.NEXT_PUBLIC_META_ADS_CONFIG_ID || "28328955280071486",
    startPath: "/api/v1/settings/meta/ads-signup/start",
    completePath: "/api/v1/settings/meta/ads-signup/complete",
    completeKey: "ad_account_id",
    emptyError: "No ad account was shared. Start again and select an ad account in the Meta window.",
  },
};

export function assetOptions(
  target: MetaChannelTarget,
  assets: MetaChannelAssets | null,
): MetaChannelPage[] | MetaChannelAdAccount[] {
  if (!assets) return [];
  return (target === "page" ? assets.pages : assets.ad_accounts) ?? [];
}

export function useMetaChannelSignup({
  canManage,
  onConnected,
}: {
  canManage: boolean;
  onConnected: () => void | Promise<void>;
}) {
  const [busyTarget, setBusyTarget] = useState<MetaChannelTarget | null>(null);
  const [finishing, setFinishing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [target, setTarget] = useState<MetaChannelTarget | null>(null);
  const [assets, setAssets] = useState<MetaChannelAssets | null>(null);
  const [selectedId, setSelectedId] = useState("");
  // Guards against a second Meta window while one is still in flight, and against a
  // stale callback from a window the operator abandoned.
  const attemptRef = useRef(0);

  const stage = useCallback(async (chosen: MetaChannelTarget, code: string, attemptId: number) => {
    const spec = TARGETS[chosen];
    const auth = await getAuthHeaders();
    const res = await fetch(`${API_URL}${spec.startPath}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...auth },
      body: JSON.stringify({ code }),
    });
    const data = await res.json();
    if (attemptRef.current !== attemptId) return;
    if (!res.ok) throw new Error(data.detail || "Meta could not list the assets you granted");

    const granted = data as MetaChannelAssets;
    const options = assetOptions(chosen, granted);
    if (options.length === 0) throw new Error(spec.emptyError);
    setAssets(granted);
    setTarget(chosen);
    // One option is not a choice — preselect it so the picker is a confirmation.
    setSelectedId(options.length === 1 ? options[0].id : "");
    setBusyTarget(null);
  }, []);

  const start = useCallback(async (chosen: MetaChannelTarget) => {
    if (!canManage || busyTarget || finishing) return;
    const attemptId = ++attemptRef.current;
    setBusyTarget(chosen);
    setError(null);
    setAssets(null);
    setTarget(null);
    setSelectedId("");
    try {
      await loadFacebookSdk();
      window.FB?.login(
        (response) => {
          if (attemptRef.current !== attemptId) return;
          const code = response?.authResponse?.code;
          if (!code) {
            setBusyTarget(null);
            return;
          }
          void stage(chosen, code, attemptId).catch((err) => {
            if (attemptRef.current !== attemptId) return;
            setError(err instanceof Error ? err.message : "Connecting Meta failed");
            setBusyTarget(null);
          });
        },
        // A General login variation has no WhatsApp onboarding extras.
        buildMetaLoginOptions(TARGETS[chosen].configId, "standard")
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not open Meta signup");
      setBusyTarget(null);
    }
  }, [canManage, busyTarget, finishing, stage]);

  const complete = useCallback(async () => {
    if (!canManage || !assets || !target || !selectedId) return;
    const spec = TARGETS[target];
    setFinishing(true);
    setError(null);
    try {
      const auth = await getAuthHeaders();
      const res = await fetch(`${API_URL}${spec.completePath}`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...auth },
        body: JSON.stringify({ session_id: assets.session_id, [spec.completeKey]: selectedId }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Connecting Meta failed");
      setAssets(null);
      setTarget(null);
      setSelectedId("");
      await onConnected();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Connecting Meta failed");
    } finally {
      setFinishing(false);
    }
  }, [canManage, assets, target, selectedId, onConnected]);

  const dismiss = useCallback(() => {
    // Retire the attempt so a late Meta callback cannot reopen the picker.
    attemptRef.current += 1;
    setAssets(null);
    setTarget(null);
    setSelectedId("");
    setError(null);
    setBusyTarget(null);
  }, []);

  return {
    busyTarget,
    isBusy: Boolean(busyTarget) || finishing,
    finishing,
    error,
    target,
    assets,
    selectedId,
    setSelectedId,
    start,
    complete,
    dismiss,
  };
}
