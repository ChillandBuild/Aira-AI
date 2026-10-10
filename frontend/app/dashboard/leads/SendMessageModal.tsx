"use client";
import { useState } from "react";
import { X, Send, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { api, Lead } from "@/lib/api";

interface SendMessageModalProps {
  selectedLeads: Lead[];
  onClose: () => void;
  onAfterSend: () => void;
}

export function SendMessageModal({ selectedLeads, onClose, onAfterSend }: SendMessageModalProps) {
  const [message, setMessage] = useState("");
  const [sending, setSending] = useState(false);

  // Compute which leads have open reply windows
  const now = new Date();
  const openLeads = selectedLeads.filter((lead) => {
    if (!lead.last_inbound_at) return false;
    const lastInbound = new Date(lead.last_inbound_at).getTime();
    const diffMs = now.getTime() - lastInbound;
    const hoursLeft = 24 - diffMs / (1000 * 60 * 60);
    return hoursLeft > 0;
  });
  const skipped = selectedLeads.length - openLeads.length;
  const canSend = openLeads.length > 0 && message.trim() && !sending;

  async function send() {
    if (!canSend) return;
    setSending(true);
    let sent = 0;
    let failed = 0;

    for (const lead of openLeads) {
      try {
        await api.leads.sendMessage(lead.id, message.trim());
        sent++;
      } catch {
        failed++;
      }
    }

    setSending(false);
    let msg = `Sent ${sent}`;
    if (skipped > 0) msg += ` · ${skipped} skipped — reply window closed`;
    if (failed > 0) msg += ` · ${failed} failed`;
    toast.success(msg);
    onAfterSend();
    onClose();
  }

  return (
    <div className="fixed inset-0 z-dialog flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div
        className="bg-white rounded-2xl shadow-lg w-full max-w-md p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-5">
          <h3 className="font-display text-lg font-bold text-[#0A1528]">Send message</h3>
          <button onClick={onClose} className="text-[#64748b] hover:text-[#0A1528]">
            <X size={20} />
          </button>
        </div>

        {openLeads.length === 0 ? (
          <div className="p-4 rounded-xl bg-amber-50 border border-amber-200 mb-4">
            <p className="text-xs text-amber-700">
              None of the selected leads have an open reply window. Use Send template on each lead instead.
            </p>
          </div>
        ) : (
          <>
            <p className="text-xs text-[#64748b] mb-4">
              Goes to {openLeads.length} of {selectedLeads.length} selected
              {skipped > 0 ? ` — ${skipped} skipped, reply window closed` : ""}
            </p>
            <textarea
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              rows={4}
              placeholder="Type your message..."
              className="w-full px-4 py-3 bg-[#f8fafc] rounded-xl font-body text-sm text-[#0A1528] border border-[#e2e8f0] focus:outline-none focus:ring-2 focus:ring-primary resize-none"
            />
          </>
        )}

        <div className="flex justify-end gap-2 mt-5">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-[#f1f5f9] text-[#0A1528] rounded-xl font-label text-sm font-semibold hover:bg-[#e2e8f0]"
          >
            Cancel
          </button>
          <button
            onClick={send}
            disabled={!canSend}
            className="flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-xl font-label text-sm font-semibold hover:bg-primary/90 disabled:opacity-50"
          >
            {sending ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
            {sending ? "Sending…" : "Send"}
          </button>
        </div>
      </div>
    </div>
  );
}
