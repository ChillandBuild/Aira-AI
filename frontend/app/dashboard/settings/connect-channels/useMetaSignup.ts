"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { API_URL, getAuthHeaders } from "@/lib/api";
import type { EmbeddedSignupSession, MetaBusinessAssets, MetaBusinessLoginState } from "./channels";

// Not secrets — safe to expose client-side. Env var lets prod/staging override.
const META_APP_ID = process.env.NEXT_PUBLIC_META_APP_ID || "2225044871604460";
const META_UNIFIED_CONFIG_ID = process.env.NEXT_PUBLIC_META_UNIFIED_CONFIG_ID || "2026693308738446";

declare global {
  interface Window {
    FB?: {
      init: (params: { appId: string; xfbml?: boolean; version: string }) => void;
      login: (
        callback: (response: { authResponse?: { code?: string } }) => void,
        options: {
          config_id: string;
          response_type: string;
          override_default_response_type: boolean;
          extras?: { featureType?: string; sessionInfoVersion?: string };
        }
      ) => void;
    };
    fbAsyncInit?: () => void;
  }
}

let fbSdkPromise: Promise<void> | null = null;
function loadFacebookSdk(): Promise<void> {
  if (typeof window === "undefined") return Promise.resolve();
  if (window.FB) return Promise.resolve();
  if (fbSdkPromise) return fbSdkPromise;
  fbSdkPromise = new Promise((resolve) => {
    window.fbAsyncInit = () => {
      window.FB!.init({ appId: META_APP_ID, xfbml: false, version: "v25.0" });
      resolve();
    };
    const script = document.createElement("script");
    script.src = "https://connect.facebook.net/en_US/sdk.js";
    script.async = true;
    script.defer = true;
    document.body.appendChild(script);
  });
  return fbSdkPromise;
}

/**
 * Drives Meta's Embedded Signup v4: opens the Meta window, exchanges the one-time
 * code server-side, then lets the tenant pick which granted assets to connect.
 */
export function useMetaSignup({
  canManage,
  onConnected,
}: {
  canManage: boolean;
  onConnected: () => void | Promise<void>;
}) {
  const [state, setState] = useState<MetaBusinessLoginState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [assets, setAssets] = useState<MetaBusinessAssets | null>(null);
  const [selectedPageId, setSelectedPageId] = useState("");
  const [selectedAdAccountId, setSelectedAdAccountId] = useState("");
  const sessionRef = useRef<EmbeddedSignupSession>({});
  const codeRef = useRef<string | null>(null);

  const finish = useCallback(async () => {
    if (!canManage) return;
    const code = codeRef.current;
    const session = sessionRef.current;
    if (!code || !session.waba_id || !session.phone_number_id) return;
    codeRef.current = null;
    sessionRef.current = {};
    setState("connecting");
    setError(null);
    try {
      const auth = await getAuthHeaders();
      const res = await fetch(`${API_URL}/api/v1/settings/meta/unified-signup/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...auth },
        body: JSON.stringify({
          code,
          waba_id: session.waba_id,
          phone_number_id: session.phone_number_id,
          business_id: session.business_id,
          is_coexistence: session.is_coexistence ?? false,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Meta could not list the assets you granted");
      const granted = data as MetaBusinessAssets;
      setAssets(granted);
      setSelectedPageId(granted.pages.length === 1 ? granted.pages[0].id : "");
      setSelectedAdAccountId("");
      setState("selecting");
    } catch (err) {
      setState("error");
      setError(err instanceof Error ? err.message : "Connecting Meta Business failed");
    }
  }, [canManage]);

  useEffect(() => {
    function handleUnifiedMessage(event: MessageEvent) {
      if (event.origin !== "https://www.facebook.com" && event.origin !== "https://web.facebook.com") return;
      try {
        const data = typeof event.data === "string" ? JSON.parse(event.data) : event.data;
        if (
          data?.type === "WA_EMBEDDED_SIGNUP" &&
          (data?.event === "FINISH" || data?.event === "FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING")
        ) {
          sessionRef.current = {
            waba_id: data.data?.waba_id,
            phone_number_id: data.data?.phone_number_id,
            business_id: data.data?.business_id,
            is_coexistence: data.event === "FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING",
          };
          finish();
        }
      } catch {}
    }
    window.addEventListener("message", handleUnifiedMessage);
    return () => window.removeEventListener("message", handleUnifiedMessage);
  }, [finish]);

  const start = useCallback(async (isCoexistence = false) => {
    if (!canManage) return;
    setState("connecting");
    setError(null);
    codeRef.current = null;
    sessionRef.current = {};
    try {
      await loadFacebookSdk();
      window.FB?.login(
        (response) => {
          const code = response?.authResponse?.code;
          if (!code) {
            setState("idle");
            return;
          }
          codeRef.current = code;
          finish();
        },
        {
          config_id: META_UNIFIED_CONFIG_ID,
          response_type: "code",
          override_default_response_type: true,
          ...(isCoexistence ? { extras: { featureType: "whatsapp_business_app_onboarding", sessionInfoVersion: "3" } } : {}),
        }
      );
    } catch (err) {
      setState("error");
      setError(err instanceof Error ? err.message : "Could not open Meta signup");
    }
  }, [canManage, finish]);

  const complete = useCallback(async () => {
    if (!canManage || !assets || !selectedPageId) return;
    setState("finishing");
    setError(null);
    try {
      const auth = await getAuthHeaders();
      const res = await fetch(`${API_URL}/api/v1/settings/meta/unified-signup/complete`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...auth },
        body: JSON.stringify({
          session_id: assets.session_id,
          page_id: selectedPageId,
          ad_account_id: selectedAdAccountId || null,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Connecting Meta Business failed");
      setAssets(null);
      setState("success");
      await onConnected();
    } catch (err) {
      setState("error");
      setError(err instanceof Error ? err.message : "Connecting Meta Business failed");
    }
  }, [canManage, assets, selectedPageId, selectedAdAccountId, onConnected]);

  const dismissAssets = useCallback(() => {
    setAssets(null);
    setState("idle");
    setError(null);
  }, []);

  const isBusy = state === "connecting" || state === "finishing";

  return {
    state,
    error,
    assets,
    selectedPageId,
    selectedAdAccountId,
    setSelectedPageId,
    setSelectedAdAccountId,
    start,
    complete,
    dismissAssets,
    isBusy,
  };
}
