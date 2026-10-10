"use client";
import { X } from "lucide-react";
import dynamic from "next/dynamic";

interface SendTemplateModalProps {
  leadId: string;
  onClose: () => void;
}

// Dynamically import SendDetailsCard to avoid circular dependencies
const SendDetailsCard = dynamic(
  () => import("@/app/dashboard/telecalling/components/SendDetailsCard").then((mod) => mod.default),
  { ssr: false, loading: () => <div className="p-8 text-center text-xs text-[#64748b]">Loading...</div> }
);

export function SendTemplateModal({ leadId, onClose }: SendTemplateModalProps) {
  return (
    <div className="fixed inset-0 z-dialog flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div
        className="bg-white rounded-2xl shadow-xl w-full max-w-lg p-5 max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-5">
          <h3 className="font-display text-lg font-bold text-[#0A1528]">Send template</h3>
          <button onClick={onClose} className="text-[#64748b] hover:text-[#0A1528]">
            <X size={20} />
          </button>
        </div>

        <SendDetailsCard leadId={leadId} />
      </div>
    </div>
  );
}
