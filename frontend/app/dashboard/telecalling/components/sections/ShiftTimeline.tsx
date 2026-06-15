"use client";

import { useEffect, useState, useCallback } from "react";
import { Phone, Clock, Loader2 } from "lucide-react";

import { api, type TimelineEvent } from "@/lib/api";
import { formatPhone, formatIST } from "@/lib/utils";

interface ShiftTimelineProps {
  callerId: string;
  statsFrom: string;
  statsTo?: string;
}

const START_HOUR = 9;
const END_HOUR = 19;
const TOTAL_SECONDS = (END_HOUR - START_HOUR) * 3600;

export default function ShiftTimeline({ callerId, statsFrom }: ShiftTimelineProps) {
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
          <h2 className="font-display text-base font-bold text-tertiary">Shift Timeline Visualizer</h2>
          <p className="font-label text-xs text-on-surface-muted">Analyze live calling activity blocks, status transitions, and gaps.</p>
        </div>
        <div className="flex items-center gap-1.5 bg-slate-50 p-1.5 rounded-xl border border-slate-200">
          <span className="font-label text-[10px] text-slate-500 font-bold uppercase pl-1">Date:</span>
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)} className="px-1.5 py-0.5 rounded bg-white border border-slate-200 font-body text-xs text-slate-800 focus:outline-none" />
        </div>
      </div>

      {loading ? (
        <div className="py-12 flex flex-col items-center justify-center">
          <Loader2 className="animate-spin text-slate-400 mb-2" size={24} />
          <p className="text-xs text-slate-400">Fetching timeline details...</p>
        </div>
      ) : (
        <div className="space-y-6">
          <div className="relative pt-4">
            <div className="w-full h-10 bg-slate-200 rounded-xl relative border border-slate-350/50 shadow-inner overflow-hidden">
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
            <div className="flex justify-between text-[10px] text-slate-400 font-bold px-1 mt-2">
              <span>09:00 IST</span>
              <span>11:00</span>
              <span>13:00</span>
              <span>15:00</span>
              <span>17:00</span>
              <span>19:00 IST</span>
            </div>
          </div>

          <div className="bg-slate-50/50 rounded-2xl p-4 border border-slate-100 max-h-[300px] overflow-y-auto space-y-2">
            <span className="font-label text-[10px] text-slate-450 font-bold uppercase tracking-wider block mb-2">Detailed Log Checklist</span>
            {events.length === 0 ? (
              <p className="text-xs text-slate-400 text-center py-4">No events logged for this day.</p>
            ) : (
              events.map((event) => (
                <div key={event.id} className="flex items-center justify-between py-2 border-b border-slate-100 text-xs text-slate-650">
                  <div className="flex items-center gap-2.5">
                    <Clock size={12} className="text-slate-400" />
                    <span className="font-bold text-slate-700">{formatIST(event.started_at)}</span>
                    <span className="text-slate-400">·</span>
                    {event.type === "status" ? (
                      <span>Status changed to <span className="font-bold text-slate-800 capitalize">{event.status}</span></span>
                    ) : (
                      <span>
                        Called <span className="font-bold text-slate-800">{event.lead_name || formatPhone(event.lead_phone)}</span>
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
                      "bg-slate-150 text-slate-600 border-slate-200"
                    }`}>
                      {event.outcome || "Answered"}
                    </span>
                  )}
                  {event.type === "status" && (
                    <span className="px-2 py-0.5 bg-slate-100 text-slate-600 font-bold text-[9px] uppercase rounded border border-slate-200">
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
