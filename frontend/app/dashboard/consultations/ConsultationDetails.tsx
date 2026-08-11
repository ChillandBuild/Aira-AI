"use client";
import { useState } from "react";
import { CheckCircle2, Clock, Phone, Loader2 } from "lucide-react";
import { api, ExpertHandoffSession } from "@/lib/api";

function formatFieldKey(key: string): string {
  return key
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

interface ConsultationDetailsProps {
  session: ExpertHandoffSession;
  onResolved: () => void;
}

export function ConsultationDetails({ session, onResolved }: ConsultationDetailsProps) {
  const [resolving, setResolving] = useState(false);
  const fee = session.amount_paise != null ? `₹${(session.amount_paise / 100).toFixed(0)}` : "—";
  const entries = Object.entries(session.collected_data || {});

  async function handleResolve() {
    setResolving(true);
    try {
      await api.expertHandoff.resolveSession(session.id);
      onResolved();
    } catch {
      setResolving(false);
    }
  }

  return (
    <div className="card rounded-2xl p-5 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-display font-bold text-ink text-sm">Consultation Details</h3>
          <div className="flex items-center gap-1 mt-0.5 text-xs text-ink-muted font-body">
            <span>{session.leads?.name || "Unknown lead"}</span>
            <span className="text-border">·</span>
            <Phone size={11} />
            <span>{session.leads?.phone || "—"}</span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {session.status === "paid" ? (
            <span className="badge badge-green inline-flex items-center gap-1">
              <CheckCircle2 size={10} /> Paid {fee}
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 text-amber-700 border border-amber-200 px-2.5 py-1 font-label text-[10px] font-bold">
              <Clock size={10} /> Awaiting payment · {fee}
            </span>
          )}
          {session.status === "paid" && (
            <button
              type="button"
              onClick={handleResolve}
              disabled={resolving}
              className="inline-flex items-center gap-1 rounded-full bg-primary text-white px-3 py-1 font-label text-[10px] font-bold hover:bg-primary/90 disabled:opacity-60"
            >
              {resolving ? <Loader2 size={10} className="animate-spin" /> : null}
              Mark Resolved
            </button>
          )}
        </div>
      </div>

      {entries.length === 0 ? (
        <p className="font-body text-xs text-ink-muted italic">No details collected yet.</p>
      ) : (
        <table className="w-full border-collapse">
          <tbody>
            {entries.map(([key, value]) => (
              <tr key={key} className="border-b border-border-subtle last:border-0">
                <td className="py-2 pr-4 font-label text-[10px] font-bold uppercase tracking-wide text-ink-muted whitespace-nowrap align-top">
                  {formatFieldKey(key)}
                </td>
                <td className="py-2 font-body text-sm text-ink">{value || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
