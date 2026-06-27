"use client";

import { api } from "@/lib/api";

function urlBase64ToUint8Array(base64String: string) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const rawData = window.atob(base64);
  const outputArray = new Uint8Array(rawData.length);
  for (let i = 0; i < rawData.length; ++i) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
}

export function isPushSupported() {
  return (
    typeof window !== "undefined" &&
    "serviceWorker" in navigator &&
    "PushManager" in window &&
    "Notification" in window
  );
}

export async function syncPushSubscription() {
  if (!isPushSupported() || Notification.permission !== "granted") {
    return { enabled: false, reason: "permission" as const };
  }

  const { public_key: publicKey } = await api.push.publicKey();
  if (!publicKey) {
    return { enabled: false, reason: "missing_key" as const };
  }

  const registration = await navigator.serviceWorker.ready;
  const existing = await registration.pushManager.getSubscription();
  const subscription = existing ?? await registration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: urlBase64ToUint8Array(publicKey),
  });

  await api.push.saveSubscription(subscription.toJSON());
  return { enabled: true, reason: "saved" as const };
}

export async function requestAndSyncPushSubscription() {
  if (!isPushSupported()) {
    return { enabled: false, reason: "unsupported" as const };
  }
  const permission = await Notification.requestPermission();
  if (permission !== "granted") {
    return { enabled: false, reason: "denied" as const };
  }
  return syncPushSubscription();
}
