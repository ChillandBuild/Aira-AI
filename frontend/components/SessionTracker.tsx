"use client";

import { useEffect, useRef } from "react";
import { useAuthRole } from "@/app/dashboard/contexts/AuthRoleContext";
import { api } from "@/lib/api";

function todayLocal() {
  return new Date().toDateString();
}

export function SessionTracker() {
  const { role, callerId } = useAuthRole();
  const lastPingedDayRef = useRef<string | null>(null);

  useEffect(() => {
    if (role !== "caller" || !callerId) return;

    const pingIfNewDay = () => {
      const today = todayLocal();
      if (lastPingedDayRef.current === today) return;
      lastPingedDayRef.current = today;
      // Force caller status to active so today's attendance is recorded —
      // re-fires on day rollover since a PWA session can stay open across midnight.
      api.callers.setMyStatus("active").catch(console.error);
    };

    pingIfNewDay();
    document.addEventListener("visibilitychange", pingIfNewDay);
    return () => document.removeEventListener("visibilitychange", pingIfNewDay);
  }, [role, callerId]);

  return null;
}
