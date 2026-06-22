"use client";
import { useState, useEffect, useRef, useCallback } from "react";
import { api } from "@/lib/api";
import type { Caller } from "@/lib/api";
import { UserCheck, ChevronDown, Loader2, UserX } from "lucide-react";
import { createPortal } from "react-dom";

interface AssignButtonProps {
  leadId: string;
  currentAssignedTo: string | null | undefined;
  callers?: Caller[];
  onAssigned?: (callerId: string | null) => void;
}

export function AssignButton({ leadId, currentAssignedTo, callers: callersProp, onAssigned }: AssignButtonProps) {
  const [callers, setCallers] = useState<Caller[]>(callersProp ?? []);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [fetchingCallers, setFetchingCallers] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [assignedId, setAssignedId] = useState(currentAssignedTo ?? null);
  const [dropdownPos, setDropdownPos] = useState({ top: 0, left: 0, width: 0 });

  const buttonRef = useRef<HTMLButtonElement>(null);

  // Calculate dropdown position — flip upward if near bottom of viewport
  const updatePos = useCallback(() => {
    if (!buttonRef.current) return;
    const rect = buttonRef.current.getBoundingClientRect();
    const dropdownHeight = 280; // estimated max height
    const spaceBelow = window.innerHeight - rect.bottom;
    const flipUp = spaceBelow < dropdownHeight && rect.top > dropdownHeight;

    setDropdownPos({
      top: flipUp ? rect.top - dropdownHeight - 6 : rect.bottom + 6,
      left: rect.right - 220,
      width: 220,
    });
  }, []);

  function toggleOpen() {
    if (!open) updatePos();
    setOpen((o) => !o);
    setError(null);
  }

  // Close on outside click or scroll
  useEffect(() => {
    if (!open) return;
    function handleClose(e: MouseEvent | Event) {
      if (e instanceof MouseEvent && buttonRef.current?.contains(e.target as Node)) return;
      setOpen(false);
    }
    document.addEventListener("mousedown", handleClose);
    window.addEventListener("scroll", handleClose, true);
    return () => {
      document.removeEventListener("mousedown", handleClose);
      window.removeEventListener("scroll", handleClose, true);
    };
  }, [open]);

  // Sync if parent passes updated callers list
  useEffect(() => {
    if (callersProp) setCallers(callersProp);
  }, [callersProp]);

  // Fetch callers on dropdown open only if not pre-loaded
  useEffect(() => {
    if (!open || callers.length > 0) return;
    setFetchingCallers(true);
    api.callers
      .list()
      .then((res) => setCallers((res.data || []).filter((c) => c.active)))
      .catch(() => setError("Failed to load callers"))
      .finally(() => setFetchingCallers(false));
  }, [open, callers.length]);

  const assignedCaller = callers.find((c) => c.id === assignedId);

  async function assign(callerId: string | null) {
    const originalAssignedId = assignedId;
    // Optimistic UI updates
    setAssignedId(callerId);
    onAssigned?.(callerId);
    setOpen(false);
    setError(null);
    setLoading(true);

    try {
      const { getAuthHeaders, API_URL } = await import("@/lib/api");
      const auth = await getAuthHeaders();
      const res = await fetch(`${API_URL}/api/v1/leads/${leadId}/assign`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", ...auth },
        body: JSON.stringify({ caller_id: callerId }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `Error ${res.status}`);
      }
    } catch (err) {
      // Rollback
      setAssignedId(originalAssignedId);
      onAssigned?.(originalAssignedId);
      setError(err instanceof Error ? err.message : "Assign failed");
      setOpen(true);
    } finally {
      setLoading(false);
    }
  }

  const dropdown = open ? (
    <div
      style={{
        position: "fixed",
        top: dropdownPos.top,
        left: Math.max(8, dropdownPos.left),
        width: 230,
        maxHeight: 280,
        zIndex: 9999,
      }}
      className="bg-white border border-gray-200 rounded-xl shadow-2xl py-1 overflow-y-auto"
      onMouseDown={(e) => e.stopPropagation()}
    >
      <p className="px-3 py-2 text-[10px] font-bold text-gray-400 uppercase tracking-widest border-b border-gray-100 sticky top-0 bg-white">
        Assign to telecaller
      </p>

      {fetchingCallers ? (
        <div className="flex items-center gap-2 px-4 py-3 text-xs text-gray-400">
          <Loader2 size={12} className="animate-spin" /> Loading…
        </div>
      ) : callers.length === 0 ? (
        <p className="px-4 py-3 text-xs text-gray-400">No active callers</p>
      ) : (
        <>
          {/* Unassign row — only if already assigned */}
          {assignedId && (
            <button
              onClick={() => assign(null)}
              disabled={loading}
              className="w-full flex items-center gap-2 px-4 py-2 text-xs text-red-500 hover:bg-red-50 transition-colors disabled:opacity-50"
            >
              <UserX size={12} /> Unassign
            </button>
          )}

          {/* Caller rows */}
          {callers.map((c) => (
            <button
              key={c.id}
              onClick={() => assign(c.id)}
              disabled={loading || c.id === assignedId}
              className={`w-full flex items-center justify-between px-4 py-2.5 text-sm transition-colors ${
                c.id === assignedId
                  ? "bg-teal-50 text-teal-700 font-semibold cursor-default"
                  : "text-gray-700 hover:bg-gray-50"
              }`}
            >
              <span className="flex items-center gap-2">
                {c.id === assignedId && <span className="text-teal-500 text-xs">✓</span>}
                {c.name}
              </span>
              {c.overall_score != null && (
                <span className="text-[11px] text-gray-400">⭐ {Number(c.overall_score).toFixed(1)}</span>
              )}
            </button>
          ))}
        </>
      )}

      {loading && (
        <div className="flex items-center gap-2 px-4 py-2 text-xs text-gray-400 border-t border-gray-100">
          <Loader2 size={11} className="animate-spin" /> Saving…
        </div>
      )}
      {error && (
        <p className="px-4 py-2 text-xs text-red-500 border-t border-gray-100">{error}</p>
      )}
    </div>
  ) : null;

  return (
    <>
      <button
        ref={buttonRef}
        onClick={toggleOpen}
        className={`flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-lg font-semibold transition-colors whitespace-nowrap ${
          assignedId
            ? "bg-teal-50 text-teal-700 hover:bg-teal-100 ring-1 ring-teal-200"
            : "bg-gray-100 text-gray-500 hover:bg-gray-200"
        }`}
      >
        <UserCheck size={12} />
        {assignedCaller?.name ?? (assignedId ? "Assigned" : "Assign")}
        <ChevronDown size={10} className={`transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {/* Portal: renders outside the table so overflow:hidden can't clip it */}
      {typeof document !== "undefined" && dropdown && createPortal(dropdown, document.body)}
    </>
  );
}
