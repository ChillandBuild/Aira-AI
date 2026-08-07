"use client";
import { CheckCircle2, Clock } from "lucide-react";
import { ExpertHandoffSession } from "@/lib/api";

function formatFieldKey(key: string): string {
  return key
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

export function ConsultationDetails({ session }: { session: ExpertHandoffSession }) {
  const fee = session.amount_paise != null ? `₹${(session.amount_paise / 100).toFixed(0)}` : "—";
  const entries = Object.entries(session.collected_data || {});

  return (
    <div className="card rounded-2xl p-5 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="font-display font-bold text-ink text-sm">Consultation Details</h3>
        {session.status === "paid" ? (
          <span className="badge badge-green inline-flex items-center gap-1">
            <CheckCircle2 size={10} /> Paid {fee}
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 text-amber-700 border border-amber-200 px-2.5 py-1 font-label text-[10px] font-bold">
            <Clock size={10} /> Awaiting payment · {fee}
          </span>
        )}
      </div>
      <div className="grid grid-cols-2 gap-3">
        {entries.map(([key, value]) => (
          <div key={key}>
            <div className="font-label text-[10px] font-bold uppercase tracking-wide text-ink-muted">
              {formatFieldKey(key)}
            </div>
            <div className="font-body text-sm text-ink mt-0.5">{value || "—"}</div>
          </div>
        ))}
        {entries.length === 0 && (
          <p className="font-body text-xs text-ink-muted italic col-span-2">No details collected yet.</p>
        )}
      </div>
    </div>
  );
}
