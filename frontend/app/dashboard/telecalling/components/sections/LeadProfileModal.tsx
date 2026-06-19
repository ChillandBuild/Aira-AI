"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Phone, Users, Calendar, X, Loader2 } from "lucide-react";
import { api, type Lead } from "@/lib/api";
import { formatPhone, timeAgo } from "@/lib/utils";
import { fetchNotes } from "../../lib/notes-api";
import type { NotesResponse, Note } from "../../types";

interface LeadProfileModalProps {
  leadId: string;
  onClose: () => void;
}

export default function LeadProfileModal({ leadId, onClose }: LeadProfileModalProps) {
  const [lead, setLead] = useState<Lead | null>(null);
  const [notes, setNotes] = useState<NotesResponse | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      api.leads.get(leadId),
      fetchNotes(leadId).catch(() => ({ pinned: [], notes: [] })),
    ])
      .then(([leadData, notesData]) => {
        setLead(leadData);
        setNotes(notesData);
      })
      .catch((err) => {
        toast.error("Failed to load lead profile");
        console.error(err);
      })
      .finally(() => setLoading(false));
  }, [leadId]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/45 backdrop-blur-sm cursor-pointer"
      onClick={onClose}
    >
      <div
        className="w-full max-w-4xl bg-white rounded-3xl p-7 shadow-2xl max-h-[90vh] overflow-y-auto cursor-default border border-[#e8e3db]/50 flex flex-col gap-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-[#f0ece4] pb-4">
          <h3 className="font-display text-lg font-bold text-[#292524] flex items-center gap-2">
            🔍 Lead Attribution profile
          </h3>
          <button
            onClick={onClose}
            className="p-2 text-[#a8a29e] hover:text-[#44403c] hover:bg-[#faf8f5] rounded-xl transition-all"
          >
            <X size={16} />
          </button>
        </div>

        {loading ? (
          <div className="py-12 flex flex-col items-center justify-center">
            <Loader2 className="animate-spin text-indigo-500 mb-2" size={28} />
            <p className="text-xs text-[#78716c] font-medium">Fetching lead history...</p>
          </div>
        ) : lead ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8 items-start">
            <div className="space-y-6">
              <div className="bg-[#faf8f5]/50 border border-[#f0ece4] p-5 rounded-2xl">
                <div className="flex items-center gap-3">
                  <div className="w-12 h-12 rounded-xl bg-indigo-500 text-white font-display text-lg font-bold flex items-center justify-center">
                    {lead.name ? lead.name.charAt(0).toUpperCase() : <Users size={18} />}
                  </div>
                  <div>
                    <div className="flex items-center gap-2 flex-wrap">
                      <p className="font-body text-base font-extrabold text-[#1c1917]">{lead.name || "Unnamed Lead"}</p>
                      <span className={`px-2 py-0.5 rounded font-label text-[9px] font-black uppercase ${
                        lead.segment === "A" ? "bg-emerald-50 text-emerald-700 border border-emerald-100" :
                        lead.segment === "B" ? "bg-blue-50 text-blue-700 border border-blue-100" :
                        lead.segment === "C" ? "bg-amber-50 text-amber-700 border border-amber-100" :
                        "bg-[#f0ece4] text-[#44403c]"
                      }`}>
                        Seg {lead.segment}
                      </span>
                      {lead.call_status && (
                        <span className={`px-2 py-0.5 rounded font-label text-[9px] font-black uppercase ${
                          lead.call_status === "converted" ? "bg-emerald-100 text-emerald-800 border border-emerald-250" :
                          lead.call_status === "dnc" ? "bg-red-100 text-red-800 border border-red-200" :
                          lead.call_status === "unreachable" ? "bg-rose-100 text-rose-800 border border-rose-250" :
                          lead.call_status === "callback" ? "bg-amber-100 text-amber-800 border border-amber-250" :
                          "bg-indigo-100 text-indigo-800 border border-indigo-200"
                        }`}>
                          {lead.call_status}
                        </span>
                      )}
                      {lead.do_not_call && (
                        <span className="px-2 py-0.5 bg-red-650 text-white rounded font-label text-[9px] font-black uppercase">
                          DNC
                        </span>
                      )}
                    </div>
                    <p className="font-label text-xs text-[#78716c] mt-1 select-all">
                      {formatPhone(lead.phone)} · Score {lead.score}/10
                    </p>
                  </div>
                </div>
              </div>

              <div className="bg-white border border-[#e8e3db]/60 rounded-2xl p-4 flex items-center gap-3 shadow-sm">
                <Calendar size={16} className="text-indigo-500 shrink-0" />
                <div>
                  <p className="font-label text-[9px] text-[#a8a29e] uppercase tracking-wider font-extrabold">Queue Assignment Timestamp</p>
                  <p className="font-body text-xs text-[#292524] font-bold mt-0.5">
                    {lead.assigned_at
                      ? new Date(lead.assigned_at).toLocaleString("en-US", { dateStyle: "long", timeStyle: "short" })
                      : "Unknown (Assigned prior to tracking)"}
                  </p>
                </div>
              </div>

              {lead.broadcast_id || lead.template_name ? (
                <div className="bg-gradient-to-br from-purple-50/50 to-indigo-50/20 border border-purple-100/60 rounded-3xl p-5 shadow-sm space-y-4">
                  <span className="font-display text-[11px] font-black text-purple-800 uppercase tracking-widest flex items-center gap-1.5">
                    <Phone size={12} className="text-purple-500" /> Outbound Campaign
                  </span>
                  <div className="space-y-3.5">
                    <div className="bg-white/90 backdrop-blur-sm border border-purple-100/65 rounded-xl p-3.5 relative shadow-sm">
                      <span className="font-label text-[9px] text-purple-700/60 uppercase font-extrabold block">Broadcast Campaign ID</span>
                      <p className="font-mono text-xs text-[#292524] font-bold mt-1.5 truncate pr-8 select-all">
                        {lead.broadcast_id || "None"}
                      </p>
                    </div>
                    <div className="bg-white/90 backdrop-blur-sm border border-purple-100/65 rounded-xl p-3.5 shadow-sm">
                      <span className="font-label text-[9px] text-purple-700/60 uppercase font-extrabold block">Message Template</span>
                      <p className="font-body text-xs text-[#1c1917] font-bold mt-1.5 truncate">
                        {lead.template_name || "N/A"}
                      </p>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="bg-gradient-to-br from-emerald-50/50 to-teal-50/20 border border-emerald-100/60 rounded-3xl p-5 shadow-sm space-y-4">
                  <span className="font-display text-[11px] font-black text-emerald-800 uppercase tracking-widest flex items-center gap-1.5">
                    <Phone size={12} className="text-emerald-500" /> Inbound Origin
                  </span>
                  <div className="grid grid-cols-2 gap-3.5">
                    <div className="bg-white/90 backdrop-blur-sm border border-emerald-100/65 rounded-xl p-3.5 shadow-sm">
                      <span className="font-label text-[9px] text-emerald-700/60 uppercase font-extrabold block">Ad Campaign</span>
                      <p className="font-body text-xs text-[#1c1917] font-bold mt-1 truncate">{lead.ad_campaign_name || "Organic Traffic"}</p>
                    </div>
                    <div className="bg-white/90 backdrop-blur-sm border border-emerald-100/65 rounded-xl p-3.5 shadow-sm">
                      <span className="font-label text-[9px] text-emerald-700/60 uppercase font-extrabold block">Channel Source</span>
                      <p className="font-body text-xs text-[#1c1917] font-bold mt-1 capitalize truncate">{lead.channel || lead.source || "Organic"}</p>
                    </div>
                  </div>
                </div>
              )}
            </div>

            <div className="space-y-4">
              <h4 className="font-display text-xs font-black text-[#292524] uppercase tracking-widest flex items-center gap-1.5">
                <Users size={12} className="text-indigo-500" /> Lead Interaction Timeline
              </h4>

              {notes?.pinned && notes.pinned.length > 0 && (
                <div className="space-y-1.5">
                  <p className="font-label text-[9px] text-[#a8a29e] uppercase tracking-wider font-extrabold">📌 Pinned Notes</p>
                  {notes.pinned.map((n: Note) => (
                    <div key={n.id} className="p-3 bg-indigo-50 border border-indigo-100 rounded-xl text-xs text-[#44403c] font-semibold shadow-sm">
                      {n.content}
                    </div>
                  ))}
                </div>
              )}

              <div className="space-y-3">
                <p className="font-label text-[9px] text-[#a8a29e] uppercase tracking-wider font-extrabold">📝 Recent Notes</p>
                {notes?.notes && notes.notes.length > 0 ? (
                  <div className="relative border-l border-[#f0ece4] pl-4 ml-2.5 max-h-[350px] overflow-y-auto pr-1 space-y-4">
                    {notes.notes.slice(0, 5).map((n: Note) => (
                      <div key={n.id} className="relative">
                        <span className="absolute -left-[21px] top-1 w-2 h-2 rounded-full bg-indigo-400 border-2 border-white ring-4 ring-white" />
                        <div className="flex justify-between items-center text-[9px] text-[#a8a29e] font-bold mb-1">
                          <span>{timeAgo(n.created_at)}</span>
                          {n.is_pinned && <span className="text-indigo-600 bg-indigo-50 px-1.5 py-0.5 rounded font-black text-[8px]">PINNED</span>}
                        </div>
                        <p className="font-body text-xs text-[#57534e] bg-[#faf8f5] border border-[#f0ece4] p-3 rounded-2xl leading-relaxed break-words font-medium">
                          {n.content}
                        </p>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-[#a8a29e] text-center py-8 bg-[#faf8f5]/60 border border-[#f0ece4] rounded-2xl">
                    No prior interaction notes logged.
                  </p>
                )}
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
