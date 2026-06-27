"use client";

export function sanitizeTelNumber(phone: string | null | undefined) {
  return (phone ?? "").replace(/[^\d+]/g, "");
}

export function buildTelHref(phone: string | null | undefined) {
  const normalized = sanitizeTelNumber(phone);
  return normalized ? `tel:${normalized}` : "";
}

export function isMobileDialSurface() {
  if (typeof window === "undefined") return false;
  return window.matchMedia("(max-width: 767px), (pointer: coarse)").matches;
}

export function openNativeDialer(phone: string | null | undefined) {
  if (typeof window === "undefined") return false;

  const href = buildTelHref(phone);
  if (!href) return false;

  if (typeof document === "undefined" || !document.body) {
    window.location.assign(href);
    return true;
  }

  const anchor = document.createElement("a");
  anchor.href = href;
  anchor.rel = "noopener";
  anchor.style.display = "none";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  return true;
}
