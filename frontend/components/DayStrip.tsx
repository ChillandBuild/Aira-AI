"use client";
import { useEffect, useRef, useState } from "react";
import { Inbox, Send as SendIcon, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";

export interface DailyMessageStat {
  day: string;
  inbound: number;
  outbound: number;
  ai: number;
  human: number;
}

function dayLabel(dayIso: string): { top: string; bottom: string } {
  const date = new Date(`${dayIso}T00:00:00`);
  const today = new Date();
  const isToday = date.toDateString() === today.toDateString();
  return {
    top: isToday ? "Today" : date.toLocaleDateString("en-IN", { weekday: "short" }),
    bottom: date.toLocaleDateString("en-IN", { day: "numeric", month: "short" }),
  };
}

/** Clickable day strip (last N days) + the selected day's inbound/outbound/AI-handled counts. */
export function DayStrip({ data }: { data: DailyMessageStat[] }) {
  const [selectedDay, setSelectedDay] = useState<string | null>(null);
  const active = data.find((d) => d.day === selectedDay) ?? data[data.length - 1];
  const activeButtonRef = useRef<HTMLButtonElement>(null);

  // Keep the active day scrolled into view — on mount this ensures "Today"
  // (the last item) isn't hidden off the right edge in a card narrower than
  // the full strip.
  useEffect(() => {
    activeButtonRef.current?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, [active?.day]);

  if (data.length === 0) {
    return <p className="font-body text-sm text-ink-muted">No message activity yet.</p>;
  }

  return (
    <div>
      <div className="flex gap-1.5 overflow-x-auto pb-1 mb-6 -mx-1 px-1">
        {data.map((d) => {
          const { top, bottom } = dayLabel(d.day);
          const isActive = d.day === active.day;
          return (
            <button
              key={d.day}
              ref={isActive ? activeButtonRef : undefined}
              type="button"
              onClick={() => setSelectedDay(d.day)}
              aria-pressed={isActive}
              className={cn(
                "flex min-w-[52px] shrink-0 flex-col items-center gap-0.5 rounded-xl px-2.5 py-1.5 transition-colors",
                isActive ? "bg-primary text-white" : "text-ink-muted hover:bg-surface-low",
              )}
            >
              <span className="font-label text-[10px] font-bold uppercase tracking-wide">{top}</span>
              <span className={cn("font-mono text-[11px]", isActive ? "text-white/80" : "text-ink-muted/70")}>
                {bottom}
              </span>
            </button>
          );
        })}
      </div>

      <div className="space-y-5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-blue-50 flex items-center justify-center">
              <Inbox size={16} className="text-blue-600" />
            </div>
            <div>
              <div className="font-body font-semibold text-[13px] text-ink">Inbound</div>
              <div className="font-body text-xs text-ink-muted">Messages received</div>
            </div>
          </div>
          <div className="font-mono font-bold text-ink text-[20px]">{active.inbound}</div>
        </div>

        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-emerald-50 flex items-center justify-center">
              <SendIcon size={16} className="text-emerald-600" />
            </div>
            <div>
              <div className="font-body font-semibold text-[13px] text-ink">Outbound</div>
              <div className="font-body text-xs text-ink-muted">Replies sent</div>
            </div>
          </div>
          <div className="font-mono font-bold text-ink text-[20px]">{active.outbound}</div>
        </div>

        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-purple-50 flex items-center justify-center">
              <Sparkles size={16} className="text-purple-600" />
            </div>
            <div>
              <div className="font-body font-semibold text-[13px] text-ink">AI handled</div>
              <div className="font-body text-xs text-ink-muted">Auto-replies sent</div>
            </div>
          </div>
          <div className="font-mono font-bold text-ink text-[20px]">{active.ai}</div>
        </div>
      </div>
    </div>
  );
}
