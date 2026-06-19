"use client";
import { useEffect, useState, useCallback, useMemo } from "react";
import { format, parseISO, subMonths } from "date-fns";
import { Loader2, CalendarCheck, UserCheck, UserX, Percent, Download } from "lucide-react";
import { api, AttendanceDay } from "@/lib/api";
import { WEEKDAY_LABELS, buildMiniMonths } from "./helpers";

interface AttendanceMiniProps {
  callerId: string;
  readOnly?: boolean;
}

export default function AttendanceMini({ callerId, readOnly = false }: AttendanceMiniProps) {
  const today = format(new Date(), "yyyy-MM-dd");
  const [days, setDays] = useState<AttendanceDay[]>([]);
  const [loading, setLoading] = useState(true);
  const [markDate, setMarkDate] = useState(today);
  const [saving, setSaving] = useState<"present" | "absent" | null>(null);

  // Date filters states
  const [fromFilter, setFromFilter] = useState(() => format(subMonths(new Date(), 5), "yyyy-MM-dd"));
  const [toFilter, setToFilter] = useState(today);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      // Fetch past 6 months to allow sufficient date filtering
      const res = await api.team.attendanceForCaller(callerId, 6);
      setDays(res.data.days);
    } catch (err) {
      console.error("Failed to load caller attendance:", err);
      setDays([]);
    } finally {
      setLoading(false);
    }
  }, [callerId]);

  useEffect(() => {
    load();
  }, [load]);

  async function mark(status: "present" | "absent") {
    if (readOnly || saving !== null) return;
    setSaving(status);
    try {
      await api.team.markAttendance(callerId, markDate, status);
      await load();
    } catch (err) {
      console.error("Failed to mark attendance:", err);
    } finally {
      setSaving(null);
    }
  }

  // Filtered days based on fromFilter and toFilter
  const filteredDays = useMemo(() => {
    return days.filter((d) => {
      if (fromFilter && d.date < fromFilter) return false;
      if (toFilter && d.date > toFilter) return false;
      return true;
    });
  }, [days, fromFilter, toFilter]);

  // KPIs derived from the filtered range
  const { presentCount, absentCount, rate } = useMemo(() => {
    const present = filteredDays.filter((d) => d.status === "present").length;
    const absent = filteredDays.filter((d) => d.status === "absent").length;
    const total = present + absent;
    return {
      presentCount: present,
      absentCount: absent,
      rate: total > 0 ? Math.round((present / total) * 100) : 0,
    };
  }, [filteredDays]);

  const markDayStatus = useMemo(() => {
    return days.find((d) => d.date === markDate)?.status;
  }, [days, markDate]);

  const months = useMemo(() => buildMiniMonths(filteredDays, 6), [filteredDays]);

  const handleExportCsv = () => {
    if (filteredDays.length === 0) return;
    const header = "Date,Status";
    const rowsCsv = filteredDays.map((d) => `${d.date},${d.status}`);
    const csv = [header, ...rowsCsv].join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `attendance_report_${callerId}_${fromFilter || "start"}_to_${toFilter || "end"}.csv`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  if (loading) {
    return (
      <div className="bg-surface rounded-card p-6 border border-border-subtle shadow-card flex items-center justify-center h-48">
        <Loader2 className="animate-spin text-primary" size={24} />
      </div>
    );
  }

  return (
    <div className="bg-surface rounded-card border border-border-subtle shadow-card p-6">
      {/* Header with Title and Filters */}
      <div className="flex items-center justify-between flex-wrap gap-4 border-b border-border-subtle pb-4 mb-5">
        <div className="flex items-center gap-2">
          <CalendarCheck size={18} className="text-primary" />
          <h3 className="font-display font-bold text-tertiary text-sm">Attendance Log</h3>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {/* Filters */}
          <div className="flex items-center gap-1.5 bg-[#faf8f5] p-1.5 rounded-xl border border-[#e8e3db]">
            <span className="font-label text-[9px] text-[#78716c] font-bold uppercase pl-1">Filter:</span>
            <input
              type="date"
              value={fromFilter}
              max={toFilter}
              onChange={(e) => setFromFilter(e.target.value)}
              className="px-1 py-0.5 rounded bg-white border border-[#e8e3db] font-body text-[10px] text-[#292524] focus:outline-none w-24"
            />
            <span className="text-[#a8a29e] text-[10px]">to</span>
            <input
              type="date"
              value={toFilter}
              min={fromFilter}
              max={today}
              onChange={(e) => setToFilter(e.target.value)}
              className="px-1 py-0.5 rounded bg-white border border-[#e8e3db] font-body text-[10px] text-[#292524] focus:outline-none w-24"
            />
            <button
              onClick={handleExportCsv}
              disabled={filteredDays.length === 0}
              title="Download CSV"
              className="flex items-center gap-1 px-2.5 py-1 bg-primary text-white rounded-lg hover:bg-primary/95 disabled:opacity-50 disabled:cursor-not-allowed font-label text-[10px] font-bold transition-colors ml-1 shadow-sm"
            >
              <Download size={10} /> CSV
            </button>
          </div>
        </div>
      </div>

      {/* KPI Stats Cards (Horizontal, Compact, and Beautiful) */}
      <div className="grid grid-cols-3 gap-3 mb-5">
        <div className="bg-emerald-55/40 rounded-xl border border-emerald-100 flex items-center shadow-sm hover:shadow transition-shadow p-3 gap-3">
          <div className="rounded-lg bg-emerald-100 text-emerald-600 shrink-0 p-2">
            <UserCheck size={14} />
          </div>
          <div>
            <span className="block font-display font-black text-[#1c1917] leading-none text-lg">
              {presentCount}
            </span>
            <span className="text-emerald-700 font-label text-[8px] uppercase font-bold tracking-wider mt-0.5 block">
              Present
            </span>
          </div>
        </div>

        <div className="bg-rose-55/40 rounded-xl border border-rose-100 flex items-center shadow-sm hover:shadow transition-shadow p-3 gap-3">
          <div className="rounded-lg bg-rose-100 text-rose-600 shrink-0 p-2">
            <UserX size={14} />
          </div>
          <div>
            <span className="block font-display font-black text-[#1c1917] leading-none text-lg">
              {absentCount}
            </span>
            <span className="text-rose-700 font-label text-[8px] uppercase font-bold tracking-wider mt-0.5 block">
              Absent
            </span>
          </div>
        </div>

        <div className="bg-indigo-55/40 rounded-xl border border-indigo-100 flex items-center shadow-sm hover:shadow transition-shadow p-3 gap-3">
          <div className="rounded-lg bg-indigo-100 text-indigo-600 shrink-0 p-2">
            <Percent size={14} />
          </div>
          <div>
            <span className="block font-display font-black text-[#1c1917] leading-none text-lg">
              {rate}%
            </span>
            <span className="text-indigo-700 font-label text-[8px] uppercase font-bold tracking-wider mt-0.5 block">
              Rate
            </span>
          </div>
        </div>
      </div>

      {/* Admin Attendance Marker Panel */}
      {!readOnly && (
        <div className="flex flex-wrap items-center gap-2 mb-6 p-3 rounded-2xl bg-[#faf8f5] border border-[#e8e3db]/60 shadow-inner">
          <span className="font-label text-[10px] text-[#78716c] font-bold uppercase pl-1">Mark Attendance:</span>
          <input
            type="date"
            value={markDate}
            max={today}
            onChange={(e) => setMarkDate(e.target.value)}
            className="input h-8 px-2.5 text-xs w-auto border border-[#e8e3db] focus:outline-none rounded-xl"
          />
          <button
            onClick={() => mark("present")}
            disabled={saving !== null}
            className={`px-3.5 py-1.5 rounded-xl text-xs font-label font-bold border transition-colors flex items-center gap-1 ${
              markDayStatus === "present"
                ? "bg-emerald-500 text-white border-emerald-500"
                : "bg-white text-emerald-600 border-emerald-200 hover:bg-emerald-55"
            }`}
          >
            {saving === "present" && <Loader2 size={12} className="animate-spin" />}
            Present
          </button>
          <button
            onClick={() => mark("absent")}
            disabled={saving !== null}
            className={`px-3.5 py-1.5 rounded-xl text-xs font-label font-bold border transition-colors flex items-center gap-1 ${
              markDayStatus === "absent"
                ? "bg-rose-500 text-white border-rose-500"
                : "bg-white text-rose-600 border-rose-200 hover:bg-rose-55"
            }`}
          >
            {saving === "absent" && <Loader2 size={12} className="animate-spin" />}
            Absent
          </button>
        </div>
      )}

      {/* Dynamic Monthly Calendar Grid */}
      {months.length === 0 ? (
        <div className="text-center py-8 text-xs text-ink-muted font-body">No attendance records in this range.</div>
      ) : (
        <div className="grid gap-3 grid-cols-2 sm:grid-cols-3 lg:grid-cols-6">
          {months.map((m) => (
            <div
              key={m.key}
              className="rounded-xl border border-border-subtle/80 bg-surface p-1.5 shadow-sm hover:shadow-md hover:border-primary/20 transition-all duration-150 max-w-[170px] w-full mx-auto"
            >
              <div className="text-center text-[9.5px] font-label font-bold text-tertiary mb-1.5 tracking-wide bg-[#faf8f5] py-0.5 rounded-md border border-[#f0ece4]">
                {m.label}
              </div>
              <div className="grid grid-cols-7 gap-[1px] mb-1">
                {WEEKDAY_LABELS.map((d, i) => (
                  <div key={i} className="text-center text-[6.5px] font-label font-semibold text-ink-muted/50 uppercase">
                    {d}
                  </div>
                ))}
              </div>
              {m.weeks.map((week, wi) => (
                <div key={wi} className="grid grid-cols-7 gap-[1px] mb-[1px]">
                  {week.map((cell, di) => {
                    if (!cell) {
                      return <span key={`pad-${wi}-${di}`} className="block w-full aspect-square" />;
                    }

                    let cellClass = "";
                    let textClass = "";

                    if (cell.status === "present") {
                      cellClass =
                        "bg-gradient-to-br from-emerald-400 to-emerald-500 border border-emerald-500/20 shadow-[0_1px_2px_rgba(16,185,129,0.15)] hover:from-emerald-500 hover:to-emerald-600 hover:scale-105 transition-all cursor-pointer";
                      textClass = "text-white font-bold";
                    } else if (cell.status === "absent") {
                      cellClass =
                        "bg-gradient-to-br from-rose-400 to-rose-500 border border-rose-500/20 shadow-[0_1px_2px_rgba(244,63,94,0.15)] hover:from-rose-500 hover:to-rose-600 hover:scale-105 transition-all cursor-pointer";
                      textClass = "text-white font-bold";
                    } else if (cell.status === "holiday") {
                      cellClass =
                        "bg-gradient-to-br from-sky-400 to-sky-500 border border-sky-500/20 shadow-[0_1px_2px_rgba(14,165,233,0.15)] hover:from-sky-500 hover:to-sky-600 hover:scale-105 transition-all cursor-pointer";
                      textClass = "text-white font-bold";
                    } else {
                      cellClass = "bg-[#faf8f5] border border-[#f0ece4] hover:bg-[#f0ece4]";
                      textClass = "text-[#a8a29e]/80 font-medium";
                    }

                    return (
                      <span
                        key={cell.date}
                        title={`${format(parseISO(cell.date), "MMM d, yyyy")}: ${cell.status}`}
                        className={`relative flex items-center justify-center w-full aspect-square rounded-[3px] select-none text-[6.5px] sm:text-[7.5px] ${cellClass}`}
                      >
                        <span className={textClass}>{format(parseISO(cell.date), "d")}</span>
                      </span>
                    );
                  })}
                </div>
              ))}
            </div>
          ))}
        </div>
      )}

      {/* Legend */}
      <div className="flex items-center flex-wrap gap-x-4 gap-y-2 mt-5 pt-4 border-t border-border-subtle text-[10px] text-ink-muted font-body justify-center">
        <div className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded bg-gradient-to-br from-emerald-400 to-emerald-500 inline-block border border-emerald-500/10 shadow-sm" /> Present
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded bg-gradient-to-br from-rose-400 to-rose-500 inline-block border border-rose-500/10 shadow-sm" /> Absent
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded bg-gradient-to-br from-sky-400 to-sky-500 inline-block border border-sky-500/10 shadow-sm" /> Holiday
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded bg-[#faf8f5] inline-block border border-[#f0ece4]" /> Future / No Data
        </div>
      </div>
    </div>
  );
}
