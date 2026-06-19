"use client";
import { useState, useEffect } from "react";
import { Clock } from "lucide-react";
import { NotificationBell } from "@/components/NotificationBell";
import { ProfileMenu } from "@/components/ProfileMenu";

export function AppHeader({ onOpenCalendar }: { onOpenCalendar: () => void }) {
  const [time, setTime] = useState<string>("");

  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      setTime(now.toLocaleTimeString("en-US", { hour12: false, hour: '2-digit', minute: '2-digit' }));
    };
    updateTime();
    const interval = setInterval(updateTime, 1000);
    return () => clearInterval(interval);
  }, []);

  return (
    <header className="sticky top-0 z-40 h-14 flex items-center justify-end gap-2.5 px-7 bg-[#faf8f5] border-b border-[#e8e3db]">
      <button
        onClick={onOpenCalendar}
        className="flex items-center gap-1.5 h-[34px] px-3 transition-all text-[#1c1917] font-mono text-[13px] font-semibold tracking-wide hover:bg-[#f0ece4] bg-transparent border border-[#e8e3db] rounded-lg"
        title="Schedule & Notes"
      >
        <Clock size={13} className="opacity-50" />
        <span>{time || "00:00"}</span>
        <span className="sr-only">Schedule & Notes</span>
      </button>
      <NotificationBell />
      <ProfileMenu />
    </header>
  );
}
