"use client";

import { useEffect, useState, useCallback } from "react";
import { Phone, Clock, Loader2 } from "lucide-react";

import { api, type TimelineEvent } from "@/lib/api";
import { formatPhone, formatIST } from "@/lib/utils";

interface ShiftTimelineProps {
  callerId: string;
  statsFrom: string;
  statsTo?: string;
  shiftStartHour: number;
  shiftEndHour: number;
}

export default function ShiftTimeline({ callerId, statsFrom, shiftStartHour, shiftEndHour }: ShiftTimelineProps) {
  const START_HOUR = shiftStartHour;
  const END_HOUR = shiftEndHour;
  const TOTAL_SECONDS = (END_HOUR - START_HOUR) * 3600;
  const [events, setEvents] = useState<TimelineEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [date, setDate] = useState(statsFrom);

  useEffect(() => {
    setDate(statsFrom);
  }, [statsFrom]);

  const load = useCallback(async () => {
    if (!callerId) return;
    setLoading(true);
    try {
      const res = await api.analytics.callerTimeline(callerId, date);
      setEvents(Array.isArray(res.data) ? res.data : []);
    } catch (err) {
      console.error("Failed to load timeline events:", err);
      setEvents([]);
    } finally {
      setLoading(false);
    }
  }, [callerId, date]);

  useEffect(() => {
    load();
  }, [load]);

  const getEventStyle = (event: TimelineEvent) => {
    try {
      const eventDate = new Date(event.started_at);
      const dayStart = new Date(eventDate);
      dayStart.setHours(START_HOUR, 0, 0, 0);
      const startMs = eventDate.getTime();
      const baseMs = dayStart.getTime();
      const offsetSeconds = (startMs - baseMs) / 1000;
      const durationSeconds = event.ended_at
        ? (new Date(event.ended_at).getTime() - startMs) / 1000
        : (event.duration_seconds || 60);
      const left = Math.max(0, Math.min(100, (offsetSeconds / TOTAL_SECONDS) * 100));
      const width = Math.max(0.5, Math.min(100 - left, (durationSeconds / TOTAL_SECONDS) * 100));
      return { left: `${left}%`, width: `${width}%` };
    } catch {
      return { left: "0%", width: "0%" };
    }
  };

  return (
    <div className="bg-surface rounded-card p-6 shadow-card ring-1 ring-[#c4c7c7]/15">
      <div className="flex items-center justify-between mb-5 flex-wrap gap-4">
        <div>
          <h2 className="font-display text-base font-bold text-primary">Shift Timeline Visualizer</h2>
          <p className="font-label text-xs text-on-surface-muted">Analyze live calling activity blocks, status transitions, and gaps.</p>
        </div>
        <div className="flex items-center gap-1.5 bg-[#faf8f5] p-1.5 rounded-xl border border-[#e8e3db]">
          <span className="font-manrope text-[10px] text-[#78716c] font-bold uppercase pl-1">Date:</span>
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)} className="px-1.5 py-0.5 rounded bg-white border border-[#e8e3db] font-manrope text-xs text-[#292524] focus:outline-none" />
        </div>
      </div>

      {loading ? (
        <div className="py-12 flex flex-col items-center justify-center">
          <Loader2 className="animate-spin text-[#a8a29e] mb-2" size={24} />
          <p className="text-xs text-[#a8a29e]">Fetching timeline details...</p>
        </div>
      ) : (
        <div className="space-y-6">
          <div className="relative pt-4">
            <div className="w-full h-10 bg-[#e8e3db] rounded-xl relative border border-[#d6cfc9]/50 shadow-inner overflow-hidden">
              {events.map((event) => {
                if (event.type === "status" && event.status === "break") {
                  return (
                    <div
                      key={event.id}
                      className="absolute top-0 bottom-0 bg-amber-400 border-x border-amber-500/25 opacity-70"
                      style={getEventStyle(event)}
                      title={`Break Block: ${formatIST(event.started_at)} - ${event.ended_at ? formatIST(event.ended_at) : "ongoing"}`}
                    />
                  );
                }
                if (event.type === "call") {
                  let color = "bg-primary border-primary-dark";
                  if (event.outcome === "converted") color = "bg-emerald-500 border-emerald-600";
                  else if (event.outcome === "callback") color = "bg-amber-500 border-amber-600";
                  else if (event.outcome === "no_answer") color = "bg-rose-450 border-rose-500";
                  return (
                    <div
                      key={event.id}
                      className={`absolute top-1.5 bottom-1.5 rounded-md border text-[9px] font-bold text-white flex items-center justify-center cursor-pointer transition-all hover:scale-y-110 shadow-sm ${color}`}
                      style={getEventStyle(event)}
                      title={`Call (${event.outcome || "disposition"}): ${formatIST(event.started_at)} (${event.duration_seconds || 0}s)\nLead: ${event.lead_name || event.lead_phone}`}
                    >
                      <Phone size={8} className="shrink-0" />
                    </div>
                  );
                }
                return null;
              })}
            </div>
            <div className="flex justify-between text-[10px] text-[#a8a29e] font-bold px-1 mt-2">
              {(() => {
                const hourLabels: string[] = [];
                for (let h = START_HOUR; h <= END_HOUR; h += 2) {
                  hourLabels.push(`${h.toString().padStart(2, "0")}:00${h === START_HOUR || h === END_HOUR ? " IST" : ""}`);
                }
                if (hourLabels.length > 0 && !hourLabels[hourLabels.length - 1].startsWith(END_HOUR.toString().padStart(2, "0"))) {
                  hourLabels.push(`${END_HOUR.toString().padStart(2, "0")}:00 IST`);
                }
                return hourLabels.map((label) => (
                  <span key={label}>{label}</span>
                ));
              })()}
            </div>
          </div>

          <div className="bg-[#faf8f5]/50 rounded-2xl p-4 border border-[#f0ece4] max-h-[300px] overflow-y-auto space-y-2">
            <span className="font-label text-[10px] text-[#a8a29e] font-bold uppercase tracking-wider block mb-2">Detailed Log Checklist</span>
            {events.length === 0 ? (
              <p className="text-xs text-[#a8a29e] text-center py-4">No events logged for this day.</p>
            ) : (
              events.map((event) => (
                <div key={event.id} className="flex items-center justify-between py-2 border-b border-[#f0ece4] text-xs text-[#57534e]">
                  <div className="flex items-center gap-2.5">
                    <Clock size={12} className="text-[#a8a29e]" />
                    <span className="font-bold text-[#44403c]">{formatIST(event.started_at)}</span>
                    <span className="text-[#a8a29e]">·</span>
                    {event.type === "status" ? (
                      <span>Status changed to <span className="font-bold text-[#292524] capitalize">{event.status}</span></span>
                    ) : (
                      <span>
                        Called <span className="font-bold text-[#292524]">{event.lead_name || formatPhone(event.lead_phone)}</span>
                        {" ("}
                        <span className="font-medium">{event.duration_seconds || 0}s</span>
                        {")"}
                      </span>
                    )}
                  </div>
                  {event.type === "call" && (
                    <span className={`px-2 py-0.5 rounded font-bold text-[9px] uppercase border ${
                      event.outcome === "converted" ? "bg-emerald-50 text-emerald-700 border-emerald-200" :
                      event.outcome === "callback" ? "bg-amber-50 text-amber-700 border-amber-200" :
                      "bg-[#f0ece4] text-[#57534e] border-[#e8e3db]"
                    }`}>
                      {event.outcome || "Answered"}
                    </span>
                  )}
                  {event.type === "status" && (
                    <span className="px-2 py-0.5 bg-[#f0ece4] text-[#57534e] font-bold text-[9px] uppercase rounded border border-[#e8e3db]">
                      Shift Status
                    </span>
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
