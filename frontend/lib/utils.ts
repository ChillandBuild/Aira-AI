import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatPhone(phone: string | null | undefined) {
  if (!phone) return "—";
  return phone.replace(/(\+\d{2})(\d{5})(\d{5})/, "$1 $2 $3");
}

export function timeAgo(dateStr: string) {
  const diff = Date.now() - new Date(dateStr).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

export function formatDateTime(dateStr: string): string {
  const d = new Date(dateStr);
  const datePart = d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
  const timePart = d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false });
  return `${datePart}, ${timePart}`;
}

/** Today's calendar date in IST, as YYYY-MM-DD.
 *  `new Date().toISOString().slice(0, 10)` returns UTC's date, which is still
 *  yesterday until 05:30 IST -- date pickers defaulting to it opened on the
 *  wrong day every early morning. */
export function istTodayIso(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date());
}

export function formatIST(dateStr: string): string {
  return new Date(dateStr).toLocaleTimeString("en-IN", {
    timeZone: "Asia/Kolkata",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

/** WhatsApp-style timestamp for conversation lists.
 *  Today → "14:32", Yesterday → "Yesterday", older → "31 Jul", different year → "31 Jul 2025" */
export function formatConvoTime(dateStr: string): string {
  const now = new Date();
  const date = new Date(dateStr);

  // Compare in IST
  const nowIST = new Date(now.toLocaleString("en-US", { timeZone: "Asia/Kolkata" }));
  const dateIST = new Date(date.toLocaleString("en-US", { timeZone: "Asia/Kolkata" }));

  const isToday = nowIST.toDateString() === dateIST.toDateString();

  const yesterday = new Date(nowIST);
  yesterday.setDate(yesterday.getDate() - 1);
  const isYesterday = yesterday.toDateString() === dateIST.toDateString();

  if (isToday) {
    return formatIST(dateStr);
  }
  if (isYesterday) {
    return "Yesterday";
  }
  if (nowIST.getFullYear() === dateIST.getFullYear()) {
    return dateIST.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
  }
  return dateIST.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

export function isActive(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function getHomeHref(role: "owner" | "caller" | null): string {
  return role === "caller" ? "/dashboard/profile" : "/dashboard";
}
