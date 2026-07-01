"use client";

import { useEffect } from "react";
import { syncPushSubscription } from "@/lib/push";

const SERVICE_WORKER_PATH = "/aira/sw.js";

export function PwaRegistrar() {
  useEffect(() => {
    if (process.env.NODE_ENV !== "production") {
      return;
    }

    if (!("serviceWorker" in navigator)) {
      return;
    }

    const registerServiceWorker = async () => {
      try {
        await navigator.serviceWorker.register(SERVICE_WORKER_PATH, {
          scope: "/aira/",
        });
        void syncPushSubscription().catch(() => {});
      } catch (error) {
        console.warn("Aira PWA service worker registration failed.", error);
      }
    };

    if (document.readyState === "complete") {
      void registerServiceWorker();
      return;
    }

    window.addEventListener("load", registerServiceWorker);

    return () => {
      window.removeEventListener("load", registerServiceWorker);
    };
  }, []);

  return null;
}
