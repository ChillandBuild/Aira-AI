"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Users, X, Check, Loader2, Trash2, Pencil, Clock } from "lucide-react";
import { api, type Caller } from "@/lib/api";
import { timeAgo } from "@/lib/utils";

interface ShiftConfig {
  shift_mode: "common" | "individual";
  shift_start_hour: number;
  shift_end_hour: number;
}

interface LiveAgentStatusProps {
  callers: Caller[];
  selectedCallerId: string | null;
  onSelectCaller: (id: string | null) => void;
  statsFrom: string;
  statsTo: string;
  onStatsFromChange: (v: string) => void;
  onStatsToChange: (v: string) => void;
  onCallersChange: (updater: (prev: Caller[]) => Caller[]) => void;
  onRemoved: () => Promise<void> | void;
  shiftConfig: ShiftConfig;
  onShiftConfigSave: (config: ShiftConfig) => Promise<void>;
}

function formatHour(h: number): string {
  return `${h.toString().padStart(2, "0")}:00`;
}

const HOURS = Array.from({ length: 24 }, (_, i) => i);

export default function LiveAgentStatus({
  callers, selectedCallerId, onSelectCaller,
  statsFrom, statsTo, onStatsFromChange, onStatsToChange,
  onCallersChange, onRemoved,
  shiftConfig, onShiftConfigSave,
}: LiveAgentStatusProps) {
  const [editingAgentIdFor, setEditingAgentIdFor] = useState<string | null>(null);
  const [agentIdInputValue, setAgentIdInputValue] = useState<string>("");
  const [savingAgentId, setSavingAgentId] = useState<string | null>(null);

  // Shift config local editing state
  const [localShiftConfig, setLocalShiftConfig] = useState<ShiftConfig>(shiftConfig);
  const [savingShiftConfig, setSavingShiftConfig] = useState(false);

  // Individual mode: selected caller for shift edit
  const [individualCallerId, setIndividualCallerId] = useState<string>("");
  const [individualStart, setIndividualStart] = useState<number>(9);
  const [individualEnd, setIndividualEnd] = useState<number>(19);
  const [savingIndividual, setSavingIndividual] = useState(false);

  // Keep local config in sync when parent pushes new config
  const [lastExternalConfig, setLastExternalConfig] = useState(shiftConfig);
  if (
    shiftConfig.shift_mode !== lastExternalConfig.shift_mode ||
    shiftConfig.shift_start_hour !== lastExternalConfig.shift_start_hour ||
    shiftConfig.shift_end_hour !== lastExternalConfig.shift_end_hour
  ) {
    setLastExternalConfig(shiftConfig);
    setLocalShiftConfig(shiftConfig);
  }

  const totalAgentsCount = callers.length;
  const breakAgents = callers.filter((c) => c.status === "break");
  const activeAgents = callers.filter((c) => (c.status || "active") === "active");
  const offlineAgents = callers.filter((c) => c.status === "logged_out");

  const handleRemoveCaller = async (callerId: string, callerName: string) => {
    if (!confirm(`Remove ${callerName}?`)) return;
    try {
      await api.callers.remove(callerId);
      toast.success(`${callerName} removed`);
      await onRemoved();
      if (selectedCallerId === callerId) onSelectCaller(null);
    } catch (err) {
      console.error("Failed to remove caller:", err);
      toast.error("Failed to remove caller");
    }
  };

  const handleSaveAgentId = async (callerId: string) => {
    setSavingAgentId(callerId);
    try {
      const trimmed = agentIdInputValue.trim();
      const updated = await api.callers.update(callerId, { telecmi_agent_id: trimmed || null });
      onCallersChange((prev) =>
        prev.map((c) => (c.id === callerId ? { ...c, telecmi_agent_id: updated.telecmi_agent_id } : c))
      );
      setEditingAgentIdFor(null);
      setAgentIdInputValue("");
    } catch (err) {
      console.error("Failed to update TeleCMI agent ID:", err);
      toast.error("Failed to update TeleCMI agent ID");
    } finally {
      setSavingAgentId(null);
    }
  };

  const handleSaveShiftConfig = async () => {
    setSavingShiftConfig(true);
    try {
      await onShiftConfigSave(localShiftConfig);
    } finally {
      setSavingShiftConfig(false);
    }
  };

  const handleSaveIndividualShift = async () => {
    if (!individualCallerId) return;
    setSavingIndividual(true);
    try {
      const updated = await api.callers.update(individualCallerId, {
        shift_start_hour: individualStart,
        shift_end_hour: individualEnd,
      });
      onCallersChange((prev) =>
        prev.map((c) =>
          c.id === individualCallerId
            ? { ...c, shift_start_hour: updated.shift_start_hour, shift_end_hour: updated.shift_end_hour }
            : c
        )
      );
      toast.success("Caller shift updated");
    } catch (err) {
      console.error("Failed to update caller shift:", err);
      toast.error("Failed to update caller shift");
    } finally {
      setSavingIndividual(false);
    }
  };

  return (
    <div className="bg-surface rounded-card p-5 shadow-card ring-1 ring-[#c4c7c7]/15">
      <div className="flex items-center justify-between mb-3 flex-wrap gap-3">
        <h2 className="font-display text-sm font-bold text-tertiary flex items-center gap-2">
          <Users size={16} className="text-primary" /> Live Agent Status
        </h2>
        <div className="flex items-center gap-1.5 bg-slate-50 p-1.5 rounded-xl border border-slate-200">
          <span className="font-label text-[10px] text-slate-500 font-bold uppercase pl-1">Range:</span>
          <input type="date" value={statsFrom} onChange={(e) => onStatsFromChange(e.target.value)} className="px-1.5 py-0.5 rounded bg-white border border-slate-200 font-body text-xs text-slate-800 focus:outline-none" />
          <span className="text-slate-400 text-xs">to</span>
          <input type="date" value={statsTo} onChange={(e) => onStatsToChange(e.target.value)} className="px-1.5 py-0.5 rounded bg-white border border-slate-200 font-body text-xs text-slate-800 focus:outline-none" />
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-4 text-xs">
        <div className="flex items-center gap-2 bg-slate-50 border border-slate-200 px-3 py-1.5 rounded-lg">
          <span className="font-bold text-slate-700">{totalAgentsCount} Total</span>
        </div>
        <div className="flex items-center gap-2 bg-emerald-50 border border-emerald-200 text-emerald-700 px-3 py-1.5 rounded-lg">
          <span className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse" />
          <span className="font-bold">{activeAgents.length} Ready</span>
        </div>
        <div className="flex items-center gap-2 bg-amber-50 border border-amber-200 text-amber-700 px-3 py-1.5 rounded-lg">
          <span className="w-2 h-2 bg-amber-500 rounded-full" />
          <span className="font-bold">{breakAgents.length} On Break</span>
        </div>
        <div className="flex items-center gap-2 bg-slate-100 border border-slate-300 text-slate-600 px-3 py-1.5 rounded-lg">
          <span className="w-2 h-2 bg-slate-400 rounded-full" />
          <span className="font-bold">{offlineAgents.length} Offline</span>
        </div>
      </div>

      {/* Shift Hours config section */}
      <div className="mt-4 p-3 bg-slate-50 rounded-xl border border-slate-200">
        <div className="flex items-center gap-2 mb-2">
          <Clock size={14} className="text-slate-500" />
          <span className="font-label text-xs font-bold text-slate-700 uppercase">Shift Hours</span>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          {/* Mode toggle pill */}
          <div className="flex rounded-lg border border-slate-200 overflow-hidden">
            <button
              onClick={() => { setLocalShiftConfig((prev) => ({ ...prev, shift_mode: "common" })); setIndividualCallerId(""); }}
              className={`px-3 py-1 text-xs font-bold transition-colors ${
                localShiftConfig.shift_mode === "common"
                  ? "bg-primary text-white"
                  : "bg-white text-slate-600 hover:bg-slate-100"
              }`}
            >
              Common
            </button>
            <button
              onClick={() => setLocalShiftConfig((prev) => ({ ...prev, shift_mode: "individual" }))}
              className={`px-3 py-1 text-xs font-bold transition-colors ${
                localShiftConfig.shift_mode === "individual"
                  ? "bg-primary text-white"
                  : "bg-white text-slate-600 hover:bg-slate-100"
              }`}
            >
              Individual
            </button>
          </div>

          {/* Caller dropdown — only in individual mode */}
          {localShiftConfig.shift_mode === "individual" && (
            <select
              value={individualCallerId}
              onChange={(e) => {
                const id = e.target.value;
                setIndividualCallerId(id);
                if (id) {
                  const caller = callers.find((c) => c.id === id);
                  setIndividualStart(caller?.shift_start_hour ?? localShiftConfig.shift_start_hour);
                  setIndividualEnd(caller?.shift_end_hour ?? localShiftConfig.shift_end_hour);
                }
              }}
              className="px-2 py-1 rounded-lg bg-white border border-slate-200 text-xs text-slate-800 focus:outline-none focus:ring-1 focus:ring-primary"
            >
              <option value="">Select telecaller</option>
              {callers.map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
          )}

          {/* Start / End hour selects */}
          <div className="flex items-center gap-1.5 text-xs">
            <span className="text-slate-500 font-medium">Start:</span>
            <select
              value={localShiftConfig.shift_mode === "individual" && individualCallerId ? individualStart : localShiftConfig.shift_start_hour}
              onChange={(e) => {
                const val = parseInt(e.target.value);
                if (localShiftConfig.shift_mode === "individual" && individualCallerId) {
                  setIndividualStart(val);
                } else {
                  setLocalShiftConfig((prev) => ({ ...prev, shift_start_hour: val }));
                }
              }}
              className="px-1.5 py-0.5 rounded bg-white border border-slate-200 text-xs text-slate-800 focus:outline-none focus:ring-1 focus:ring-primary"
            >
              {HOURS.map((h) => (
                <option key={h} value={h}>{formatHour(h)}</option>
              ))}
            </select>
            <span className="text-slate-500 font-medium ml-1">End:</span>
            <select
              value={localShiftConfig.shift_mode === "individual" && individualCallerId ? individualEnd : localShiftConfig.shift_end_hour}
              onChange={(e) => {
                const val = parseInt(e.target.value);
                if (localShiftConfig.shift_mode === "individual" && individualCallerId) {
                  setIndividualEnd(val);
                } else {
                  setLocalShiftConfig((prev) => ({ ...prev, shift_end_hour: val }));
                }
              }}
              className="px-1.5 py-0.5 rounded bg-white border border-slate-200 text-xs text-slate-800 focus:outline-none focus:ring-1 focus:ring-primary"
            >
              {HOURS.map((h) => (
                <option key={h} value={h}>{formatHour(h)}</option>
              ))}
            </select>
          </div>

          {/* Single Save button */}
          <button
            onClick={localShiftConfig.shift_mode === "individual" && individualCallerId ? handleSaveIndividualShift : handleSaveShiftConfig}
            disabled={savingShiftConfig || savingIndividual}
            className="flex items-center gap-1 px-3 py-1 bg-primary text-white rounded-lg hover:bg-primary/95 disabled:opacity-50 font-label text-xs font-semibold transition-colors"
          >
            {(savingShiftConfig || savingIndividual) ? <Loader2 className="animate-spin" size={12} /> : <Check size={12} />}
            Save
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-4 gap-3 mt-4">
        {callers.map((c) => {
          const st = c.status || "active";
          const statusColor = st === "active" ? "text-emerald-700 bg-emerald-50 border-emerald-200" : st === "break" ? "text-amber-700 bg-amber-50 border-amber-200" : "text-slate-500 bg-slate-100 border-slate-200";
          const isSelected = selectedCallerId === c.id;

          // Effective shift for this caller
          const effectiveStart = shiftConfig.shift_mode === "individual" && c.shift_start_hour != null
            ? c.shift_start_hour
            : shiftConfig.shift_start_hour;
          const effectiveEnd = shiftConfig.shift_mode === "individual" && c.shift_end_hour != null
            ? c.shift_end_hour
            : shiftConfig.shift_end_hour;

          const nowIST = new Date(new Date().toLocaleString("en-US", { timeZone: "Asia/Kolkata" }));
          const currentHour = nowIST.getHours();
          const isOutsideShift = currentHour < effectiveStart || currentHour >= effectiveEnd;

          return (
            <div
              key={c.id}
              onClick={() => onSelectCaller(selectedCallerId === c.id ? null : c.id)}
              className={`relative flex items-center justify-between p-2.5 bg-surface-low rounded-xl border text-xs cursor-pointer transition-all ${
                isSelected ? "ring-2 ring-primary border-primary/40 bg-primary/5" : "border-slate-100 hover:border-slate-200"
              }`}
            >
              <button
                onClick={(e) => { e.stopPropagation(); handleRemoveCaller(c.id, c.name); }}
                className="absolute top-1 right-1 p-1 text-slate-300 hover:text-red-500 hover:bg-red-50 rounded-md transition-colors"
                title={`Remove ${c.name}`}
              >
                <Trash2 size={11} />
              </button>
              <div className="truncate pr-5">
                <span className="font-bold text-slate-800">{c.name}</span>
                {c.status_changed_at && (
                  <span className="block text-[10px] text-slate-400 font-medium">Since {timeAgo(c.status_changed_at)}</span>
                )}
                <div className="flex items-center gap-1.5 text-xs text-slate-500 mt-0.5">
                  <span>{c.phone || "—"}</span>
                  <span className="text-slate-300">&middot;</span>
                  {editingAgentIdFor === c.id ? (
                    <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                      <input
                        type="text"
                        value={agentIdInputValue}
                        onChange={(e) => setAgentIdInputValue(e.target.value)}
                        onClick={(e) => e.stopPropagation()}
                        autoFocus
                        className="w-20 px-1 py-0.5 rounded bg-white border border-slate-200 text-[11px] text-slate-800 focus:outline-none focus:ring-1 focus:ring-primary"
                      />
                      <button
                        onClick={(e) => { e.stopPropagation(); handleSaveAgentId(c.id); }}
                        disabled={savingAgentId === c.id}
                        className="p-0.5 text-emerald-600 hover:bg-emerald-50 rounded border border-emerald-200"
                        title="Save Agent ID"
                      >
                        {savingAgentId === c.id ? <Loader2 className="animate-spin" size={10} /> : <Check size={10} />}
                      </button>
                      <button
                        onClick={(e) => { e.stopPropagation(); setEditingAgentIdFor(null); setAgentIdInputValue(""); }}
                        disabled={savingAgentId === c.id}
                        className="p-0.5 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded border border-slate-200"
                        title="Cancel"
                      >
                        <X size={10} />
                      </button>
                    </div>
                  ) : (
                    <span className="flex items-center gap-1">
                      {c.telecmi_agent_id || "—"}
                      <button
                        onClick={(e) => { e.stopPropagation(); setEditingAgentIdFor(c.id); setAgentIdInputValue(c.telecmi_agent_id || ""); }}
                        className="p-0.5 text-slate-300 hover:text-slate-600 hover:bg-slate-100 rounded"
                        title="Edit TeleCMI Agent ID"
                      >
                        <Pencil size={9} />
                      </button>
                    </span>
                  )}
                </div>
                {/* Shift time display (read-only) */}
                <div className="flex items-center gap-1 mt-0.5">
                  <Clock size={9} className={isOutsideShift ? "text-amber-500" : "text-slate-400"} />
                  <span className={`text-[10px] font-medium ${isOutsideShift ? "text-amber-500" : "text-slate-400"}`}>
                    {formatHour(effectiveStart)}&ndash;{formatHour(effectiveEnd)}
                  </span>
                </div>
              </div>
              <span className={`px-2 py-0.5 rounded-full border text-[10px] font-bold shrink-0 ${statusColor}`}>
                {st === "logged_out" ? "Offline" : st}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
