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
  adminCaller: Caller | null;
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
  callingProvider: "telecmi" | "sim_basic";
}

function formatHour(h: number): string {
  return `${h.toString().padStart(2, "0")}:00`;
}

const HOURS = Array.from({ length: 24 }, (_, i) => i);

function AdminCallerCard({
  caller, editingAgentIdFor, agentIdInputValue, savingAgentId,
  onEditAgentId, onSaveAgentId, onCancelEditAgentId, onAgentIdInputChange,
  callingProvider,
}: {
  caller: Caller;
  editingAgentIdFor: string | null;
  agentIdInputValue: string;
  savingAgentId: string | null;
  onEditAgentId: (id: string, current: string | null) => void;
  onSaveAgentId: (id: string) => Promise<void>;
  onCancelEditAgentId: () => void;
  onAgentIdInputChange: (v: string) => void;
  callingProvider: "telecmi" | "sim_basic";
}) {
  const [editingPhone, setEditingPhone] = useState(false);
  const [phoneInput, setPhoneInput] = useState(caller.phone || "");
  const [savingPhone, setSavingPhone] = useState(false);

  const handleSavePhone = async () => {
    setSavingPhone(true);
    try {
      const trimmed = phoneInput.trim() || undefined;
      await api.callers.update(caller.id, { phone: trimmed });
      caller.phone = trimmed ?? null;
      setEditingPhone(false);
    } catch {
      toast.error("Failed to update phone");
    } finally {
      setSavingPhone(false);
    }
  };

  const isTelecmi = callingProvider === "telecmi";
  const needsSetup = isTelecmi
    ? !caller.phone || !caller.telecmi_agent_id
    : !caller.phone;

  return (
    <div className="max-w-sm">
      <div className="relative p-3 bg-gradient-to-r from-primary/5 to-transparent rounded-xl border border-primary/20 text-xs">
        <div className="flex items-center justify-between mb-2">
          <span className="font-bold text-[#292524] text-sm">{caller.name}</span>
          <span className="px-2 py-0.5 rounded-full border text-[10px] font-bold text-primary bg-primary/10 border-primary/20">
            Owner
          </span>
        </div>
        {needsSetup && (
          <p className="text-[10px] text-amber-600 bg-amber-50 border border-amber-200 rounded-lg px-2 py-1 mb-2 font-medium">
            {isTelecmi
              ? "Set your phone and TeleCMI Agent ID to enable click-to-call"
              : "Set your phone number to enable SIM calling"}
          </p>
        )}
        <div className="space-y-1.5">
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-bold text-[#78716c] uppercase w-16 shrink-0">Phone</span>
            {editingPhone ? (
              <div className="flex items-center gap-1">
                <input
                  type="tel"
                  value={phoneInput}
                  onChange={(e) => setPhoneInput(e.target.value)}
                  autoFocus
                  placeholder="+919876543210"
                  className="w-32 px-1.5 py-0.5 rounded bg-white border border-[#e8e3db] text-[11px] text-[#292524] focus:outline-none focus:ring-1 focus:ring-primary"
                />
                <button onClick={handleSavePhone} disabled={savingPhone}
                  className="p-0.5 text-emerald-600 hover:bg-emerald-50 rounded border border-emerald-200">
                  {savingPhone ? <Loader2 className="animate-spin" size={10} /> : <Check size={10} />}
                </button>
                <button onClick={() => { setEditingPhone(false); setPhoneInput(caller.phone || ""); }}
                  className="p-0.5 text-[#a8a29e] hover:text-red-500 hover:bg-red-50 rounded border border-[#e8e3db]">
                  <X size={10} />
                </button>
              </div>
            ) : (
              <span className="flex items-center gap-1 text-[#292524]">
                {caller.phone || <span className="text-[#a8a29e] italic">Not set</span>}
                <button onClick={() => { setEditingPhone(true); setPhoneInput(caller.phone || ""); }}
                  className="p-0.5 text-[#d6cfc9] hover:text-[#57534e] hover:bg-[#f0ece4] rounded"
                  title="Edit phone">
                  <Pencil size={9} />
                </button>
              </span>
            )}
          </div>
          {isTelecmi && (
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-bold text-[#78716c] uppercase w-16 shrink-0">Agent ID</span>
            {editingAgentIdFor === caller.id ? (
              <div className="flex items-center gap-1">
                <input
                  type="text"
                  value={agentIdInputValue}
                  onChange={(e) => onAgentIdInputChange(e.target.value)}
                  autoFocus
                  placeholder="e.g. 101_33335739"
                  className="w-28 px-1.5 py-0.5 rounded bg-white border border-[#e8e3db] text-[11px] text-[#292524] focus:outline-none focus:ring-1 focus:ring-primary"
                />
                <button onClick={() => onSaveAgentId(caller.id)} disabled={savingAgentId === caller.id}
                  className="p-0.5 text-emerald-600 hover:bg-emerald-50 rounded border border-emerald-200">
                  {savingAgentId === caller.id ? <Loader2 className="animate-spin" size={10} /> : <Check size={10} />}
                </button>
                <button onClick={onCancelEditAgentId} disabled={savingAgentId === caller.id}
                  className="p-0.5 text-[#a8a29e] hover:text-red-500 hover:bg-red-50 rounded border border-[#e8e3db]">
                  <X size={10} />
                </button>
              </div>
            ) : (
              <span className="flex items-center gap-1 text-[#292524]">
                {caller.telecmi_agent_id || <span className="text-[#a8a29e] italic">Not set</span>}
                <button onClick={() => onEditAgentId(caller.id, caller.telecmi_agent_id || null)}
                  className="p-0.5 text-[#d6cfc9] hover:text-[#57534e] hover:bg-[#f0ece4] rounded"
                  title="Edit TeleCMI agent ID">
                  <Pencil size={9} />
                </button>
              </span>
            )}
          </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function LiveAgentStatus({
  callers, adminCaller, selectedCallerId, onSelectCaller,
  statsFrom, statsTo, onStatsFromChange, onStatsToChange,
  onCallersChange, onRemoved,
  shiftConfig, onShiftConfigSave,
  callingProvider,
}: LiveAgentStatusProps) {
  const [editingAgentIdFor, setEditingAgentIdFor] = useState<string | null>(null);
  const [agentIdInputValue, setAgentIdInputValue] = useState<string>("");
  const [savingAgentId, setSavingAgentId] = useState<string | null>(null);
  const [editingPhoneFor, setEditingPhoneFor] = useState<string | null>(null);
  const [phoneInputValue, setPhoneInputValue] = useState<string>("");
  const [savingPhoneFor, setSavingPhoneFor] = useState<string | null>(null);

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
      const trimmedId = agentIdInputValue.trim();
      const updated = await api.callers.update(callerId, { telecmi_agent_id: trimmedId || null });
      onCallersChange((prev) =>
        prev.map((c) =>
          c.id === callerId
            ? { ...c, telecmi_agent_id: updated.telecmi_agent_id, has_telecmi_agent_password: updated.has_telecmi_agent_password }
            : c
        )
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

  const handleSavePhone = async (callerId: string) => {
    setSavingPhoneFor(callerId);
    try {
      const trimmedPhone = phoneInputValue.trim();
      const updated = await api.callers.update(callerId, { phone: trimmedPhone || undefined });
      onCallersChange((prev) =>
        prev.map((c) =>
          c.id === callerId
            ? { ...c, phone: updated.phone }
            : c
        )
      );
      setEditingPhoneFor(null);
      setPhoneInputValue("");
    } catch (err) {
      console.error("Failed to update caller phone:", err);
      toast.error("Failed to update phone number");
    } finally {
      setSavingPhoneFor(null);
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
      await onShiftConfigSave(localShiftConfig);
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
        <h2 className="font-display text-sm font-bold text-primary flex items-center gap-2">
          <Users size={16} className="text-primary" /> Live Agent Status
        </h2>
        <div className="flex items-center gap-1.5 bg-[#faf8f5] p-1.5 rounded-xl border border-[#e8e3db]">
          <span className="font-label text-[10px] text-[#78716c] font-bold uppercase pl-1">Range:</span>
          <input type="date" value={statsFrom} onChange={(e) => onStatsFromChange(e.target.value)} className="px-1.5 py-0.5 rounded bg-white border border-[#e8e3db] font-body text-xs text-[#292524] focus:outline-none" />
          <span className="text-[#a8a29e] text-xs">to</span>
          <input type="date" value={statsTo} onChange={(e) => onStatsToChange(e.target.value)} className="px-1.5 py-0.5 rounded bg-white border border-[#e8e3db] font-body text-xs text-[#292524] focus:outline-none" />
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-4 text-xs">
        <div className="flex items-center gap-2 bg-[#faf8f5] border border-[#e8e3db] px-3 py-1.5 rounded-lg">
          <span className="font-bold text-[#44403c]">{totalAgentsCount} Total</span>
        </div>
        <div className="flex items-center gap-2 bg-emerald-50 border border-emerald-200 text-emerald-700 px-3 py-1.5 rounded-lg">
          <span className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse" />
          <span className="font-bold">{activeAgents.length} Ready</span>
        </div>
        <div className="flex items-center gap-2 bg-amber-50 border border-amber-200 text-amber-700 px-3 py-1.5 rounded-lg">
          <span className="w-2 h-2 bg-amber-500 rounded-full" />
          <span className="font-bold">{breakAgents.length} On Break</span>
        </div>
        <div className="flex items-center gap-2 bg-[#f0ece4] border border-[#d6cfc9] text-[#57534e] px-3 py-1.5 rounded-lg">
          <span className="w-2 h-2 bg-[#a8a29e] rounded-full" />
          <span className="font-bold">{offlineAgents.length} Offline</span>
        </div>
      </div>

      {/* Shift Hours config section */}
      <div className="mt-4 p-3 bg-[#faf8f5] rounded-xl border border-[#e8e3db]">
        <div className="flex items-center gap-2 mb-2">
          <Clock size={14} className="text-[#78716c]" />
          <span className="font-label text-xs font-bold text-[#44403c] uppercase">Shift Hours</span>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          {/* Mode toggle pill */}
          <div className="flex rounded-lg border border-[#e8e3db] overflow-hidden">
            <button
              onClick={() => { setLocalShiftConfig((prev) => ({ ...prev, shift_mode: "common" })); setIndividualCallerId(""); }}
              className={`px-3 py-1 text-xs font-bold transition-colors ${
                localShiftConfig.shift_mode === "common"
                  ? "bg-primary text-white"
                  : "bg-white text-[#57534e] hover:bg-[#f0ece4]"
              }`}
            >
              Common
            </button>
            <button
              onClick={() => setLocalShiftConfig((prev) => ({ ...prev, shift_mode: "individual" }))}
              className={`px-3 py-1 text-xs font-bold transition-colors ${
                localShiftConfig.shift_mode === "individual"
                  ? "bg-primary text-white"
                  : "bg-white text-[#57534e] hover:bg-[#f0ece4]"
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
              className="px-2 py-1 rounded-lg bg-white border border-[#e8e3db] text-xs text-[#292524] focus:outline-none focus:ring-1 focus:ring-primary"
            >
              <option value="">Select telecaller</option>
              {callers.map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
          )}

          {/* Start / End hour selects */}
          <div className="flex items-center gap-1.5 text-xs">
            <span className="text-[#78716c] font-medium">Start:</span>
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
              className="px-1.5 py-0.5 rounded bg-white border border-[#e8e3db] text-xs text-[#292524] focus:outline-none focus:ring-1 focus:ring-primary"
            >
              {HOURS.map((h) => (
                <option key={h} value={h}>{formatHour(h)}</option>
              ))}
            </select>
            <span className="text-[#78716c] font-medium ml-1">End:</span>
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
              className="px-1.5 py-0.5 rounded bg-white border border-[#e8e3db] text-xs text-[#292524] focus:outline-none focus:ring-1 focus:ring-primary"
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

      {/* Admin caller card — separate from team, non-deletable */}
      {adminCaller && (
        <div className="mt-4 mb-1">
          <span className="font-label text-[10px] font-bold text-[#78716c] uppercase tracking-wide">Admin</span>
          <div className="mt-1.5">
            <AdminCallerCard
              caller={adminCaller}
              editingAgentIdFor={editingAgentIdFor}
              agentIdInputValue={agentIdInputValue}
              savingAgentId={savingAgentId}
              onEditAgentId={(id, current) => { setEditingAgentIdFor(id); setAgentIdInputValue(current || ""); }}
              onSaveAgentId={handleSaveAgentId}
              onCancelEditAgentId={() => { setEditingAgentIdFor(null); setAgentIdInputValue(""); }}
              onAgentIdInputChange={setAgentIdInputValue}
              callingProvider={callingProvider}
            />
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-4 gap-3 mt-4">
        {callers.map((c) => {
          const st = c.status || "active";
          const statusColor = st === "active" ? "text-emerald-700 bg-emerald-50 border-emerald-200" : st === "break" ? "text-amber-700 bg-amber-50 border-amber-200" : "text-[#78716c] bg-[#f0ece4] border-[#e8e3db]";
          const isSelected = selectedCallerId === c.id;

          // Effective shift for this caller
          const effectiveStart = localShiftConfig.shift_mode === "individual" && c.shift_start_hour != null
            ? c.shift_start_hour
            : localShiftConfig.shift_start_hour;
          const effectiveEnd = localShiftConfig.shift_mode === "individual" && c.shift_end_hour != null
            ? c.shift_end_hour
            : localShiftConfig.shift_end_hour;

          const nowIST = new Date(new Date().toLocaleString("en-US", { timeZone: "Asia/Kolkata" }));
          const currentHour = nowIST.getHours();
          const isOutsideShift = currentHour < effectiveStart || currentHour >= effectiveEnd;

          return (
            <div
              key={c.id}
              onClick={() => onSelectCaller(selectedCallerId === c.id ? null : c.id)}
              className={`relative flex items-center justify-between p-2.5 bg-surface-low rounded-xl border text-xs cursor-pointer transition-all ${
                isSelected ? "ring-2 ring-primary border-primary/40 bg-primary/5" : "border-[#f0ece4] hover:border-[#e8e3db]"
              }`}
            >
              <button
                onClick={(e) => { e.stopPropagation(); handleRemoveCaller(c.id, c.name); }}
                className="absolute top-1 right-1 p-1 text-[#d6cfc9] hover:text-red-500 hover:bg-red-50 rounded-md transition-colors"
                title={`Remove ${c.name}`}
              >
                <Trash2 size={11} />
              </button>
              <div className="truncate pr-5">
                <span className="font-bold text-[#292524]">{c.name}</span>
                {c.status_changed_at && (
                  <span className="block text-[10px] text-[#a8a29e] font-medium">Since {timeAgo(c.status_changed_at)}</span>
                )}
                <div className="flex items-center gap-1.5 text-xs text-[#78716c] mt-0.5">
                  {editingPhoneFor === c.id ? (
                    <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                      <input
                        type="tel"
                        value={phoneInputValue}
                        onChange={(e) => setPhoneInputValue(e.target.value)}
                        onClick={(e) => e.stopPropagation()}
                        autoFocus
                        placeholder="+919876543210"
                        className="w-28 px-1 py-0.5 rounded bg-white border border-[#e8e3db] text-[11px] text-[#292524] focus:outline-none focus:ring-1 focus:ring-primary"
                      />
                      <button
                        onClick={(e) => { e.stopPropagation(); handleSavePhone(c.id); }}
                        disabled={savingPhoneFor === c.id}
                        className="p-0.5 text-emerald-600 hover:bg-emerald-50 rounded border border-emerald-200"
                        title="Save phone number"
                      >
                        {savingPhoneFor === c.id ? <Loader2 className="animate-spin" size={10} /> : <Check size={10} />}
                      </button>
                      <button
                        onClick={(e) => { e.stopPropagation(); setEditingPhoneFor(null); setPhoneInputValue(""); }}
                        disabled={savingPhoneFor === c.id}
                        className="p-0.5 text-[#a8a29e] hover:text-red-500 hover:bg-red-50 rounded border border-[#e8e3db]"
                        title="Cancel"
                      >
                        <X size={10} />
                      </button>
                    </div>
                  ) : (
                    <span className="flex items-center gap-1">
                      {c.phone || "—"}
                      <button
                        onClick={(e) => { e.stopPropagation(); setEditingPhoneFor(c.id); setPhoneInputValue(c.phone || ""); }}
                        className="p-0.5 text-[#d6cfc9] hover:text-[#57534e] hover:bg-[#f0ece4] rounded"
                        title="Edit phone number"
                      >
                        <Pencil size={9} />
                      </button>
                    </span>
                  )}
                  {callingProvider === "telecmi" && <span className="text-[#d6cfc9]">&middot;</span>}
                  {callingProvider === "telecmi" && (editingAgentIdFor === c.id ? (
                    <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                      <input
                        type="text"
                        value={agentIdInputValue}
                        onChange={(e) => setAgentIdInputValue(e.target.value)}
                        onClick={(e) => e.stopPropagation()}
                        autoFocus
                        placeholder="agent id"
                        className="w-20 px-1 py-0.5 rounded bg-white border border-[#e8e3db] text-[11px] text-[#292524] focus:outline-none focus:ring-1 focus:ring-primary"
                      />
                      <button
                        onClick={(e) => { e.stopPropagation(); handleSaveAgentId(c.id); }}
                        disabled={savingAgentId === c.id}
                        className="p-0.5 text-emerald-600 hover:bg-emerald-50 rounded border border-emerald-200"
                        title="Save TeleCMI agent ID"
                      >
                        {savingAgentId === c.id ? <Loader2 className="animate-spin" size={10} /> : <Check size={10} />}
                      </button>
                      <button
                        onClick={(e) => { e.stopPropagation(); setEditingAgentIdFor(null); setAgentIdInputValue(""); }}
                        disabled={savingAgentId === c.id}
                        className="p-0.5 text-[#a8a29e] hover:text-red-500 hover:bg-red-50 rounded border border-[#e8e3db]"
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
                        className="p-0.5 text-[#d6cfc9] hover:text-[#57534e] hover:bg-[#f0ece4] rounded"
                        title="Edit TeleCMI agent ID"
                      >
                        <Pencil size={9} />
                      </button>
                    </span>
                  ))}
                </div>
                {/* Shift time display (read-only) */}
                <div className="flex items-center gap-1 mt-0.5">
                  <Clock size={9} className={isOutsideShift ? "text-amber-500" : "text-[#a8a29e]"} />
                  <span className={`text-[10px] font-medium ${isOutsideShift ? "text-amber-500" : "text-[#a8a29e]"}`}>
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
