"use client";

import { useCallback, useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { AlertCircle } from "lucide-react";
import { api } from "@/lib/api";
import { useAuthRole } from "./contexts/AuthRoleContext";

const TELECALLING_PATH = "/dashboard/telecalling";
const POLL_MS = 10_000;

/**
 * Locks every dashboard page for a telecaller who still owes call feedback.
 * The wrap-up form itself lives on the Telecalling page, so there this renders
 * nothing (its own gate takes over) and elsewhere it blocks with a way back.
 */
export function FeedbackLockGate() {
  const { role } = useAuthRole();
  const pathname = usePathname();
  const router = useRouter();
  const [pendingCount, setPendingCount] = useState(0);

  const refresh = useCallback(async () => {
    try {
      setPendingCount((await api.calls.getPendingWrapups()).length);
    } catch {
      // Network blip: keep the last known state rather than flickering the lock.
    }
  }, []);

  useEffect(() => {
    if (role !== "caller") return;
    refresh();
    const id = setInterval(refresh, POLL_MS);
    const onVisible = () => {
      if (document.visibilityState === "visible") refresh();
    };
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("focus", refresh);
    return () => {
      clearInterval(id);
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("focus", refresh);
    };
  }, [role, refresh]);

  const onTelecalling = pathname?.startsWith(TELECALLING_PATH) ?? false;
  if (role !== "caller" || pendingCount === 0 || onTelecalling) return null;

  return (
    <div
      role="alertdialog"
      aria-modal="true"
      aria-labelledby="feedback-lock-title"
      className="fixed inset-0 z-[80] flex items-center justify-center bg-[#1c1917]/85 p-4 backdrop-blur-md"
    >
      <div className="w-full max-w-md rounded-3xl border border-[#e8e3db] bg-white p-8 text-center shadow-2xl">
        <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full border border-amber-200 bg-amber-50 text-amber-600">
          <AlertCircle size={24} />
        </div>
        <h2 id="feedback-lock-title" className="font-display text-xl font-extrabold text-[#1c1917]">
          Call feedback required
        </h2>
        <p className="mt-1.5 font-body text-sm text-[#78716c]">
          You have {pendingCount} call{pendingCount === 1 ? "" : "s"} waiting for an outcome. Fill
          {pendingCount === 1 ? " it" : " them"} in to keep working.
        </p>
        <button
          onClick={() => router.push(TELECALLING_PATH)}
          className="mt-6 rounded-xl bg-primary px-5 py-2.5 font-label text-sm font-bold text-white shadow-sm transition-all hover:bg-primary-dark"
        >
          Add feedback
        </button>
      </div>
    </div>
  );
}
