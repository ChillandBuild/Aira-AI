"use client";

import { toast } from "sonner";
import { Target, Copy, Tag } from "lucide-react";
import type { Lead } from "@/lib/api";

interface LeadAttributionProps {
  lead: Lead;
  variant?: "full" | "compact";
}

// Marketing source only (campaign/inbound). The assignment timestamp is shown
// separately by each consumer, so it is deliberately not rendered here.
export default function LeadAttribution({ lead, variant = "full" }: LeadAttributionProps) {
  const isCompact = variant === "compact";
  const hasOutbound = !!(lead.broadcast_id || lead.template_name);

  const copyToClipboard = (text: string, label: string) => {
    navigator.clipboard.writeText(text);
    toast.success(`${label} copied to clipboard`);
  };

  if (hasOutbound) {
    return (
      <div className={`bg-gradient-to-br from-purple-50/50 to-indigo-50/20 border border-purple-100/60 shadow-sm flex flex-col ${
        isCompact ? "rounded-2xl p-4 gap-3" : "rounded-3xl p-5 gap-4"
      }`}>
        <span className={`font-display font-black text-purple-800 uppercase tracking-widest flex items-center gap-1.5 ${
          isCompact ? "text-[10px]" : "text-[11px]"
        }`}>
          <Target size={isCompact ? 11 : 12} className="text-purple-500" /> Outbound Campaign
        </span>
        <div className={isCompact ? "grid grid-cols-2 gap-2.5" : "space-y-3.5"}>
          <div className={`bg-white/90 backdrop-blur-sm border border-purple-100/65 rounded-xl relative shadow-sm ${
            isCompact ? "p-3" : "p-3.5"
          }`}>
            <span className="font-label text-[9px] text-purple-700/60 uppercase font-extrabold block">Broadcast Campaign ID</span>
            <p className={`font-mono text-[#292524] font-bold mt-1.5 truncate select-all ${
              isCompact ? "text-[10px] pr-6" : "text-xs pr-8"
            }`}>
              {lead.broadcast_id || "None"}
            </p>
            {lead.broadcast_id && (
              <button 
                onClick={() => copyToClipboard(lead.broadcast_id || "", "Campaign ID")}
                className={`absolute text-purple-400 hover:text-purple-700 hover:bg-purple-50 rounded-lg transition-colors ${
                  isCompact ? "right-2.5 bottom-2.5 p-1" : "right-3 bottom-3 p-1.5"
                }`}
                title="Copy ID"
              >
                <Copy size={isCompact ? 10 : 11} />
              </button>
            )}
          </div>

          <div className={`bg-white/90 backdrop-blur-sm border border-purple-100/65 rounded-xl shadow-sm ${
            isCompact ? "p-3" : "p-3.5"
          }`}>
            <span className="font-label text-[9px] text-purple-700/60 uppercase font-extrabold block">Message Template</span>
            <p className="font-body text-xs text-[#1c1917] font-bold mt-1.5 truncate">
              {lead.template_name || "N/A"}
            </p>
          </div>

          {lead.tag_name && (
            <div className={`bg-white/90 backdrop-blur-sm border border-purple-100/65 rounded-xl shadow-sm flex items-center gap-1.5 ${
              isCompact ? "p-3 col-span-2" : "p-3.5"
            }`}>
              <Tag size={11} className="text-purple-500 shrink-0" />
              <div>
                <span className="font-label text-[9px] text-purple-700/60 uppercase font-extrabold block">Campaign Tag</span>
                <span className="text-xs font-bold text-purple-700 mt-0.5 inline-block">{lead.tag_name}</span>
              </div>
            </div>
          )}
        </div>
      </div>
    );
  } else {
    return (
      <div className={`bg-gradient-to-br from-emerald-50/50 to-teal-50/20 border border-emerald-100/60 shadow-sm flex flex-col ${
        isCompact ? "rounded-2xl p-4 gap-3" : "rounded-3xl p-5 gap-4"
      }`}>
        <span className={`font-display font-black text-emerald-800 uppercase tracking-widest flex items-center gap-1.5 ${
          isCompact ? "text-[10px]" : "text-[11px]"
        }`}>
          <Target size={isCompact ? 11 : 12} className="text-emerald-500" /> Inbound Origin
        </span>
        <div className={`grid grid-cols-2 ${isCompact ? "gap-2.5" : "gap-3.5"}`}>
          <div className={`bg-white/90 backdrop-blur-sm border border-emerald-100/65 rounded-xl shadow-sm ${
            isCompact ? "p-3" : "p-3.5"
          }`}>
            <span className="font-label text-[9px] text-emerald-700/60 uppercase font-extrabold block">Ad Campaign</span>
            <p className="font-body text-xs text-[#1c1917] font-bold mt-1 truncate">{lead.ad_campaign_name || "Organic Traffic"}</p>
          </div>
          <div className={`bg-white/90 backdrop-blur-sm border border-emerald-100/65 rounded-xl shadow-sm ${
            isCompact ? "p-3" : "p-3.5"
          }`}>
            <span className="font-label text-[9px] text-emerald-700/60 uppercase font-extrabold block">Channel Source</span>
            <p className="font-body text-xs text-[#1c1917] font-bold mt-1 capitalize truncate">{lead.channel || lead.source || "Organic"}</p>
          </div>
        </div>
      </div>
    );
  }
}
