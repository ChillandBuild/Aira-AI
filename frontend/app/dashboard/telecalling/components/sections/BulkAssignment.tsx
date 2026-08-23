"use client";

import { useEffect, useState, useCallback } from "react";
import { toast } from "sonner";
import { Users, Search, Loader2 } from "lucide-react";
import { api, type Caller, type Lead } from "@/lib/api";
import { formatPhone } from "@/lib/utils";
import { CheckTick } from "@/components/ui/controls";

interface BulkAssignmentProps {
  callers: Caller[];
}

export default function BulkAssignment({ callers }: BulkAssignmentProps) {
  const [leadList, setLeadList] = useState<Lead[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedLeadIds, setSelectedLeadIds] = useState<string[]>([]);
  const [bulkAssigneeId, setBulkAssigneeId] = useState<string>("");
  const [assigning, setAssigning] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.leads.list({ limit: 50 });
      setLeadList(res);
    } catch (err) {
      console.error("Failed to load leads for assignment:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const filteredLeads = leadList.filter((l) => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    return (
      (l.name && l.name.toLowerCase().includes(q)) ||
      (l.phone && l.phone.includes(q)) ||
      (l.segment && l.segment.toLowerCase().includes(q))
    );
  });

  const toggleSelectLead = (leadId: string) => {
    setSelectedLeadIds((prev) =>
      prev.includes(leadId) ? prev.filter((id) => id !== leadId) : [...prev, leadId]
    );
  };

  const toggleSelectAll = () => {
    const visibleIds = filteredLeads.map((l) => l.id);
    const allSelected = visibleIds.every((id) => selectedLeadIds.includes(id));
    if (allSelected) {
      setSelectedLeadIds((prev) => prev.filter((id) => !visibleIds.includes(id)));
    } else {
      setSelectedLeadIds((prev) => Array.from(new Set([...prev, ...visibleIds])));
    }
  };

  const handleBulkAssign = async () => {
    if (selectedLeadIds.length === 0 || !bulkAssigneeId) return;
    setAssigning(true);
    try {
      const res = await api.leads.bulkAssign(selectedLeadIds, bulkAssigneeId);
      toast.success(`Successfully assigned ${res.updated || selectedLeadIds.length} leads`);
      setSelectedLeadIds([]);
      setBulkAssigneeId("");
      load();
    } catch (err) {
      console.error("Failed bulk assign:", err);
      toast.error("Failed to bulk assign leads");
    } finally {
      setAssigning(false);
    }
  };

  return (
    <div className="bg-surface rounded-card p-6 shadow-card ring-1 ring-[#c4c7c7]/15 flex flex-col">
      <h2 className="font-display text-base font-bold text-primary mb-1 flex items-center gap-2">
        <Users size={16} className="text-sky-600" /> Lead Bulk Assignment
      </h2>
      <p className="font-label text-xs text-on-surface-muted mb-4">Select multiple leads to dispatch or hand off to another agent queue.</p>

      <div className="flex items-center gap-2 bg-[#faf8f5] border border-[#e8e3db] p-2 rounded-xl mb-4 text-xs">
        <Search size={14} className="text-[#a8a29e] shrink-0 ml-1" />
        <input
          type="text"
          placeholder="Search leads name, phone, segment..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="bg-transparent w-full focus:outline-none placeholder-[#a8a29e]"
        />
      </div>

      <div className="flex-1 overflow-y-auto max-h-[350px] border border-[#f0ece4] rounded-2xl pr-1 mb-4">
        {loading ? (
          <div className="py-12 flex flex-col items-center justify-center">
            <Loader2 className="animate-spin text-[#a8a29e]" size={20} />
          </div>
        ) : filteredLeads.length === 0 ? (
          <p className="text-xs text-[#a8a29e] text-center py-12">No leads matching search query.</p>
        ) : (
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="border-b border-[#f0ece4] bg-[#faf8f5]/50 sticky top-0 font-label text-[10px] text-[#a8a29e] uppercase font-bold">
                <th className="py-2.5 px-3 w-8">
                  <CheckTick
                    checked={filteredLeads.length > 0 && filteredLeads.every((l) => selectedLeadIds.includes(l.id))}
                    indeterminate={
                      selectedLeadIds.length > 0 &&
                      !filteredLeads.every((l) => selectedLeadIds.includes(l.id))
                    }
                    onChange={() => toggleSelectAll()}
                    size="sm"
                    aria-label="Select all leads"
                  />
                </th>
                <th className="py-2.5 px-2">Lead</th>
                <th className="py-2.5 px-2">Phone</th>
                <th className="py-2.5 px-2">Seg</th>
                <th className="py-2.5 px-2">Status</th>
                <th className="py-2.5 px-2">Assigned To</th>
              </tr>
            </thead>
            <tbody>
              {filteredLeads.map((lead) => {
                const isSelected = selectedLeadIds.includes(lead.id);
                const assignedCaller = callers.find((c) => c.id === lead.assigned_to);
                return (
                  <tr key={lead.id} className="border-b border-[#f0ece4] hover:bg-[#faf8f5]/20 transition-colors">
                    <td className="py-2 px-3">
                      <CheckTick
                        checked={isSelected}
                        onChange={() => toggleSelectLead(lead.id)}
                        size="sm"
                        aria-label={`Select ${lead.name || "lead"}`}
                      />
                    </td>
                    <td className="py-2 px-2 font-bold text-[#292524]">{lead.name || "Unnamed"}</td>
                    <td className="py-2 px-2 text-[#78716c] font-medium">{formatPhone(lead.phone)}</td>
                    <td className="py-2 px-2">
                      <span className="bg-[#f0ece4] px-1 py-0.5 rounded font-black text-[9px] uppercase">{lead.segment || "—"}</span>
                    </td>
                    <td className="py-2 px-2">
                      <span className={`px-1.5 py-0.5 rounded font-label text-[9px] font-black uppercase ${
                        lead.call_status === "converted" ? "bg-emerald-100 text-emerald-800" :
                        lead.call_status === "dnc" ? "bg-red-100 text-red-800" :
                        lead.call_status === "unreachable" ? "bg-rose-100 text-rose-800" :
                        "bg-[#f0ece4] text-[#57534e]"
                      }`}>
                        {lead.call_status || "new"}
                        {lead.do_not_call ? " (DNC)" : ""}
                      </span>
                    </td>
                    <td className="py-2 px-2 text-[#78716c] font-semibold truncate">
                      {assignedCaller ? assignedCaller.name : <span className="text-amber-500">Unassigned</span>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      <div className="flex items-center gap-3 bg-[#faf8f5] p-4 rounded-2xl border border-[#e8e3db] mt-auto">
        <div className="flex-1">
          <span className="font-label text-[10px] text-[#a8a29e] uppercase font-extrabold block">Reassign To:</span>
          <select
            value={bulkAssigneeId}
            onChange={(e) => setBulkAssigneeId(e.target.value)}
            className="w-full bg-white border border-[#e8e3db] px-2 py-1.5 rounded-lg text-xs font-semibold focus:outline-none focus:ring-1 focus:ring-primary mt-1"
          >
            <option value="">Select Caller...</option>
            {callers.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>
        <div className="shrink-0 pt-4">
          <button
            onClick={handleBulkAssign}
            disabled={assigning || selectedLeadIds.length === 0 || !bulkAssigneeId}
            className="flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-xl hover:bg-primary/95 disabled:opacity-50 font-label text-xs font-bold transition-all shadow-sm"
          >
            {assigning ? <Loader2 className="animate-spin" size={12} /> : null}
            Assign ({selectedLeadIds.length})
          </button>
        </div>
      </div>
    </div>
  );
}
